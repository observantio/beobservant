<div align="center">

# Observantio Test & Quality Guide

  <img src="../assets/strike.png" alt="Observantio test and quality guide" width="150" />

  <p>
    <img src="https://img.shields.io/badge/Services%20covered-Watchdog%20%7C%20Gatekeeper%20%7C%20Notifier%20%7C%20Resolver-1f2937?style=flat-square" alt="Services covered" />
    <img src="https://img.shields.io/badge/Contract%20testing-Schemathesis-0f766e?style=flat-square" alt="Schemathesis" />
    <img src="https://img.shields.io/badge/Gates-pytest%20%7C%20mypy%20%7C%20pylint-0ea5e9?style=flat-square" alt="Quality gates" />
  </p>
</div>

This README explains how testing and quality gates are organized in this workspace, what each layer validates, and how to run everything consistently as a developer.

## What Lives In `tests/`

The `tests/` folder at repo root is an OTEL traffic harness, not the primary unit-test location.

- `tests/traces.py`: emits sample trace traffic.
- `tests/logs.py`: emits sample log traffic.
- `tests/configs/otel-agent.yaml`: collector config for local ingest testing.
- `tests/configs/grafana-high-cpu-systems-otel.json`: sample dashboard config artifact.

Unit tests for backend services live inside each service directory:

- `watchdog/tests`
- `gatekeeper/tests`
- `notifier/tests`
- `resolver/tests`

## Current Unit-Test Inventory

Based on current `test_*.py` files and `def test_` functions:

| Service | Test Files | Test Functions |
| --- | ---: | ---: |
| `watchdog` | 111 | 344 |
| `gatekeeper` | 7 | 52 |
| `notifier` | 48 | 142 |
| `resolver` | 59 | 167 |
| **Total** | **225** | **705** |

## Coverage & Pytest Reports

Use the global pytest script:

```bash
scripts/run_global_pytests.sh
```

What it does:

- Runs pytest for `resolver`, `gatekeeper`, `notifier`, and `watchdog`.
- Produces per-service JUnit XML in `test-reports/junit/`.
- Produces per-service coverage XML + HTML under `test-reports/coverage/`.
- Combines coverage into a global report:
  - `test-reports/coverage/coverage.xml`
  - `test-reports/coverage/html/index.html`

Important detail:

- `COVERAGE_THRESHOLD` is configurable (defaults to `0` in `run_global_pytests.sh`).
- CI enforces stricter gates for selected components (see below).

## Global Static Quality Scripts

Run all service type checks:

```bash
scripts/run_global_mypy.sh
```

Run lint checks for Python services:

```bash
scripts/run_global_pylint.sh
```

Run combined unit tests + coverage output:

```bash
scripts/run_global_pytests.sh
```

These scripts are intended as repo-wide quality entry points before pushing changes.

## CI & Pre-Commit Gates

### Pre-commit (`.pre-commit-config.yaml`)

- Service unit tests for Watchdog and Gatekeeper.
- Mypy for Watchdog and Gatekeeper.
- Pylint for Watchdog.
- UI lint, UI tests, and UI build.

### GitHub Actions (`.github/workflows/ci.yml` and `ui-ci.yml`)

- UI lint + build + tests with **100% coverage gate** (lines, branches, functions, statements).
- Gateway (`gatekeeper`) pytest with `--cov-fail-under=100`.
- Watchdog pytest with `--cov-fail-under=100`.
- Backend quality job matrix for mypy/pylint.

This gives both local and CI enforcement paths.

## Schemathesis Contract & Fuzz Testing

### Full-stack run (all 4 services)

```bash
scripts/run_schemathesis_full_stack.sh
```

This script:

- Waits for service readiness.
- Exports auth/service tokens automatically.
- Pulls fresh OpenAPI specs for:
  - Watchdog (`4319`)
  - Gatekeeper (`4321`)
  - Resolver (`4322`)
  - Notifier (`4323`)
- Runs Schemathesis against all 4 services with:
  - `--phases=examples,coverage,fuzzing,stateful`
  - conformance, schema, header, auth, and resilience checks
  - JUnit + HAR + NDJSON reports under `test-reports/schemathesis/`

In practice, this means every supported API surface is exercised with deterministic examples plus high-volume fuzzing/stateful exploration across all four service contracts.

### Service-focused runs

- `scripts/run_schemathesis_watchdog_only.sh`
- `scripts/run_schemathesis_gatekeeper_only.sh`
- `scripts/run_schemathesis_notifier_only.sh`
- `scripts/run_schemathesis_resolver_only.sh`

Use these for faster iteration when your change is service-specific.

## Typical Developer Workflow

1. Run targeted service unit tests while developing.
2. Run `scripts/run_global_mypy.sh` and `scripts/run_global_pylint.sh`.
3. Run `scripts/run_global_pytests.sh` for full backend confidence.
4. Run service-specific Schemathesis (or full-stack script for release-level confidence).
5. Check artifacts in `test-reports/` when debugging failures.

## Why This Matters

- Unit tests validate business behavior and edge cases close to code.
- Type/lint gates keep interfaces and code health stable.
- Coverage reports make blind spots visible.
- Schemathesis catches contract, schema, and protocol-level failures that unit tests often miss.

Together, these layers provide strong confidence for multi-service changes before they reach users.
