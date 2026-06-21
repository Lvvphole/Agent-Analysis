"""Generate the canonical JSON Schemas from the Pydantic models (Section 9/10).

The Pydantic models are the single source of truth; the ``schemas/*.schema.json``
files are derived artifacts so the frontend and external validators can consume
the same contracts. Run from anywhere::

    python backend/scripts/generate_schemas.py
"""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.checkpoint import Checkpoint
from app.schemas.evidence_ledger import EvidenceLedger
from app.schemas.run_manifest import RunManifest
from app.schemas.scrum_mapping import ScrumMapping
from app.schemas.strategic_programming import StrategicProgramming
from app.schemas.verifier_report import VerifierReport

_MODELS = {
    "run_manifest": RunManifest,
    "checkpoint": Checkpoint,
    "evidence_ledger": EvidenceLedger,
    "verifier_report": VerifierReport,
    "strategic_programming": StrategicProgramming,
    "scrum_mapping": ScrumMapping,
}


def main() -> None:
    out_dir = Path(__file__).resolve().parents[2] / "schemas"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, model in _MODELS.items():
        schema = model.model_json_schema()
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
