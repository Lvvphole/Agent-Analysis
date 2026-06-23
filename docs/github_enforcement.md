# GitHub Enforcement

This document explains how Agent-Analysis becomes an **enforcing** PR gate on
GitHub, rather than an advisory one. It is the configuration side of Sprint 1
(Epic 1: *GitHub Merge Enforcement*).

## What the workflow does

The repository ships a single verification workflow:

- File: [`.github/workflows/Agent-Analysis-Verification.yml`](../.github/workflows/Agent-Analysis-Verification.yml)
- Trigger: `pull_request` targeting `main`
- Stable required-check name: **`agent-analysis-verification`**

Steps:

1. Checkout the PR (`fetch-depth: 0`, so the base ref is available for diffing).
2. Set up Python 3.11.
3. Install backend dev dependencies (`backend/requirements-dev.txt`).
4. Run the backend test suite: `python -m pytest -q`.
5. Run `git diff --check` against the PR base ref to reject whitespace errors
   and unresolved merge-conflict markers.

The workflow **reports** PASS/FAIL on the PR. It does **not** merge, deploy, or
force a pass. Merge remains human-controlled.

> **Note on the harness verification CLI.** Sprint 1 deliberately does *not*
> invent a fake PASS. The workflow runs the real test suite (which exercises
> every hard gate) plus `git diff --check`. A dedicated harness PR-verification
> CLI (driving `ChainExecutor` / the verifier over a candidate diff in CI) is a
> later increment; when it exists, add it as an additional step and upload the
> resulting `verifier_report.json` / evidence artifacts. Until then, do not add
> a step that asserts PASS without real evidence.

## Why a workflow alone is not enforcement

A workflow that *runs* on a PR is **advisory**. GitHub will happily let a PR
merge even while the check is failing, queued, or skipped — unless a **branch
ruleset** (or classic branch protection) is configured to *require* it. The
configuration below is what turns `agent-analysis-verification` into a gate that
blocks merge.

## Required branch ruleset for `main`

Configure under **Settings → Rules → Rulesets → New branch ruleset** (or the
classic **Settings → Branches → Branch protection rules**). Target the `main`
branch and enable:

| Rule | Setting |
| --- | --- |
| Require a pull request before merging | **On** |
| Require status checks to pass | **On** |
| → Required status check | **`agent-analysis-verification`** |
| Require branches to be up to date before merging | **On** |
| Require conversation resolution before merging | **On** |
| Restrict deletions | **On** (block deleting `main`) |
| Block force pushes | **On** |
| Bypass list | **Empty** (no actor may bypass) |

### Notes

- The required check name must match the **job name** in the workflow exactly:
  `agent-analysis-verification`. (The job `name:` — not the workflow `name:` or
  the file name — is what GitHub registers as the status check.)
- "Require branches to be up to date before merging" prevents a PASS that was
  computed against a stale base — it forces re-verification after the base moves.
- An **empty bypass list** is intentional: the whole thesis is that no actor —
  human or agent — can self-certify around the verifier.
- Do **not** enable auto-merge. Even with the check required, merge stays a
  deliberate human action.

## What this does *not* do

Consistent with the Sprint 1 non-scope, this enforcement layer introduces no
persistence, sandboxing, async workers, auth, object storage, live model
providers, auto-merge, or auto-deploy. It only makes the existing deterministic
harness a **required, blocking** status check on the PR boundary.

## Verifying the setup

After configuring the ruleset, open a test PR against `main` and confirm:

1. The `agent-analysis-verification` check appears on the PR.
2. The PR **cannot** be merged while the check is pending or failing.
3. The check passing is **necessary but not sufficient** — a human still clicks
   merge.
