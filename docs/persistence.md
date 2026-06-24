# Run Persistence (Epic 2)

Durable run and evidence persistence, added without changing any runtime
authority rule. The MVP kept run state in a process dict (`RunRegistry`); it
vanished on restart, kept no audit history, and could not scale across workers.
This layer puts all run access behind a **port** and adds a durable PostgreSQL
adapter.

> Authority is unchanged. A repository only **stores and retrieves** runs. It
> never decides PASS/FAIL/BLOCKED and never relaxes a gate — that stays with the
> verifier and the gates.

## The port

`backend/app/storage/run_repository.py` defines `RunRepository` (ABC):

| Method | Meaning |
| --- | --- |
| `add(record)` | Create/persist a run (upsert by `run_id`). |
| `save(record)` | Persist mutations to a run (upsert by `run_id`). |
| `get(run_id)` | Fetch a run, or `None`. |
| `list()` | All runs. |

> **Call `save` after mutating a record.** In-process the stored object *is* the
> record, so an in-place edit is already visible; with an out-of-process store
> (Postgres) the change is not durable until written back. The routers now call
> `save()` after every state/verifier/result mutation.

## Adapters

- **`InMemoryRunRepository`** (default) — process-local dict. Used by dev and the
  whole test suite. Exposes `.runs` and is aliased as `RunRegistry` for
  back-compat. No database required.
- **`PostgresRunRepository`** — durable store. Persists each run as an
  authoritative JSON snapshot in `runs.snapshot` (lossless round-trip via
  `run_serialization.py`) and projects queryable audit rows into
  `handler_results`, `gate_results`, and `verifier_decisions`. Reads reconstruct
  the record from the snapshot, so retrieval never depends on the projection.

## Selecting an adapter

The API binds an adapter at startup from the environment
(`app/api/store.py: configure_from_env`):

```bash
# in-memory (default — no database needed)
uvicorn app.main:app

# durable Postgres
export AGENT_ANALYSIS_DATABASE_URL=postgresql://user:pass@host:5432/agent_analysis
pip install -r backend/requirements-postgres.txt   # psycopg driver (optional dep)
uvicorn app.main:app
```

The `psycopg` driver is an **optional** dependency, imported lazily — the core
install and the test suite never need it.

## Schema

`backend/app/storage/sql/0001_init.sql` is an idempotent migration the Postgres
adapter applies on init. It defines six tables:

| Table | Purpose |
| --- | --- |
| `runs` | Authoritative run snapshot (`snapshot` JSONB) + indexed columns (`state`, `final_status`, `verifier_decision`, `tenant_id`). |
| `run_attempts` | One row per execution attempt (`base_commit`, `workspace_id`, `final_status`). Populated by Epic 3 (per-attempt isolation) — see [`workspace_isolation.md`](workspace_isolation.md). Projected from `RunRecord.attempts` via upsert, so the `evidence_artifacts.attempt_id` FK is never nulled. |
| `handler_results` | Ordered projection of `ChainExecutionResult.handler_results`. |
| `gate_results` | One row per gate result emitted by a handler. |
| `verifier_decisions` | Durable audit of the verifier's decision (who decided, same-agent ban). |
| `evidence_artifacts` | Content-addressed artifacts (`sha256`, `object_uri`, `used_as_evidence`). Populated by Epic 6; quarantined LLM narrative stays `used_as_evidence = FALSE`. |

`tenant_id` columns are present now so Epic 5 (multi-user) needs no migration to
become tenant-aware.

## Tests

`backend/tests/test_run_repository.py`:

- **Serialization** (no database) — snapshot round-trips a full and an empty
  record.
- **Repository contract** — parametrized over the in-memory adapter (always) and
  the Postgres adapter (when `AGENT_ANALYSIS_TEST_DATABASE_URL` is set): add/get
  round-trip, missing → `None`, `list`, and `save` persisting a mutation.
- **Durability / restart** (Postgres only) — a brand-new adapter instance (new
  connections, no schema re-apply) retrieves a previously saved run, proving run
  state survives a process restart.
- **Projection** (Postgres only) — saving a run writes the expected
  `handler_results`, `gate_results`, and `verifier_decisions` rows.

Run the Postgres-gated tests against any PostgreSQL:

```bash
export AGENT_ANALYSIS_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/agent_analysis_test
cd backend && python -m pytest tests/test_run_repository.py -q
```

Without that variable, the Postgres tests **skip** and the suite stays green on
the default `python -m pytest -q` (262 passed, 6 skipped).
