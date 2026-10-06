import os
import subprocess

import pytest
from searchbar.db import database
from sqlalchemy import MetaData, inspect, text


@pytest.mark.parametrize("existing", [False, True])
def test_migrate_new_and_existing_database(tmp_path, existing):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "SECRET_KEY": "migration-test-key-" * 3,
        "PAPERLESS_URL": "http://paperless.test",
        "PAPERLESS_PUBLIC_URL": "http://paperless.test",
        "PAPERLESS_TOKEN": "test",
    }
    if existing:
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "a19c7e2f4b01"],
            env=env,
            check=True,
            capture_output=True,
        )
        engine, _ = database(url)
        metadata = MetaData()
        metadata.reflect(bind=engine)
        with engine.begin() as conn:
            conn.execute(
                metadata.tables["profiles"].insert(),
                {"id": 1, "name": "Existing", "rules": {"all_documents": True}},
            )
            conn.execute(
                metadata.tables["users"].insert(),
                {
                    "id": 1,
                    "name": "Admin",
                    "username": "admin",
                    "local_code_digest": "existing-admin-digest",
                    "active": True,
                    "is_admin": True,
                },
            )
            conn.execute(
                metadata.tables["guest_codes"].insert(),
                {
                    "id": 1,
                    "name": "Guest",
                    "digest": "existing-guest-digest",
                    "profile_id": 1,
                    "expires_at": 9999999999,
                    "revoked": False,
                },
            )
            conn.execute(
                metadata.tables["sessions"].insert(),
                {
                    "digest": "existing-session",
                    "csrf": "existing-csrf",
                    "code_id": 1,
                    "expires_at": 9999999999,
                    "oauth": {},
                },
            )
        engine.dispose()
    for _ in range(2):
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"], env=env, check=True, capture_output=True
        )
    engine, _ = database(url)
    assert {
        "profiles",
        "users",
        "guest_codes",
        "sessions",
        "login_attempts",
        "search_configuration",
    } <= set(inspect(engine).get_table_names())
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "local_code_digest" in columns
    assert "password_hash" not in columns
    assert "local_code_digest" in {
        column["name"] for column in inspect(engine).get_columns("sessions")
    }
    for table in ("users", "guest_codes"):
        column = next(
            c for c in inspect(engine).get_columns(table) if c["name"] == "allow_download"
        )
        assert not column["nullable"]
        assert column["default"] is not None
    if existing:
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT allow_download FROM users WHERE id=1")) == 0
            assert conn.scalar(text("SELECT allow_download FROM guest_codes WHERE id=1")) == 0
            assert (
                conn.scalar(text("SELECT local_code_digest FROM users WHERE id=1"))
                == "existing-admin-digest"
            )
            assert (
                conn.scalar(text("SELECT digest FROM guest_codes WHERE id=1"))
                == "existing-guest-digest"
            )
            assert (
                conn.scalar(text("SELECT code_id FROM sessions WHERE digest='existing-session'"))
                == 1
            )
    engine.dispose()
