import os
import subprocess

from searchbar.db import database
from sqlalchemy import inspect


def test_migrate_new_and_existing_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "SECRET_KEY": "migration-test-key-" * 3,
        "PAPERLESS_URL": "http://paperless.test",
        "PAPERLESS_PUBLIC_URL": "http://paperless.test",
        "PAPERLESS_TOKEN": "test",
    }
    for _ in range(2):
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"], env=env, check=True, capture_output=True
        )
    engine, _ = database(url)
    assert {"profiles", "users", "guest_codes", "sessions", "login_attempts"} <= set(
        inspect(engine).get_table_names()
    )
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "local_code_digest" in columns
    assert "password_hash" not in columns
    assert "local_code_digest" in {
        column["name"] for column in inspect(engine).get_columns("sessions")
    }
    engine.dispose()
