# Architecture

This project is a script-oriented Polymarket monitoring and copytrading system.
The reorganization keeps the original script behavior while separating code by
runtime role and trading domain.

## Top-Level Areas

- `backend/` contains data collection, strategy simulation, reporting, and
  execution workflows.
- `frontend/` contains generated user-facing views. Today this is a static
  dashboard generator rather than a long-running web application.
- `ops/` contains operator scripts. The current Windows helpers are preserved
  as legacy migration references.
- `docs/` contains security notes, data policy, architecture notes, and Codex
  Skill material.
- `examples/` contains sanitized schemas and future fixtures only.
- `scripts/` contains project-aware launch helpers.

## Backend Domains

- `common/`: shared utility code for audit repair, risk calculations,
  settlement marks, and project path helpers.
- `execution/`: anything that prepares or performs execution, including
  preflight rows, outbox routing, CLOB readiness checks, and guarded live
  executors.
- `monitors/`: long-running or repeated health and activity watchers.
- `reports/`: read-only status, PnL, exposure, risk, cohort, and backtest
  reports.
- `research/`: wallet discovery and account analysis.
- `strategies/`: simulation and signal logic, grouped by market/strategy
  family.
- `tools/`: one-off debug scripts and operator utilities.

## Runtime Model

The historical project stored runtime CSV, JSON, log, dashboard, outbox, and
receipt files at the repository root. The reorganized project keeps that model
to avoid scattering private local state through source folders.

Use `scripts/run_python.ps1` or `scripts/run_python.py` to run scripts after the
reorganization. The runner:

- changes the process working directory to the repository root,
- sets `POLY_PROJECT_ROOT`,
- prepends every backend/frontend script folder to `PYTHONPATH`,
- then invokes the requested Python script.

Many scripts still import neighboring modules by bare file name. The runner
preserves that behavior without forcing a larger package refactor.

## Live Execution Boundaries

Live execution code lives only in `backend/execution/` and remains disabled by
default. Running live paths requires credentials plus explicit real-money risk
acknowledgement environment variables. Reporting, monitoring, and simulation
paths should remain read-only unless a file name and operator command clearly
indicate execution.

