"""Run store selection for the control API.

The run state lives behind a port (:class:`RunRepository`); this module owns the
*active* adapter the routers use. The default is the in-memory adapter (dev and
the whole test suite). Set ``AGENT_ANALYSIS_DATABASE_URL`` to bind the durable
Postgres adapter instead (see ``configure_from_env``).

Back-compat: ``RunRecord``, ``RunRegistry`` and the ``registry`` singleton are
re-exported so existing imports and ``registry.runs.clear()`` keep working — the
default active repository *is* that in-memory ``registry`` instance.
"""

from __future__ import annotations

import os

from app.storage.run_records import RunRecord
from app.storage.run_repository import (
    InMemoryRunRepository,
    RunRegistry,
    RunRepository,
)

__all__ = [
    "RunRecord",
    "RunRegistry",
    "RunRepository",
    "registry",
    "get_repository",
    "set_repository",
    "reset_repository",
    "configure_from_env",
]

# Default in-memory store. Kept as a module-level singleton for back-compat.
registry: InMemoryRunRepository = InMemoryRunRepository()

_active: RunRepository = registry


def get_repository() -> RunRepository:
    """Return the active run repository the routers should use."""
    return _active


def set_repository(repo: RunRepository) -> None:
    """Bind a specific repository adapter (used at startup and in tests)."""
    global _active
    _active = repo


def reset_repository() -> None:
    """Restore the default in-memory repository."""
    global _active
    _active = registry


def configure_from_env() -> RunRepository:
    """Select the adapter from the environment.

    ``AGENT_ANALYSIS_DATABASE_URL`` set -> durable Postgres adapter; otherwise the
    in-memory adapter. Importing the Postgres adapter is deferred so the core
    install never needs a database driver.
    """
    dsn = os.environ.get("AGENT_ANALYSIS_DATABASE_URL")
    if dsn:
        from app.storage.postgres_run_repository import PostgresRunRepository

        set_repository(PostgresRunRepository(dsn))
    else:
        reset_repository()
    return get_repository()
