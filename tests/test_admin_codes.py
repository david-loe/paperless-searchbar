import os
import subprocess

import pytest
from conftest import login
from searchbar.cli import rotate_admin_code
from searchbar.db import BrowserSession, User, now
from searchbar.security import COOKIE, digest
from sqlalchemy import select


def submit_code(client, code):
    csrf = client.get("/api/auth/session").json()["csrf"]
    return client.post("/api/auth/code", json={"code": code}, headers={"X-CSRF-Token": csrf})


def test_admin_uses_shared_code_endpoint_and_never_exposes_hash(env):
    app, client, _ = env
    previous_cookie = client.get("/api/auth/session").cookies.get(COOKIE)
    result = login(client, admin=True)
    assert result["is_admin"] and result["has_access"]
    assert client.cookies.get(COOKIE) != previous_cookie
    assert client.get("/api/documents/202").status_code == 200
    with app.state.db() as db:
        session = db.get(BrowserSession, digest(app.state.settings, client.cookies.get(COOKIE)))
        assert now() + 12 * 3600 - 5 <= session.expires_at <= now() + 12 * 3600
    for path in ("/api/auth/session", "/api/admin/users", "/api/admin/codes"):
        response = client.get(path)
        assert response.status_code == 200
        assert "local_code_digest" not in response.text
        assert digest(app.state.settings, "admin-code") not in response.text
        assert "admin-code" not in response.text
    assert client.post(
        "/api/auth/password", json={"username": "admin", "password": "unused"}
    ).status_code in (404, 405)
    assert "/api/auth/password" not in client.get("/api/openapi.json").json()["paths"]


def test_rotation_preserves_account_and_rejects_old_code_and_sessions(env):
    app, client, _ = env
    login(client, admin=True)
    stale_cookie = client.cookies.get(COOKIE)
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        identity = user.id
        old_hash = user.local_code_digest
        db.add(
            BrowserSession(
                digest="other-admin-session",
                user_id=identity,
                csrf="csrf",
                expires_at=now() + 300,
                local_code_digest=old_hash,
            )
        )
        db.commit()
    raw = rotate_admin_code(app.state.settings)
    assert len(raw) >= 32 and raw != "admin-code"
    with app.state.db() as db:
        user = db.get(User, identity)
        assert user.username == "admin" and user.is_admin
        assert user.local_code_digest == digest(app.state.settings, raw)
        assert db.scalar(select(BrowserSession).where(BrowserSession.user_id == identity)) is None
    assert client.get("/api/admin/users").status_code == 401
    assert submit_code(client, "admin-code").status_code == 401
    assert submit_code(client, raw).status_code == 200
    assert client.get("/api/auth/session").json()["is_admin"]
    # An in-flight login using the old credential must also stay invalid after rotation.
    with app.state.db() as db:
        db.add(
            BrowserSession(
                digest=digest(app.state.settings, stale_cookie),
                user_id=identity,
                csrf="csrf",
                expires_at=now() + 300,
                local_code_digest=old_hash,
            )
        )
        db.commit()
    client.cookies.set(COOKIE, stale_cookie, domain="testserver.local", path="/")
    assert client.get("/api/admin/users").status_code == 401


def test_blocked_admin_and_admin_role_are_checked(env):
    app, client, _ = env
    login(client, admin=True)
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        user.active = False
        db.commit()
    assert client.get("/api/admin/users").status_code == 401
    assert submit_code(client, "admin-code").status_code == 401
    new_code = rotate_admin_code(app.state.settings)
    assert submit_code(client, new_code).status_code == 401
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        user.active = True
        user.is_admin = False
        db.commit()
    assert submit_code(client, new_code).status_code == 401


def test_code_remains_valid_after_session_expiration(env):
    app, client, _ = env
    login(client, admin=True)
    with app.state.db() as db:
        session = db.get(BrowserSession, digest(app.state.settings, client.cookies.get(COOKIE)))
        session.expires_at = now() - 1
        db.commit()
    assert client.get("/api/admin/users").status_code == 401
    assert submit_code(client, "admin-code").status_code == 200


def test_cli_creates_named_admin_without_input_and_rotates(env):
    app, client, _ = env
    config = {
        **os.environ,
        "DATABASE_URL": app.state.settings.database_url,
        "PAPERLESS_URL": "http://paperless.test",
        "PAPERLESS_PUBLIC_URL": "https://docs.example",
        "PAPERLESS_TOKEN": "test-token",
        "SECRET_KEY": app.state.settings.secret_key.get_secret_value(),
    }
    args = ["uv", "run", "python", "-m", "searchbar.cli", "admin-code", "--name", "recovery"]
    result = subprocess.run(args, input="", capture_output=True, text=True, env=config, check=True)
    code = result.stdout.splitlines()[1]
    assert result.stdout.count(code) == 1
    assert len(code) >= 32
    assert submit_code(client, code).status_code == 200
    assert client.get("/api/auth/session").json()["name"] == "recovery"
    second = subprocess.run(args, input="", capture_output=True, text=True, env=config, check=True)
    assert second.stdout.splitlines()[1] != code
    assert submit_code(client, code).status_code == 401
    with app.state.db() as db:
        users = db.scalars(select(User).where(User.username == "recovery")).all()
        assert len(users) == 1
        assert users[0].local_code_digest != code


@pytest.mark.parametrize("name", ["", "   ", "a" * 121])
def test_invalid_internal_name_rejected(env, name):
    app, _, _ = env
    with pytest.raises(ValueError):
        rotate_admin_code(app.state.settings, name)


def test_admin_code_throttling_and_csrf(env):
    _, client, _ = env
    assert client.post("/api/auth/code", json={"code": "admin-code"}).status_code == 403
    csrf = client.get("/api/auth/session").json()["csrf"]
    for _ in range(15):
        assert (
            client.post(
                "/api/auth/code", json={"code": "invalid"}, headers={"X-CSRF-Token": csrf}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/code", json={"code": "admin-code"}, headers={"X-CSRF-Token": csrf}
        ).status_code
        == 429
    )
