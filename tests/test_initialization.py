import os
import subprocess
import sys

from searchbar.db import Base, database
from sqlalchemy import inspect, text


def test_cli_initializes_final_schema_and_preserves_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'new.db'}"
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "SECRET_KEY": "initialization-test-key-" * 3,
        "PAPERLESS_URL": "http://paperless.test",
        "PAPERLESS_PUBLIC_URL": "http://paperless.test",
        "PAPERLESS_TOKEN": "test",
    }

    def initialize():
        subprocess.run(
            [sys.executable, "-m", "searchbar.cli", "init-db"],
            env=env,
            check=True,
            capture_output=True,
        )

    initialize()
    engine, _ = database(url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables)
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    assert {"verified_email", "paperless_user_id", "paperless_link_error"} <= user_columns
    assert "profile_id" not in user_columns
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO search_configuration VALUES (1, '[1,5]')"))
    initialize()
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT custom_field_ids FROM search_configuration")) == "[1,5]"
        )
    for table in ("users", "guest_codes"):
        column = next(c for c in inspector.get_columns(table) if c["name"] == "allow_download")
        assert not column["nullable"] and column["default"] is not None
    engine.dispose()
