# Agent-Analysis Frontend (Phase 6 — planned)

The frontend is the **control plane**: it displays run state, evidence, and gate
status, and submits *requested* actions. It is **not** the source of truth and
is intentionally not yet implemented in this slice.

## Authority rules (must hold when built)

The frontend **may** display state, evidence, and gate status; stream logs; show
disabled controls; and submit requested actions.

The frontend **may not**, and these controls must never be built:

- Merge button
- Deploy button
- Mark-complete button
- Force-pass button
- Bypass-verifier button
- Freeform agent chat as the primary workflow
- Definition-of-Done editing during an active run

`PASS` is decided only by the independent verifier; merge/deploy live outside
this loop. The backend enforces every hard gate regardless of the UI.

## Planned stack (Section 5.1)

Next.js App Router · React · TypeScript · Tailwind · shadcn/ui · TanStack Query
· Zod · React Hook Form · React Flow · SSE/WebSockets for live run logs.

## Planned screens (Section 16.1)

Project Console · Run Manifest Builder · State Machine Timeline · Codebase
AI-Readiness Dashboard · Evidence Ledger Viewer · Strategic Programming Review
Panel · Agent Invocation Screen · Diff & Test Viewer · Verifier Workbench ·
Backlog Converter · PR Gate Panel.

The canonical JSON contracts the UI will consume are generated to
`../schemas/*.schema.json` from the backend Pydantic models.
