# Developer Index

This file is a quick map for contributors who want the shortest path to the right workflow.

## Start Here

- If you are an AI coding agent, read [AGENTS.md](AGENTS.md) first.
- Read [README.md](README.md) for the product overview and local setup paths.
- Read [CONTRIBUTING.md](CONTRIBUTING.md) for contribution expectations.
- Read [scripts/README.md](scripts/README.md) for the canonical task runner details.
- Use [Makefile](Makefile) for the shortest local bootstrap and quality-gate aliases.
- Use [DEPLOYMENT.md](DEPLOYMENT.md) when your change affects release or compose deployment behavior.

## Core Developer Commands

The repository already standardizes its quality gates through the `scripts/` helpers.

- `make quickstart` to bootstrap a local dev environment with `install.py`.
- `make lint`, `make typecheck`, and `make test` as short aliases for the global quality gates.
- `make mutations` and `make schemathesis SERVICE=<service>` when you need the slower validation flows.

- `scripts/run_global_mypy.sh` for type checking.
- `scripts/run_global_pylint.sh` for linting.
- `scripts/run_global_pytests.sh` for tests.
- `scripts/run_global_mutations.sh` for mutation coverage.
- `scripts/run_schemathesis.sh <service>` for API contract and fuzz testing.

Pass one service name when you only changed a single area: `resolver`, `gatekeeper`, `notifier`, or `watchdog`.

## Service Boundaries

- `watchdog` owns the main control plane and the root developer setup flow.
- `gatekeeper` owns OTLP auth and ingress validation.
- `notifier` owns alerting, incidents, and integrations.
- `resolver` owns RCA and analysis workflows.

## Generated Or Shared Artifacts

- Update OpenAPI snapshots when an endpoint contract changes.
- Treat `test-reports/` as generated output.
- Use the root `.env.example` and service docs as the source of truth for environment variables.
- Keep generated files out of normal hand-edited changes unless the generator itself changed.

## Good Workflow Habits

- Make changes in the smallest service that owns the behavior.
- Add or update tests alongside behavior changes.
- Prefer a narrow quality gate over a full repo sweep when only one service changed.
- If a change touches setup or runtime docs, update the nearest root doc instead of creating a new one.