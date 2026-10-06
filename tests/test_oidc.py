from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from joserfc import jwt
from joserfc.jwk import RSAKey
from searchbar.db import User, now
from sqlalchemy import select


@pytest.fixture
def provider():
    key = RSAKey.generate_key(2048, parameters={"kid": "test-key"})
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://idp.test/.well-known/openid-configuration").respond(
            200,
            json={
                "issuer": "https://idp.test",
                "authorization_endpoint": "https://idp.test/authorize",
                "token_endpoint": "https://idp.test/token",
                "jwks_uri": "https://idp.test/jwks",
                "response_types_supported": ["code"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
            },
        )
        mock.get("https://idp.test/jwks").respond(200, json={"keys": [key.as_dict(private=False)]})
        yield mock, key


def begin(client):
    client.get("/api/auth/session")
    response = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert response.status_code == 302, response.text
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://testserver/api/auth/oidc/callback"]
    assert params["nonce"]
    return params


def token_route(provider, params, **changes):
    mock, key = provider
    claims = {
        "iss": "https://idp.test",
        "sub": "user-123",
        "aud": "searchbar",
        "exp": now() + 300,
        "iat": now(),
        "nonce": params["nonce"][0],
        "name": "Anna",
        "email": "anna@example.com",
        "groups": ["admins"],
    }
    claims.update(changes)
    encoded = jwt.encode({"alg": "RS256", "kid": "test-key"}, claims, key)

    def token(request):
        form = parse_qs(request.content.decode())
        assert len(form["code_verifier"][0]) >= 43
        return httpx.Response(
            200, json={"access_token": "access", "token_type": "Bearer", "id_token": encoded}
        )

    mock.post("https://idp.test/token").mock(side_effect=token)


def oidc_login(client, provider, **claims):
    params = begin(client)
    token_route(provider, params, **claims)
    response = client.get(
        "/api/auth/oidc/callback",
        params={"code": "ok", "state": params["state"][0]},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/"
    session = client.get("/api/auth/session").json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    return session


def test_oidc_login_paperless_access_and_local_block(env, provider):
    app, client, _ = env
    session = oidc_login(client, provider)
    assert session["authenticated"] and session["has_access"] and not session["is_admin"]
    assert session["allow_download"] is False
    assert client.get("/api/documents/101").status_code == 200
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.subject == "user-123"))
        assert user.issuer == "https://idp.test"
        assert user.paperless_user_id == 11
        user.active = False
        db.commit()
    assert client.get("/api/documents/101").status_code == 401


@pytest.mark.parametrize(
    "change", [{"nonce": "wrong"}, {"aud": "other-app"}, {"iss": "https://evil.test"}, {"exp": 1}]
)
def test_oidc_invalid_claims_rejected(env, provider, change):
    _, client, _ = env
    params = begin(client)
    token_route(provider, params, **change)
    response = client.get(
        "/api/auth/oidc/callback",
        params={"code": "ok", "state": params["state"][0]},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/login?error=oidc"
    assert not client.get("/api/auth/session").json()["authenticated"]


def test_oidc_wrong_state_and_replay_rejected(env, provider):
    _, client, _ = env
    params = begin(client)
    token_route(provider, params)
    response = client.get("/api/auth/oidc/callback?code=ok&state=wrong", follow_redirects=False)
    assert response.headers["location"] == "/login?error=oidc"
    assert not client.get("/api/auth/session").json()["authenticated"]


def test_secure_cookies_and_public_redirect(env):
    app, client, _ = env
    app.state.settings.app_url = "https://search.example"
    response = client.get("/api/auth/session")
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]


@pytest.mark.parametrize(
    "claims",
    [
        {"email": None},
        {"email": ""},
        {"email": "missing@example.com"},
        {"email": "keine-email"},
        {"email": 123},
        {"email": "a" * 255 + "@example.com"},
    ],
)
def test_oidc_without_unique_email_has_no_access(env, provider, claims):
    _, client, fake = env
    session = oidc_login(client, provider, **claims)
    assert session["authenticated"] and not session["has_access"]
    assert session["access_error"]
    for suffix in ("", "/preview", "/thumb", "/download"):
        assert client.get("/api/documents/101" + suffix).status_code == 403
    assert not any(r.url.path.startswith("/api/documents/") for r in fake.calls)


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"email_verified": True},
        {"email_verified": False},
        {"email_verified": None},
        {"email_verified": "true"},
    ],
)
def test_oidc_email_verification_claim_is_not_required(env, provider, claims):
    app, client, _ = env
    session = oidc_login(client, provider, email=" ANNA@EXAMPLE.COM ", **claims)
    assert session["authenticated"] and session["has_access"]
    assert session["access_error"] is None
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.subject == "user-123"))
        assert user.verified_email == "anna@example.com"
        assert user.paperless_user_id == 11
    assert client.get("/api/documents/101").status_code == 200
    assert client.get("/api/documents/202").status_code == 404


