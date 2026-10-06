import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy import delete, select, text
from starlette.background import BackgroundTask
from starlette.staticfiles import StaticFiles

from .config import get_settings
from .db import BrowserSession, GuestCode, Profile, User, database, now
from .paperless import Paperless, operators
from .schemas import (
    CatalogResponse,
    CodeInput,
    CodeLogin,
    DocumentResult,
    ProfileInput,
    Rules,
    Search,
    SearchResults,
    UserUpdate,
)
from .security import (
    COOKIE,
    SessionSecurity,
    access_rules,
    admin,
    digest,
    issue_session,
    principal,
    throttle,
    user_by_identity,
)


def create_app(settings=None):
    settings = settings or get_settings()
    engine, db = database(settings.database_url)
    paperless = Paperless(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await paperless.http.aclose()
        engine.dispose()

    app = FastAPI(
        title="Paperless Searchbar",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.engine = engine
    app.state.paperless = paperless
    app.add_middleware(SessionSecurity)
    oauth = OAuth()
    if settings.oidc_issuer:
        oauth.register(
            "provider",
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret.get_secret_value(),
            server_metadata_url=settings.oidc_issuer.rstrip("/")
            + "/.well-known/openid-configuration",
            client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"},
        )
    app.state.oauth = oauth

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic input echoes could otherwise expose access codes.
        errors = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail": "Ungültige Eingabe.", "errors": errors}, 422)

    @app.get("/health")
    def health():
        with db() as session:
            session.execute(text("SELECT digest FROM sessions LIMIT 1"))
        return {"status": "ok"}

    @app.get("/api/openapi.json", dependencies=[Depends(admin)])
    def openapi():
        return app.openapi()

    @app.get("/api/auth/session")
    def session_info(request: Request):
        response = JSONResponse({})
        try:
            p = principal(request)
            data = {
                "authenticated": True,
                "name": p.name,
                "is_admin": p.is_admin,
                "has_access": p.is_admin or p.profile_id is not None,
                "csrf": p.csrf,
            }
        except HTTPException:
            with db() as session:
                row = session.get(BrowserSession, request.state.sid) if request.state.sid else None
            if not row or row.user_id or row.code_id:
                row = issue_session(request, response)
            data = {"authenticated": False, "csrf": row.csrf}
        data["oidc_enabled"] = bool(settings.oidc_issuer)
        response.body = response.render(data)
        response.headers["content-length"] = str(len(response.body))
        return response

    @app.post("/api/auth/code")
    def code_login(body: CodeLogin, request: Request):
        throttle(request)
        code_digest = digest(settings, body.code.strip())
        with db() as session:
            user = session.scalar(
                select(User).where(
                    User.local_code_digest == code_digest, User.username.is_not(None)
                )
            )
            code = session.scalar(select(GuestCode).where(GuestCode.digest == code_digest))
            if user:
                if not user.active or not user.is_admin:
                    raise HTTPException(401, "Zugangscode ungültig oder abgelaufen.")
            elif not code or code.revoked or code.expires_at <= now():
                raise HTTPException(401, "Zugangscode ungültig oder abgelaufen.")
        response = JSONResponse({"ok": True})
        if user:
            # Bind the session to this credential even if a CLI rotation races the login.
            issue_session(request, response, user_id=user.id, local_code_digest=code_digest)
        else:
            issue_session(request, response, code=code)
        return response

    @app.post("/api/auth/logout")
    def logout(request: Request):
        with db() as session:
            session.execute(
                delete(BrowserSession).where(BrowserSession.digest == request.state.sid)
            )
            session.commit()
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.get("/api/auth/oidc/login")
    async def oidc_login(request: Request):
        if not settings.oidc_issuer:
            raise HTTPException(404, "OIDC ist nicht eingerichtet.")
        if not request.state.sid:
            return RedirectResponse("/login")
        throttle(request)
        try:
            return await oauth.provider.authorize_redirect(
                request, settings.app_url + "/api/auth/oidc/callback", response_mode="query"
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, "OIDC-Anbieter ist nicht erreichbar.") from exc

    @app.get("/api/auth/oidc/callback")
    async def oidc_callback(request: Request):
        if not settings.oidc_issuer or not request.state.sid:
            return RedirectResponse("/login?error=oidc")
        try:
            token = await oauth.provider.authorize_access_token(request)
            claims = token.get("userinfo")
            if (
                not token.get("id_token")
                or not claims
                or not claims.get("sub")
                or claims.get("iss") != settings.oidc_issuer
            ):
                raise ValueError("invalid identity")
            with db() as session:
                user = user_by_identity(
                    session, claims["iss"], claims["sub"], claims.get("name") or claims["sub"]
                )
                if not user.active:
                    raise ValueError("disabled")
            response = RedirectResponse("/", status_code=303)
            issue_session(request, response, user_id=user.id)
            return response
        except Exception:
            # Do not echo tokens, provider error details or callback parameters.
            request.session.clear()
            return RedirectResponse("/login?error=oidc", status_code=303)

    async def context(request, p):
        rules = access_rules(request, p)
        catalogs = await paperless.catalogs()
        try:
            await paperless.validate_rules(rules, catalogs)
        except HTTPException as exc:
            if exc.status_code in (409, 422, 404):
                raise HTTPException(
                    403, "Freigabe ungültig. Bitte Administrator kontaktieren."
                ) from exc
            raise
        return rules, catalogs

    @app.get("/api/filters", response_model=CatalogResponse)
    async def filters(request: Request, p=Depends(principal)):
        rules, catalogs = await context(request, p)
        if not p.is_admin:
            # Probe candidates through the same permission query; no unscoped facets.
            for key, attr in (
                ("storage_paths", "storage_path"),
                ("correspondents", "correspondent"),
            ):
                visible = []
                for obj in catalogs[key]:
                    result = await paperless.search(
                        Search(**{attr: obj["id"], "page_size": 1}), rules, catalogs
                    )
                    if result["count"]:
                        visible.append(obj)
                catalogs[key] = visible
            fields = []
            for field in catalogs["custom_fields"]:
                if not operators(field["data_type"]):
                    continue
                query = Search(
                    custom_fields=[{"field": field["id"], "op": "exists", "value": True}],
                    page_size=1,
                )
                if (await paperless.search(query, rules, catalogs))["count"]:
                    visible_field = dict(field)
                    if field["data_type"] == "select":
                        options = []
                        for option in (field.get("extra_data") or {}).get("select_options", []):
                            choice_query = Search(
                                custom_fields=[
                                    {"field": field["id"], "op": "exact", "value": option["id"]}
                                ],
                                page_size=1,
                            )
                            if (await paperless.search(choice_query, rules, catalogs))["count"]:
                                options.append(option)
                        visible_field["extra_data"] = {"select_options": options}
                    fields.append(visible_field)
            catalogs["custom_fields"] = fields
        return {
            "storage_paths": [
                {"id": x["id"], "name": x["name"]} for x in catalogs["storage_paths"]
            ],
            "correspondents": [
                {"id": x["id"], "name": x["name"]} for x in catalogs["correspondents"]
            ],
            "custom_fields": [
                {
                    "id": x["id"],
                    "name": x["name"],
                    "data_type": x["data_type"],
                    "operators": operators(x["data_type"]),
                    "options": (x.get("extra_data") or {}).get("select_options", []),
                }
                for x in catalogs["custom_fields"]
                if operators(x["data_type"])
            ],
        }

    @app.post("/api/documents/search", response_model=SearchResults)
    async def search_documents(body: Search, request: Request, p=Depends(principal)):
        if not body.has_filter:
            raise HTTPException(422, "Mindestens ein Suchkriterium angeben.")
        rules, catalogs = await context(request, p)
        return await paperless.search(body, rules, catalogs)

    async def authorized_document(identity, request, p):
        if identity < 1:
            raise HTTPException(404, "Dokument nicht gefunden.")
        rules, catalogs = await context(request, p)
        result = await paperless.search(Search(document_id=identity, page_size=1), rules, catalogs)
        if not result["results"]:
            raise HTTPException(404, "Dokument nicht gefunden.")
        return result["results"][0]

    @app.get("/api/documents/{identity}", response_model=DocumentResult)
    async def document(identity: int, request: Request, p=Depends(principal)):
        return await authorized_document(identity, request, p)

    @app.get("/api/documents/{identity}/{kind}")
    async def document_file(identity: int, kind: str, request: Request, p=Depends(principal)):
        if kind not in {"preview", "download"}:
            raise HTTPException(404)
        await authorized_document(identity, request, p)
        headers = {"Accept-Encoding": "identity"}
        for name in ("range", "if-range"):
            if request.headers.get(name):
                headers[name] = request.headers[name]
        try:
            upstream = await paperless.http.send(
                paperless.http.build_request(
                    "GET", f"documents/{identity}/{kind}/", headers=headers
                ),
                stream=True,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Dokumentdatei ist nicht erreichbar.") from exc
        try:
            paperless.check(upstream)
        except Exception:
            await upstream.aclose()
            raise
        response_headers = {
            k: v
            for k, v in upstream.headers.items()
            if k.lower()
            in {
                "content-length",
                "content-encoding",
                "content-range",
                "accept-ranges",
                "etag",
                "last-modified",
            }
        }
        content_type = upstream.headers.get("content-type", "application/octet-stream").split(";")[
            0
        ]
        safe_preview = kind == "preview" and content_type == "application/pdf"
        response_headers["Content-Disposition"] = (
            f'{"inline" if safe_preview else "attachment"}; filename="document-{identity}{".pdf" if content_type == "application/pdf" else ""}"'
        )
        response_headers["Content-Security-Policy"] = "sandbox"

        async def stream():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(
            stream(),
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=content_type,
            background=BackgroundTask(upstream.aclose),
        )

    @app.get("/api/admin/profiles", dependencies=[Depends(admin)])
    async def profiles():
        catalogs = await paperless.catalogs()
        with db() as session:
            rows = session.scalars(select(Profile).order_by(Profile.name)).all()
        result = []
        for row in rows:
            error = None
            try:
                await paperless.validate_rules(Rules.model_validate(row.rules), catalogs)
            except HTTPException, ValueError:
                error = "Referenzen oder Werte sind ungültig. Profil prüfen."
            result.append({"id": row.id, "name": row.name, "rules": row.rules, "error": error})
        return result

    async def save_profile(body, identity=None):
        await paperless.validate_rules(body.rules, await paperless.catalogs())
        with db() as session:
            duplicate = session.scalar(select(Profile).where(Profile.name == body.name))
            if duplicate and duplicate.id != identity:
                raise HTTPException(409, "Ein Profil mit diesem Namen existiert bereits.")
            row = session.get(Profile, identity) if identity else Profile()
            if not row:
                raise HTTPException(404)
            row.name, row.rules = body.name, body.rules.model_dump()
            session.add(row)
            session.commit()
            return {"id": row.id, "name": row.name, "rules": row.rules}

    @app.post("/api/admin/profiles", dependencies=[Depends(admin)])
    async def add_profile(body: ProfileInput):
        return await save_profile(body)

    @app.put("/api/admin/profiles/{identity}", dependencies=[Depends(admin)])
    async def edit_profile(identity: int, body: ProfileInput):
        return await save_profile(body, identity)

    @app.delete("/api/admin/profiles/{identity}", dependencies=[Depends(admin)])
    def delete_profile(identity: int):
        with db() as session:
            row = session.get(Profile, identity)
            if not row:
                raise HTTPException(404)
            if session.scalar(
                select(GuestCode.id).where(GuestCode.profile_id == identity)
            ) or session.scalar(select(User.id).where(User.profile_id == identity)):
                raise HTTPException(409, "Das Profil wird noch verwendet.")
            session.delete(row)
            session.commit()
        return {"ok": True}

    @app.get("/api/admin/users", dependencies=[Depends(admin)])
    def users():
        with db() as session:
            return [
                {
                    "id": u.id,
                    "name": u.name,
                    "active": u.active,
                    "is_admin": u.is_admin,
                    "profile_id": u.profile_id,
                    "issuer": u.issuer,
                    "subject": u.subject,
                    "local": u.username is not None,
                }
                for u in session.scalars(select(User).order_by(User.id))
            ]

    @app.put("/api/admin/users/{identity}")
    def update_user(identity: int, body: UserUpdate, p=Depends(admin)):
        with db() as session:
            user = session.get(User, identity)
            if not user:
                raise HTTPException(404)
            if identity == p.user_id and (not body.active or not body.is_admin):
                raise HTTPException(409, "Den eigenen Admin-Zugang nicht sperren oder herabstufen.")
            if user.username and not body.is_admin:
                raise HTTPException(409, "Lokale Konten sind ausschließlich Administratoren.")
            if body.profile_id and not session.get(Profile, body.profile_id):
                raise HTTPException(422, "Profil nicht gefunden.")
            user.profile_id, user.active, user.is_admin = (
                body.profile_id,
                body.active,
                body.is_admin,
            )
            session.commit()
        return {"ok": True}

    @app.get("/api/admin/codes", dependencies=[Depends(admin)])
    def codes():
        with db() as session:
            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "profile_id": c.profile_id,
                    "expires_at": c.expires_at,
                    "revoked": c.revoked,
                }
                for c in session.scalars(select(GuestCode).order_by(GuestCode.id.desc()))
            ]

    @app.post("/api/admin/codes", dependencies=[Depends(admin)])
    def add_code(body: CodeInput):
        if body.expires_at <= now():
            raise HTTPException(422, "Der Ablauf muss in der Zukunft liegen.")
        raw = secrets.token_urlsafe(24)
        with db() as session:
            if not session.get(Profile, body.profile_id):
                raise HTTPException(422, "Profil nicht gefunden.")
            row = GuestCode(**body.model_dump(), digest=digest(settings, raw))
            session.add(row)
            session.commit()
            return {"id": row.id, "code": raw}

    @app.post("/api/admin/codes/{identity}/revoke", dependencies=[Depends(admin)])
    def revoke(identity: int):
        with db() as session:
            code = session.get(GuestCode, identity)
            if not code:
                raise HTTPException(404)
            code.revoked = True
            session.commit()
        return {"ok": True}

    static = Path(settings.static_dir).resolve()
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    if (static / "pdfjs").is_dir():
        app.mount("/pdfjs", StaticFiles(directory=static / "pdfjs"), name="pdfjs")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/") or path == "api" or not (static / "index.html").is_file():
            raise HTTPException(404)
        return FileResponse(
            static / "index.html",
            headers={
                "Cache-Control": "no-cache",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
            },
        )

    return app
