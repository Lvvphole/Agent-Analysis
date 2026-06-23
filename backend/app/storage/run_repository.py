"""Run persistence port + the in-memory (dev/test) adapter.

Epic 2 (Durable Run and Evidence Persistence) replaces the MVP's in-memory
dict-of-runs with a durable store. To make that swap contained and reviewable,
all run access goes through one **port** — :class:`RunRepository` — and the API
selects an adapter at startup. Nothing in the routers knows whether runs live in
a process dict or in Postgres.

This module ships the port and the in-memory adapter. The Postgres adapter lives
in ``postgres_run_repository`` and is imported lazily (only when configured) so
the core install never needs a database driver.

Authority note: a repository only *stores and retrieves* runs. It never decides
PASS/FAIL/BLOCKED and never relaxes a gate — that stays with the verifier and
the gates, exactly as before.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.storage.run_records import RunRecord


class RunRepository(ABC):
    """The port every run store implements.

    ``add`` and ``save`` are both upserts keyed by ``run_id``; ``add`` reads as
    "create" and ``save`` as "persist mutations", but an adapter may implement
    them identically. Callers must ``save`` a record after mutating it: with an
    out-of-process store (Postgres) an in-place mutation is not durable until it
    is written back.
    """

    @abstractmethod
    def add(self, record: RunRecord) -> None: ...

    @abstractmethod
    def save(self, record: RunRecord) -> None: ...

    @abstractmethod
    def get(self, run_id: str) -> RunRecord | None: ...

    @abstractmethod
    def list(self) -> list[RunRecord]: ...


class InMemoryRunRepository(RunRepository):
    """Process-local store. The default for dev and the whole test suite.

    Keeps a public ``runs`` dict because existing tests reset state between
    cases with ``registry.runs.clear()``.
    """

    def __init__(self) -> None:
        self.runs: dict[str, RunRecord] = {}

    def add(self, record: RunRecord) -> None:
        self.runs[record.run_id] = record

    def save(self, record: RunRecord) -> None:
        # The stored object is the same reference, so in-place mutations are
        # already visible; re-binding by id keeps add/save interchangeable.
        self.runs[record.run_id] = record

    def get(self, run_id: str) -> RunRecord | None:
        return self.runs.get(run_id)

    def list(self) -> list[RunRecord]:
        return list(self.runs.values())


# Back-compat alias: the MVP called the in-memory store ``RunRegistry``.
RunRegistry = InMemoryRunRepository