def test_email_lookup_paginates_and_rejects_duplicates(env, provider):
    _, client, fake = env
    anna = fake.users[0].copy()
    fake.users = [{**anna, "id": i + 100, "email": f"user{i}@example.com"} for i in range(100)] + [
        anna
    ]
    assert oidc_login(client, provider, email=" ANNA@EXAMPLE.COM ")["has_access"]
    assert any(r.url.params.get("page") == "2" for r in fake.calls)
    assert all(r.url.host == "paperless.test" for r in fake.calls)
    fake.users.append({**anna, "id": 12, "email": "ANNA@example.com"})
    assert not oidc_login(client, provider)["has_access"]
    assert client.get("/api/documents/101").status_code == 403


@pytest.mark.parametrize("change", ["inactive", "deleted", "email", "model_permission"])
def test_paperless_account_changes_apply_to_live_session(env, provider, change):
    _, client, fake = env
    assert oidc_login(client, provider)["has_access"]
    if change == "inactive":
        fake.users[0]["is_active"] = False
    elif change == "deleted":
        fake.users.clear()
    elif change == "email":
        fake.users[0]["email"] = "changed@example.com"
    else:
        fake.users[0]["inherited_permissions"] = []
    session = client.get("/api/auth/session").json()
    assert session["authenticated"] and not session["has_access"]
    assert session["access_error"]
    assert client.get("/api/documents/101").status_code == 403


@pytest.mark.parametrize("permission", ["group", "direct", "owner", "unowned", "superuser"])
def test_paperless_document_permissions_all_endpoints(env, provider, permission):
    _, client, fake = env
    perms = fake.permissions[101]
    perms["groups"] = []
    if permission == "group":
        perms["groups"] = [7]
    elif permission == "direct":
        perms["users"] = [11]
    elif permission == "owner":
        perms["owner"] = 11
    elif permission == "unowned":
        perms["owner"] = None
    else:
        fake.users[0]["is_superuser"] = True
    assert oidc_login(client, provider)["has_access"]
    for suffix in ("", "/preview", "/thumb"):
        assert client.get("/api/documents/101" + suffix).status_code == 200
    assert client.get("/api/documents/101/download").status_code == 403
    for request in fake.calls:
        if request.url.path.startswith("/api/documents/"):
            assert request.headers["remote-user"] == "anna"
            assert "authorization" not in request.headers
        else:
            assert "remote-user" not in request.headers


def test_group_revocation_and_local_admin_do_not_bypass_paperless(env, provider):
    app, client, fake = env
    oidc_login(client, provider)
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.subject == "user-123"))
        user.is_admin = True
        user.allow_download = True
        db.commit()
    assert client.get("/api/documents/101/download").status_code == 200
    for suffix in ("", "/preview", "/thumb", "/download"):
        assert client.get("/api/documents/202" + suffix).status_code == 404
    fake.users[0]["groups"] = []
    for suffix in ("", "/preview", "/thumb", "/download"):
        assert client.get("/api/documents/101" + suffix).status_code == 404
    assert client.get("/api/admin/users").status_code == 200


def test_search_paginates_in_paperless_and_catalogs_are_not_user_filtered(env, provider):
    _, client, fake = env
    oidc_login(client, provider)
    fake.permissions[303]["users"] = [11]
    fake.calls.clear()
    for page, expected in [(1, 303), (2, 101)]:
        result = client.post(
            "/api/documents/search", json={"storage_path": 1, "page": page, "page_size": 1}
        )
        assert result.status_code == 200
        assert result.json()["count"] == 2
        assert [d["id"] for d in result.json()["results"]] == [expected]
    calls = [r for r in fake.calls if r.url.path == "/api/documents/"]
    assert len(calls) == 2
    assert [r.url.params["page"] for r in calls] == ["1", "2"]
    fake.calls.clear()
    catalog = client.get("/api/filters").json()
    assert [p["id"] for p in catalog["storage_paths"]] == [1, 2]
    assert not any(r.url.path.startswith("/api/documents/") for r in fake.calls)


@pytest.mark.parametrize("status", [401, 403, 500])
def test_remote_failure_never_falls_back_to_service_token(env, provider, status):
    _, client, fake = env
    oidc_login(client, provider)
    fake.remote_error = status
    fake.calls.clear()
    response = client.post("/api/documents/search", json={"document_id": 101})
    assert response.status_code == (403 if status != 500 else 502)
    calls = [r for r in fake.calls if r.url.path.startswith("/api/documents/")]
    assert len(calls) == 1 and calls[0].headers["remote-user"] == "anna"


