import copy
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .db import BrowserSession, GuestCode, LoginAttempt, Profile, User, now
from .schemas import Rules

COOKIE = "searchbar_session"


def digest(settings, value: str):
    return hmac.new(
        settings.secret_key.get_secret_value().encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def issue_session(request, response, user_id=None, code=None, local_code_digest=None):
    token = secrets.token_urlsafe(32)
    expires = min(now() + 12 * 3600, code.expires_at if code else now() + 12 * 3600)
    with request.app.state.db() as db:
        if old := getattr(request.state, "sid", None):
            db.execute(delete(BrowserSession).where(BrowserSession.digest == old))
        db.execute(delete(BrowserSession).where(BrowserSession.expires_at <= now()))
        row = BrowserSession(
            digest=digest(request.app.state.settings, token),
            csrf=secrets.token_urlsafe(32),
            user_id=user_id,
            code_id=code.id if code else None,
            expires_at=expires,
            oauth={},
            local_code_digest=local_code_digest,
        )
        db.add(row)
        db.commit()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=request.app.state.settings.secure_cookie,
        samesite="lax",
        max_age=expires - now(),
        path="/",
    )
    return row


class SessionSecurity(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        settings = request.app.state.settings
        sid = digest(settings, request.cookies.get(COOKIE, ""))
        with request.app.state.db() as db:
            row = db.get(BrowserSession, sid)
            if row and row.expires_at <= now():
                db.delete(row)
                db.commit()
                row = None
        request.state.sid = sid if row else None
        request.scope["session"] = copy.deepcopy(row.oauth or {}) if row else {}
        before = copy.deepcopy(request.scope["session"])
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if (
                not row
                or not hmac.compare_digest(row.csrf, request.headers.get("x-csrf-token", ""))
                or (origin and origin != settings.app_url)
            ):
                return JSONResponse(
                    {"detail": "Sicherheitsprüfung fehlgeschlagen. Seite neu laden."},
                    403,
                    headers={"Cache-Control": "no-store"},
                )
        response = await call_next(request)
        if row and request.scope["session"] != before:
            with request.app.state.db() as db:
                current = db.get(BrowserSession, sid)
                if current:
                    current.oauth = request.scope["session"]
                    db.commit()
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response


@dataclass
class Principal:
    name: str
    is_admin: bool
    profile_id: int | None
    csrf: str
    user_id: int | None = None
    allow_download: bool = False


def principal(request: Request) -> Principal:
    with request.app.state.db() as db:
        row = db.get(BrowserSession, request.state.sid) if request.state.sid else None
        if not row or row.expires_at <= now():
            raise HTTPException(401, "Bitte anmelden.")
        if row.user_id:
            user = db.get(User, row.user_id)
            if user and user.active:
                if user.username is not None and (
                    not user.is_admin
                    or not row.local_code_digest
                    or not user.local_code_digest
                    or not hmac.compare_digest(row.local_code_digest, user.local_code_digest)
                ):
                    raise HTTPException(401, "Sitzung abgelaufen oder Zugang gesperrt.")
                return Principal(
                    user.name,
                    user.is_admin,
                    user.profile_id,
                    row.csrf,
                    user.id,
                    allow_download=user.allow_download,
                )
        elif row.code_id:
            code = db.get(GuestCode, row.code_id)
            if code and not code.revoked and code.expires_at > now():
                return Principal(
                    code.name, False, code.profile_id, row.csrf, allow_download=code.allow_download
                )
    raise HTTPException(401, "Sitzung abgelaufen oder Zugang gesperrt.")


def admin(request: Request):
    p = principal(request)
    if not p.is_admin:
        raise HTTPException(403, "Administratorrechte erforderlich.")
    return p


def access_rules(request: Request, p: Principal) -> Rules:
    if p.is_admin:
        return Rules(all_documents=True)
    with request.app.state.db() as db:
        profile = db.get(Profile, p.profile_id) if p.profile_id else None
        if not profile:
            raise HTTPException(
                403, "Dein Zugang wartet auf eine Freigabe durch einen Administrator."
            )
        try:
            return Rules.model_validate(profile.rules)
        except ValueError as exc:
            raise HTTPException(
                403, "Die Freigabe ist ungültig. Bitte Administrator kontaktieren."
            ) from exc


def throttle(request: Request):
    key = digest(
        request.app.state.settings,
        "login:" + (request.client.host if request.client else "unknown"),
    )
    with request.app.state.db() as db:
        db.execute(delete(LoginAttempt).where(LoginAttempt.until <= now()))
        stmt = insert(LoginAttempt).values(key=key, count=1, until=now() + 300)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[LoginAttempt.key], set_={"count": LoginAttempt.count + 1}
            )
        )
        db.commit()
        row = db.get(LoginAttempt, key)
        if row.count > 15:
            raise HTTPException(
                429,
                "Zu viele Anmeldeversuche. Bitte fünf Minuten warten.",
                headers={"Retry-After": "300"},
            )


def user_by_identity(db, issuer: str, subject: str, name: str):
    user = db.scalar(select(User).where(User.issuer == issuer, User.subject == subject))
    if not user:
        # Ignore IdP role/group/email claims for authorization and account linking.
        user = User(issuer=issuer, subject=subject, name=name[:200], is_admin=False, active=True)
        db.add(user)
        db.commit()
    return user
