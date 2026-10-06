import asyncio
import time

import httpx
import pytest
from conftest import login
from fastapi import HTTPException
from searchbar.cache import AsyncCache
from searchbar.db import GuestCode, Profile, SearchConfiguration
from searchbar.paperless import Paperless
from searchbar.schemas import Rules, Search
from sqlalchemy import select


async def test_cache_coalesces_copies_expires_and_retries_failures():
    clock = [0]
    cache = AsyncCache(300, clock=lambda: clock[0])
    calls = 0
    fail = False

    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        if fail:
            raise ValueError("upstream failed")
        return {"nested": [calls]}

    results = await asyncio.gather(*(cache.get("same", load) for _ in range(20)))
    assert calls == 1
    results[0].value["nested"].append(99)
    assert results[1].value == {"nested": [1]}
    clock[0] = 299
    assert (await cache.get("same", load)).value == {"nested": [1]}
    clock[0] = 300
    fail = True
    with pytest.raises(ValueError):
        await cache.get("same", load)
    fail = False
    assert (await cache.get("same", load)).value == {"nested": [3]}
    await cache.close()


async def test_cache_lru_deadline_and_disabled_mode():
    clock = [0]
    cache = AsyncCache(300, capacity=128, clock=lambda: clock[0])

    async def load():
        return []

    for key in range(128):
        await cache.get(key, load)
    await cache.get(0, load)
    await cache.get(128, load)
    assert len(cache.entries) == 128
    assert 0 in cache.entries and 1 not in cache.entries
    clock[0] = 290
    entry = await cache.get("derived", load, expires_at=300)
    assert entry.expires_at == 300
    clock[0] = 300
    assert (await cache.get("derived", load, expires_at=600)).generation != entry.generation
    await cache.close()
    cache = AsyncCache(0)
    await asyncio.gather(*(cache.get("same", load) for _ in range(3)))
    assert not cache.entries and not cache.pending


async def test_cancelled_waiter_does_not_cancel_shared_load():
    cache = AsyncCache(300)
    started, finish = asyncio.Event(), asyncio.Event()

    async def load():
        started.set()
        await finish.wait()
        return "ok"

    first = asyncio.create_task(cache.get("same", load))
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(cache.get("same", load))
    finish.set()
    assert (await second).value == "ok"
    await cache.close()
    assert not cache.pending


def controlled_clock(app):
    clock = [0]
    app.state.paperless.catalog_cache.clock = lambda: clock[0]
    app.state.paperless.filter_cache.clock = lambda: clock[0]
    return clock


def test_warm_search_thumbnails_and_filters_avoid_repeated_work(env):
    app, client, fake = env
    clock = controlled_clock(app)
    login(client)
    started = time.perf_counter()
    first = client.get("/api/filters")
    cold_time = time.perf_counter() - started
    assert first.status_code == 200
    cold_calls = len(fake.calls)
    fake.calls.clear()
    started = time.perf_counter()
    assert client.get("/api/filters").json() == first.json()
    warm_time = time.perf_counter() - started
    assert not fake.calls
    print(
        f"\nGuest filters (fixture): cold {cold_calls} calls/{cold_time:.4f}s; warm 0 calls/{warm_time:.4f}s"
    )
    assert client.post("/api/documents/search", json={"storage_path": 1}).status_code == 200
    assert client.get("/api/documents/101/thumb").status_code == 200
    assert [r.url.path for r in fake.calls] == [
        "/api/documents/",
        "/api/documents/",
        "/api/documents/101/thumb/",
    ]
    assert fake.calls[1].url.params["fields"] == "id"
    # A later derived entry must not extend the original catalog's freshness.
    clock[0] = 290
    with app.state.db() as db:
        db.get(SearchConfiguration, 1).custom_field_ids = [1]
        db.commit()
    assert client.get("/api/filters").status_code == 200
    fake.catalog["storage_paths"] = []
    clock[0] = 300
    assert client.get("/api/filters").status_code == 403
    assert client.get("/api/documents/101/thumb").status_code == 403


