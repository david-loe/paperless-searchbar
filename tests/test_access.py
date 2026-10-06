import json

import pytest
from conftest import login
from searchbar.db import BrowserSession, GuestCode, Profile, User, now
from searchbar.schemas import Rules
from sqlalchemy import select


def test_guest_scope_counts_and_direct_access(env):
    _, client, fake = env
    login(client)
    response = client.post("/api/documents/search", json={"storage_path": 1})
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert [d["id"] for d in response.json()["results"]] == [101]
    assert "PRIVATE OCR" not in response.text
    request = next(r for r in reversed(fake.calls) if r.url.path == "/api/documents/")
    assert request.url.params["storage_path__id__in"] == "1"
    assert json.loads(request.url.params["custom_field_query"])[1][0] == [1, "exact", "A"]
    for identity in (202, 303, 999):
        for suffix in ("", "/preview", "/download"):
            response = client.get(f"/api/documents/{identity}{suffix}")
            assert response.status_code == 404
            assert response.json()["detail"] == "Dokument nicht gefunden."
    assert not any("/202/" in str(r.url) for r in fake.calls)
    assert (
        client.get("/api/documents/101").json()["paperless_url"]
        == "https://docs.example/documents/101/"
    )


def test_search_cannot_override_permission_or_inject_query(env):
    _, c, _ = env
    login(c)
    for payload in (
        {"storage_path": 2},
        {"custom_fields": [{"field": 1, "op": "exact", "value": "B"}]},
    ):
        response = c.post("/api/documents/search", json=payload)
        assert response.json() == {"count": 0, "results": []}
    for payload in ({"document_id": 101, "query": "*"}, {"document_id": "101"}, {"page": 0}, {}):
        assert c.post("/api/documents/search", json=payload).status_code == 422


def test_selection_does_not_leak_other_paths_or_correspondents(env):
    _, c, _ = env
    login(c)
    data = c.get("/api/filters").json()
    assert [x["id"] for x in data["storage_paths"]] == [1]
    assert [x["id"] for x in data["correspondents"]] == [1]
    select = next(f for f in data["custom_fields"] if f["id"] == 5)
    assert select["options"] == [{"id": "a", "label": "Allgemein"}]


def test_admin_and_csrf(env):
    _, c, _ = env
    assert c.post("/api/auth/code", json={"code": "guest-code"}).status_code == 403
    login(c)
    assert c.get("/api/admin/users").status_code == 403
    assert (
        c.post(
            "/api/admin/codes", json={"name": "x", "profile_id": 1, "expires_at": now() + 300}
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/documents/search",
            json={"document_id": 101},
            headers={"origin": "https://evil.test"},
        ).status_code
        == 403
    )
    assert c.get("/api/documents/101").headers["cache-control"] == "private, no-store"
    assert c.get("/api/openapi.json").status_code == 403


@pytest.mark.parametrize("change", ["revoked", "expired", "profile", "empty", "session"])
def test_existing_session_immediately_loses_access(env, change):
    app, c, _ = env
    login(c)
    assert c.get("/api/documents/101").status_code == 200
    with app.state.db() as db:
        code = db.scalar(select(GuestCode))
        if change == "revoked":
            code.revoked = True
        elif change == "expired":
            code.expires_at = now() - 1
        elif change in ("profile", "empty"):
            p = db.get(Profile, code.profile_id)
            p.rules = (
                Rules(storage_paths=[2]).model_dump()
                if change == "profile"
                else Rules().model_dump()
            )
        else:
            for s in db.scalars(select(BrowserSession)):
                s.expires_at = now() - 1
        db.commit()
    assert c.get("/api/documents/101/download").status_code in (401, 404)


def test_deleted_reference_fails_closed_and_admin_sees_error(env):
    _, c, fake = env
    login(c)
    fake.catalog["storage_paths"] = []
    assert c.get("/api/documents/101").status_code == 403
    login(c, admin=True)
    assert c.get("/api/admin/profiles").json()[0]["error"]


def test_files_range_and_no_write_proxy(env):
    _, c, _ = env
    login(c)
    response = c.get("/api/documents/101/preview", headers={"range": "bytes=0-0"})
    assert response.status_code == 206
    assert response.content == b"%"
    assert response.headers["content-range"].startswith("bytes 0-0/")
    assert response.headers["content-disposition"].startswith("inline")
    assert c.get("/api/documents/101/download").content.startswith(b"%PDF")
    assert c.get("/api/documents/101/update_version").status_code == 404
    assert c.patch("/api/documents/101", json={"title": "hacked"}).status_code == 405


def test_admin_lifecycle(env):
    app, c, _ = env
    login(c, admin=True)
    profile = c.post(
        "/api/admin/profiles", json={"name": "Alle", "rules": {"all_documents": True}}
    ).json()
    assert "id" in profile
    response = c.post(
        "/api/admin/codes",
        json={"name": "Beratung", "profile_id": profile["id"], "expires_at": now() + 120},
    )
    assert response.status_code == 200
    code = response.json()
    assert len(code["code"]) >= 24
    listing = c.get("/api/admin/codes")
    assert code["code"] not in listing.text and "digest" not in listing.text
    assert c.post(f"/api/admin/codes/{code['id']}/revoke", json={}).status_code == 200
    with app.state.db() as db:
        user = User(name="OIDC Neu", issuer="https://idp.test", subject="new")
        db.add(user)
        db.commit()
        uid = user.id
    assert (
        c.put(
            f"/api/admin/users/{uid}",
            json={"profile_id": profile["id"], "active": True, "is_admin": False},
        ).status_code
        == 200
    )
    assert (
        c.put(
            "/api/admin/users/1", json={"profile_id": None, "active": False, "is_admin": False}
        ).status_code
        == 409
    )
    assert c.delete(f"/api/admin/profiles/{profile['id']}").status_code == 409


@pytest.mark.parametrize("status", [401, 403, 500])
def test_upstream_failure_is_controlled(env, status):
    _, c, fake = env
    login(c)
    fake.error = status
    response = c.get("/api/documents/101")
    assert response.status_code == 502
    assert "test-token" not in response.text


def test_rate_limit_and_session_rotation(env):
    _, c, _ = env
    first = c.get("/api/auth/session").json()
    cookie = c.cookies.get("searchbar_session")
    login(c)
    assert c.cookies.get("searchbar_session") != cookie
    assert (
        c.post("/api/auth/logout", json={}, headers={"x-csrf-token": first["csrf"]}).status_code
        == 403
    )
    c.post("/api/auth/logout", json={})
    csrf = c.get("/api/auth/session").json()["csrf"]
    for _ in range(16):
        response = c.post(
            "/api/auth/code", json={"code": "invalid"}, headers={"x-csrf-token": csrf}
        )
    assert response.status_code == 429
