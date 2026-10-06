from alembic import context
from searchbar.config import get_settings
from searchbar.db import Base, database

config = context.config
engine, _ = database(get_settings().database_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