def test_file_rechecks_permission_and_closes_remote_client(env, provider, monkeypatch):
    app, client, fake = env
    oidc_login(client, provider)
    remote_clients = []
    factory = app.state.paperless.for_user

    def tracked(username):
        remote = factory(username)
        remote_clients.append(remote.http)
        return remote

    monkeypatch.setattr(app.state.paperless, "for_user", tracked)
    response = client.get(
        "/api/documents/101/preview",
        headers={"Range": "bytes=0-0", "Remote-User": "other", "Authorization": "Token other"},
    )
    assert response.status_code == 206 and response.content == b"%"
    assert all(c.is_closed for c in remote_clients)

    def revoked_on_file(request):
        if request.url.path.endswith("/preview/"):
            fake.permissions[101]["groups"] = []
        return fake.handle(request)

    app.state.paperless.remote_transport = httpx.MockTransport(revoked_on_file)
    assert client.get("/api/documents/101/preview").status_code == 404
    assert all(c.is_closed for c in remote_clients)


@pytest.mark.asyncio
async def test_concurrent_users_have_isolated_headers_and_cookie_jars(env):
    import asyncio

    from searchbar.db import BrowserSession
    from searchbar.security import COOKIE, digest

    app, _, fake = env
    fake.users.append(
        {**fake.users[0], "id": 12, "username": "bob", "email": "bob@example.com", "groups": [8]}
    )
    tokens = []
    with app.state.db() as db:
        for upstream in fake.users:
            user = User(
                name=upstream["username"],
                issuer="https://idp.test",
                subject=upstream["username"],
                verified_email=upstream["email"],
                paperless_user_id=upstream["id"],
            )
            db.add(user)
            db.flush()
            token = "test-session-" + upstream["username"]
            tokens.append(token)
            db.add(
                BrowserSession(
                    digest=digest(app.state.settings, token),
                    user_id=user.id,
                    csrf="csrf",
                    expires_at=now() + 300,
                    oauth={},
                )
            )
        db.commit()

    async def cookie_response(request):
        await asyncio.sleep(0)
        username = request.headers["remote-user"]
        cookie = request.headers.get("cookie", "")
        assert not cookie or cookie == f"paperless_session={username}"
        response = fake.handle(request)
        response.headers["set-cookie"] = f"paperless_session={username}; Path=/"
        return response

    app.state.paperless.remote_transport = httpx.MockTransport(cookie_response)

    async def access(token, allowed, denied):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            cookies={COOKIE: token, "paperless_session": "browser-forgery"},
        ) as client:
            for _ in range(2):
                response = await client.get(f"/api/documents/{allowed}/preview")
                assert response.status_code == 200 and response.content.startswith(b"%PDF")
                assert "set-cookie" not in response.headers
                assert (await client.get(f"/api/documents/{denied}")).status_code == 404

    await asyncio.gather(access(tokens[0], 101, 202), access(tokens[1], 202, 101))


def test_oidc_profile_assignment_is_no_longer_an_api_field(env):
    from conftest import login

    _, client, _ = env
    login(client, admin=True)
    response = client.put(
        "/api/admin/users/1", json={"active": True, "is_admin": True, "profile_id": 1}
    )
    assert response.status_code == 422


def test_custom_remote_user_header_for_search_details_and_streams(env, provider):
    app, client, fake = env
    app.state.settings.paperless_http_remote_user_header_name = "HTTP_X_AUTH_USER"
    fake.remote_header = "X-Auth-User"
    oidc_login(client, provider)
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.subject == "user-123"))
        user.allow_download = True
        db.commit()
    # Neither header supplied by the browser may override the linked identity.
    client.headers.update({"Remote-User": "forged", "X-Auth-User": "forged"})
    fake.calls.clear()
    response = client.post("/api/documents/search", json={"document_id": 101})
    assert response.status_code == 200 and response.json()["count"] == 1
    for suffix in ("", "/preview", "/thumb", "/download"):
        assert client.get("/api/documents/101" + suffix).status_code == 200
        assert client.get("/api/documents/202" + suffix).status_code == 404
    response = client.get("/api/documents/101/preview", headers={"Range": "bytes=0-0"})
    assert response.status_code == 206 and response.content == b"%"
    for request in fake.calls:
        assert "remote-user" not in request.headers
        if request.url.path.startswith("/api/documents/"):
            assert request.headers["x-auth-user"] == "anna"
            assert "authorization" not in request.headers
        else:
            assert "x-auth-user" not in request.headers
            assert request.headers["authorization"] == "Token test-token"