def test_filter_cache_obeys_profile_settings_and_revocation(env):
    app, client, fake = env
    login(client)
    original = client.get("/api/filters").json()
    assert original["storage_paths"] == [{"id": 1, "name": "Buchhaltung"}]
    with app.state.db() as db:
        profile = db.scalar(select(Profile))
        profile.rules = Rules(storage_paths=[2]).model_dump()
        db.commit()
    changed = client.get("/api/filters").json()
    assert changed["storage_paths"] == [{"id": 2, "name": "Privat"}]
    assert changed["custom_fields"][1]["options"] == [{"id": "b", "label": "Vertraulich"}]
    with app.state.db() as db:
        db.get(SearchConfiguration, 1).custom_field_ids = [5]
        db.commit()
    assert [f["id"] for f in client.get("/api/filters").json()["custom_fields"]] == [5]
    with app.state.db() as db:
        db.scalar(select(GuestCode)).revoked = True
        db.commit()
    assert client.get("/api/filters").status_code == 401
    login(client, admin=True)
    # Guest filtering must not change the cached catalog shared with administrators.
    catalogs = client.get("/api/admin/filters").json()
    assert len(catalogs["storage_paths"]) == 2
    assert len(next(f for f in catalogs["custom_fields"] if f["id"] == 5)["options"]) == 2


def test_disabled_caches_and_expired_upstream_failure(env):
    app, client, fake = env
    clock = controlled_clock(app)
    login(client)
    assert client.get("/api/filters").status_code == 200
    clock[0] = 300
    fake.error = 500
    assert client.get("/api/filters").status_code == 502
    fake.error = None
    app.state.paperless.catalog_cache.ttl = 0
    app.state.paperless.filter_cache.ttl = 0
    assert client.get("/api/filters").status_code == 200
    fake.calls.clear()
    assert client.get("/api/filters").status_code == 200
    assert len(fake.calls) > 4


async def test_parallel_probes_are_bounded_ordered_and_faster(env):
    app, _, fake = env
    active = peak = 0

    async def delayed(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.01)
            return fake.handle(request)
        finally:
            active -= 1

    client = Paperless(app.state.settings, transport=httpx.MockTransport(delayed))
    try:
        catalogs = await client.catalogs()
        choices = [{"id": 101 if i % 2 else 999} for i in range(60)]

        def query(item):
            return Search(document_id=item["id"])

        rules = Rules(all_documents=True)
        start = time.perf_counter()
        expected = [item for item in choices if await client.exists(query(item), rules, catalogs)]
        sequential = time.perf_counter() - start
        peak = 0
        start = time.perf_counter()
        results = await asyncio.gather(
            client.visible_choices(choices[:30], query, rules, catalogs),
            client.visible_choices(choices[30:], query, rules, catalogs),
        )
        parallel = time.perf_counter() - start
        assert results[0] + results[1] == expected
        assert peak == 6 and active == 0
        print(
            f"\n60 probes, 10ms upstream delay: sequential {sequential:.3f}s; parallel {parallel:.3f}s ({sequential / parallel:.1f}x)"
        )
        # Structural concurrency assertions are stable; timings are diagnostic only.
        fake.error = 500
        with pytest.raises(HTTPException):
            await client.visible_choices(choices, query, rules, catalogs)
        assert active == 0
    finally:
        await client.close()


def test_static_cache_headers(env, tmp_path):
    from fastapi.testclient import TestClient
    from searchbar.app import create_app

    original, _, _ = env
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-abc123.js").write_text("export {}")
    (tmp_path / "pdfjs").mkdir()
    (tmp_path / "pdfjs" / "font.bin").write_bytes(b"font")
    (tmp_path / "index.html").write_text("app")
    settings = original.state.settings.model_copy(update={"static_dir": str(tmp_path)})
    with TestClient(create_app(settings)) as client:
        asset = client.get("/assets/app-abc123.js")
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert (
            client.get(
                "/assets/app-abc123.js", headers={"If-None-Match": asset.headers["etag"]}
            ).status_code
            == 304
        )
        assert client.get("/pdfjs/font.bin").headers["cache-control"] == "no-cache"
        assert client.get("/").headers["cache-control"] == "no-cache"
