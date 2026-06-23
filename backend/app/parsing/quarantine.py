"""Agent-output quarantine helpers.

Raw model output and any human-readable summary are *context only*: stored and
hashed for traceability but never appended to the evidence ledger as proof
(Section 6.2 quarantine rule). These helpers route such output exclusively
through ``ChainContext.write_quarantined`` so it can never become evidence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.chains.context import ChainContext

RAW_OUTPUT_NAME = "raw_agent_output.log"
SUMMARY_NAME = "agent_summary.md"


def quarantine_agent_output(
    context: "ChainContext",
    *,
    raw_output: str,
    summary: str = "",
    recorded_by: str = "",
) -> dict[str, str]:
    """Store raw output and summary as quarantined (un-ledgered) artifacts.

    Returns a map of artifact name -> stored path. Nothing here is evidence.
    """
    raw = context.write_quarantined(
        name=RAW_OUTPUT_NAME, data=raw_output, recorded_by=recorded_by
    )
    summ = context.write_quarantined(
        name=SUMMARY_NAME, data=summary, recorded_by=recorded_by
    )
    return {RAW_OUTPUT_NAME: raw.path, SUMMARY_NAME: summ.path}
