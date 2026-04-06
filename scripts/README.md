<div align="center">

# Observantio Scripts Guide

  <img src="../assets/scripts.png" alt="Observantio scripts icon" width="150" />

  <p>
    <img src="https://img.shields.io/badge/Scope-Repo%20Automation-1f2937?style=flat-square" alt="Scope" />
    <img src="https://img.shields.io/badge/Quality-pytest%20%7C%20mypy%20%7C%20pylint-0f766e?style=flat-square" alt="Quality" />
    <img src="https://img.shields.io/badge/Contracts-Schemathesis-0ea5e9?style=flat-square" alt="Schemathesis" />
  </p>
</div>

This folder contains repo-level automation scripts for quality gates, contract testing, and runtime configuration.

## Prerequisites

- Run from repository root unless noted otherwise.
- Python virtual environment at `.venv` for Python tooling scripts.
- Docker + Docker Compose for stack and Schemathesis flows.

## Script Catalog

### `run_global_pytests.sh`

Runs pytest for backend services with coverage and JUnit output. Default order: `resolver`, `gatekeeper`, `notifier`, `watchdog`.

```bash
scripts/run_global_pytests.sh [SERVICE]
```

Optional first argument: one of `resolver`, `gatekeeper`, `notifier`, or `watchdog` to run only that suite. Use `-h` / `--help` for usage.

Expect:

- Per-service JUnit XML in `test-reports/junit/`.
- Per-service and combined coverage in `test-reports/coverage/` (combined report includes only the services that ran).
- Combined HTML report in `test-reports/coverage/html/index.html`.

### `run_global_mypy.sh`

Runs mypy using repo `pyproject.toml` defaults. By default all four services are checked; pass a service name to scope the run.

```bash
scripts/run_global_mypy.sh [SERVICE]
```

Optional first argument: `resolver`, `gatekeeper`, `notifier`, or `watchdog`. Use `-h` / `--help` for usage.

Expect:

- Type-check output per invoked service.
- Non-zero exit if any type errors remain.

### `run_global_pylint.sh`

Runs pylint with shared config. By default all four services are checked; pass a service name to scope the run.

```bash
scripts/run_global_pylint.sh [SERVICE]
```

Optional first argument: `resolver`, `gatekeeper`, `notifier`, or `watchdog`. Use `-h` / `--help` for usage.

Expect:

- Lint output per invoked service.
- Non-zero exit on lint failures.

### `run_optimal_config.sh`

Generates adaptive observability runtime configs based on host resources and `.env` profile.

```bash
scripts/run_optimal_config.sh
```

Expect:

- Updated generated configs under `configs/generated/`.
- Updated sizing keys in `.env` depending on `OBS_RESOURCE_PROFILE`.
- Useful for day-2 tuning and release restarts.

### `run_schemathesis.sh`

Runs contract + fuzz/stateful testing for a single service selected by argument.

```bash
scripts/run_schemathesis.sh [SERVICE]
```

Optional first argument: one of `resolver`, `gatekeeper`, `notifier`, or `watchdog`. Use `-h` / `--help` for usage.

Expect:

- Readiness checks and auth/context bootstrap for the selected service.
- OpenAPI snapshot in `test-reports/openapi-<service>.json` and mirrored to `<service>/openapi.json`.
- Reports under `test-reports/schemathesis/<service>/` + JUnit XML at root of `test-reports/`.

## Recommended Gate Order

1. `scripts/run_global_mypy.sh`
2. `scripts/run_global_pylint.sh`
3. `scripts/run_global_pytests.sh`
4. `scripts/run_schemathesis.sh <service>` for each service you changed

## Troubleshooting

- `.venv` missing: create/install tool dependencies first.
- Compose/network failures: ensure stack is healthy (`docker compose ps`).
- Auth failures in Schemathesis: verify `.env` secrets and `.schemathesis` bearer when required.

## Related Docs

- Root project overview: [../README.md](../README.md)
- Deployment details and hardening: [../DEPLOYMENT.md](../DEPLOYMENT.md)
- Test strategy guide: [../tests/README.md](../tests/README.md)
