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


def test_oidc_login_pending_assignment_and_block(env, provider):
    app, client, _ = env
    params = begin(client)
    token_route(provider, params)
    response = client.get(
        "/api/auth/oidc/callback",
        params={"code": "ok", "state": params["state"][0]},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/"
    session = client.get("/api/auth/session").json()
    assert session["authenticated"] and not session["has_access"] and not session["is_admin"]
    assert session["allow_download"] is False
    assert client.get("/api/documents/101").status_code == 403
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.subject == "user-123"))
        assert user.issuer == "https://idp.test"
        user.profile_id = 1
        db.commit()
    assert client.get("/api/documents/101").status_code == 200
    with app.state.db() as db:
        user = db.scalar(select(User).where(User.subject == "user-123"))
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
