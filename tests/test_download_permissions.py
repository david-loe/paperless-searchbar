import httpx
import pytest
from conftest import login
from fastapi.testclient import TestClient
from searchbar.db import BrowserSession, User, now
from searchbar.security import COOKIE, digest
from sqlalchemy import select


@pytest.mark.parametrize("is_admin", [False, True])
def test_downloads_default_off_without_affecting_previews(env, is_admin):
    _, client, fake = env
    assert login(client, admin=is_admin)["allow_download"] is False
    assert client.get("/api/documents/101").status_code == 200
    assert client.get("/api/documents/101/preview").status_code == 200
    assert client.get("/api/documents/101/thumb").status_code == 200
    assert client.get("/api/documents/101/download").status_code == 403
    assert not any(r.url.path.endswith("/download/") for r in fake.calls)


def test_code_permission_changes_existing_session_and_is_independent(env):
    app, guest, _ = env
    login(guest)
    admin = TestClient(app)
    try:
        login(admin, admin=True)
        default = admin.post(
            "/api/admin/codes", json={"name": "Default", "profile_id": 1, "expires_at": now() + 300}
        ).json()
        enabled = admin.post(
            "/api/admin/codes",
            json={
                "name": "Enabled",
                "profile_id": 1,
                "expires_at": now() + 300,
                "allow_download": True,
            },
        ).json()
        listing = {c["id"]: c for c in admin.get("/api/admin/codes").json()}
        assert listing[default["id"]]["allow_download"] is False
        assert listing[enabled["id"]]["allow_download"] is True
        for allow in (True, False):
            assert (
                admin.patch("/api/admin/codes/1", json={"allow_download": allow}).status_code == 200
            )
            assert guest.get("/api/auth/session").json()["allow_download"] is allow
            assert guest.get("/api/documents/101/download").status_code == (200 if allow else 403)
            assert guest.get("/api/documents/202/download").status_code == 404
            assert guest.get("/api/documents/101/preview").status_code == 200
        assert admin.get("/api/auth/session").json()["allow_download"] is False
        listing = {c["id"]: c for c in admin.get("/api/admin/codes").json()}
        assert listing[default["id"]]["allow_download"] is False
        assert listing[enabled["id"]]["allow_download"] is True
    finally:
        admin.close()


@pytest.mark.parametrize("local_admin", [False, True])
def test_user_download_permission_is_live_and_not_derived_from_role(env, local_admin):
    app, client, _ = env
    if local_admin:
        login(client, admin=True)
        identity = 1
    else:
        # Bind an already-authenticated OIDC session to a new regular user.
        login(client)
        with app.state.db() as db:
            user = User(
                name="OIDC", issuer="https://idp.test", subject="download-user", profile_id=1
            )
            db.add(user)
            db.flush()
            identity = user.id
            row = db.get(BrowserSession, digest(app.state.settings, client.cookies.get(COOKIE)))
            row.code_id, row.user_id = None, identity
            db.commit()
    admin = TestClient(app)
    try:
        login(admin, admin=True)
        assert client.get("/api/auth/session").json()["allow_download"] is False
        body = {"profile_id": None if local_admin else 1, "active": True, "is_admin": local_admin}
        for allow in (True, False):
            assert (
                admin.put(
                    f"/api/admin/users/{identity}", json={**body, "allow_download": allow}
                ).status_code
                == 200
            )
            assert client.get("/api/auth/session").json()["allow_download"] is allow
            assert client.get("/api/documents/101/download").status_code == (200 if allow else 403)
            # Updating unrelated rights must not reset the explicit download choice.
            assert admin.put(f"/api/admin/users/{identity}", json=body).status_code == 200
            assert client.get("/api/auth/session").json()["allow_download"] is allow
        assert admin.get("/api/admin/codes").json()[0]["allow_download"] is False
        if not local_admin:
            assert admin.get("/api/auth/session").json()["allow_download"] is False
        with app.state.db() as db:
            assert db.scalar(select(User).where(User.id == identity)).allow_download is False
    finally:
        admin.close()


def test_download_settings_require_admin_and_csrf(env):
    _, client, _ = env
    assert client.patch("/api/admin/codes/1", json={"allow_download": True}).status_code == 403
    login(client)
    assert client.patch("/api/admin/codes/1", json={"allow_download": True}).status_code == 403
    assert (
        client.put(
            "/api/admin/users/1", json={"active": True, "is_admin": True, "allow_download": True}
        ).status_code
        == 403
    )
    login(client, admin=True)
    assert (
        client.patch(
            "/api/admin/codes/1", json={"allow_download": True}, headers={"x-csrf-token": "wrong"}
        ).status_code
        == 403
    )
    assert client.patch("/api/admin/codes/999", json={"allow_download": True}).status_code == 404
    for payload in ({}, {"allow_download": "false"}, {"allow_download": True, "revoked": False}):
        assert client.patch("/api/admin/codes/1", json=payload).status_code == 422


def test_non_pdf_preview_does_not_offer_an_alternative_download(env):
    app, client, fake = env
    login(client)

    def handle(request):
        if request.url.path.endswith("/preview/"):
            return httpx.Response(
                200,
                stream=httpx.ByteStream(b"original document"),
                headers={"Content-Type": "application/octet-stream"},
            )
        return fake.handle(request)

    app.state.paperless.http = httpx.AsyncClient(
        base_url="http://paperless.test/api/",
        headers={"Authorization": "Token test-token"},
        transport=httpx.MockTransport(handle),
    )
    assert client.get("/api/documents/101/preview").status_code == 403
