import argparse
import secrets

from sqlalchemy import delete, select

from .config import Settings, get_settings
from .db import BrowserSession, User, database
from .security import digest


def rotate_admin_code(settings: Settings, name: str = "admin") -> str:
    """Issue a permanent local credential; plaintext is returned only to the CLI caller."""
    name = name.strip()
    if not name or len(name) > 120:
        raise ValueError("Die interne Admin-Kennung muss zwischen 1 und 120 Zeichen lang sein.")
    raw = secrets.token_urlsafe(32)
    engine, factory = database(settings.database_url)
    try:
        with factory() as db:
            user = db.scalar(select(User).where(User.username == name))
            if user is None:
                user = User(username=name, name=name, active=True)
                db.add(user)
            elif user.issuer is not None or user.subject is not None:
                raise ValueError("OIDC-Benutzer können keinen lokalen Admin-Code erhalten.")
            user.local_code_digest = digest(settings, raw)
            user.is_admin = True
            # Preserve explicit account blocks; rotating a credential does not unblock it.
            if user.id:
                db.execute(delete(BrowserSession).where(BrowserSession.user_id == user.id))
            db.commit()
    finally:
        engine.dispose()
    return raw


def main():
    parser = argparse.ArgumentParser(description="Lokalen Admin-Code erzeugen oder ersetzen")
    parser.add_argument("command", choices=["admin-code"])
    parser.add_argument("--name", default="admin", help="Interne Admin-Kennung (Standard: admin)")
    args = parser.parse_args()
    try:
        code = rotate_admin_code(get_settings(), args.name)
    except ValueError as exc:
        parser.error(str(exc))
    print("Neuer Admin-Zugangscode (wird nur einmal angezeigt):")
    print(code)
    print("Bis zum Ersetzen gültig. Alte Codes und Sitzungen dieses Administrators sind ungültig.")


if __name__ == "__main__":
    main()
