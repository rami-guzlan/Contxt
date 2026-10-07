"""Alembic environment. Runs with a connection handed in by `workspace_core.db.migrate`, or
with the URL in the config (offline SQL previews, `python -m alembic` during development)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from workspace_core.db.schema import metadata

config = context.config
target_metadata = metadata


def run_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        context.run_migrations()
        return
    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
