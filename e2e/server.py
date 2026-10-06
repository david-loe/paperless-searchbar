"""Test-only application with isolated storage, Paperless fixtures and a local OIDC provider.

Not included in the runtime image. Never import this module from production code.
"""

import base64
import hashlib
import os
import secrets
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from joserfc import jwt
from joserfc.jwk import RSAKey
from searchbar.app import create_app
from searchbar.config import Settings
from searchbar.db import Base, GuestCode, Profile, User, now
from searchbar.schemas import Rules
from searchbar.security import digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from conftest import FakePaperless  # noqa: E402


def create_test_app():
    directory = tempfile.TemporaryDirectory(prefix="searchbar-e2e-")
    origin = f"http://127.0.0.1:{int(os.environ.get('SEARCHBAR_E2E_PORT', '18765'))}"
    settings = Settings(
        database_url=f"sqlite:///{directory.name}/test.db",
        app_url=origin,
        paperless_url="http://paperless.test",
        paperless_public_url="https://docs.example",
        paperless_token="test-token",
        secret_key="e2e-test-only-secret-" * 3,
        oidc_issuer=origin + "/test-idp",
        oidc_client_id="test",
        oidc_client_secret="test-secret",
    )
    app = create_app(settings)
    app.state.temp_directory = directory
    Base.metadata.create_all(app.state.engine)
    fake = FakePaperless()
    app.state.paperless.http = httpx.AsyncClient(
        base_url="http://paperless.test/api/",
        headers={"Authorization": "Token test-token"},
        transport=httpx.MockTransport(fake.handle),
    )
    with app.state.db() as db:
        profile = Profile(
            name="Firma A",
            rules=Rules(
                storage_paths=[1], custom_fields=[{"field": 1, "op": "exact", "value": "A"}]
            ).model_dump(),
        )
        db.add(profile)
        db.flush()
        db.add(
            User(
                name="Admin",
                username="admin",
                local_code_digest=digest(settings, "e2e-admin-code"),
                active=True,
                is_admin=True,
            )
        )
        db.add(
            GuestCode(
                name="Gastzugang",
                digest=digest(settings, "e2e-guest-code"),
                profile_id=profile.id,
                expires_at=now() + 3600,
            )
        )
        db.commit()
    key = RSAKey.generate_key(2048, parameters={"kid": "e2e"})
    codes = {}
    issuer = settings.oidc_issuer

    # Insert test routes before the production SPA catch-all.
    spa = app.router.routes.pop()

    @app.get("/test-idp/.well-known/openid-configuration")
    def discovery():
        return {
            "issuer": issuer,
            "authorization_endpoint": issuer + "/authorize",
            "token_endpoint": issuer + "/token",
            "jwks_uri": issuer + "/jwks",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    @app.get("/test-idp/jwks")
    def jwks():
        return {"keys": [key.as_dict(private=False)]}

    @app.get("/test-idp/authorize")
    def authorize(request: Request):
        params = dict(request.query_params)
        code = secrets.token_urlsafe(24)
        codes[code] = params
        return RedirectResponse(
            params["redirect_uri"] + "?" + urlencode({"code": code, "state": params["state"]})
        )

    @app.post("/test-idp/token")
    async def token(request: Request):
        params = parse_qs((await request.body()).decode())
        original = codes.pop(params.get("code", [""])[0], None)
        verifier = params.get("code_verifier", [""])[0]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        if not original or original["code_challenge"] != challenge:
            return JSONResponse({"error": "invalid_grant"}, 400)
        claims = {
            "iss": issuer,
            "sub": "anna",
            "aud": "test",
            "iat": now(),
            "exp": now() + 300,
            "nonce": original["nonce"],
            "name": "Anna Beispiel",
        }
        return {
            "access_token": secrets.token_urlsafe(24),
            "token_type": "Bearer",
            "id_token": jwt.encode({"alg": "RS256", "kid": "e2e"}, claims, key),
        }

    app.router.routes.append(spa)
    return app
