# AGENTS.md

This file is the working guide for AI coding agents in this repository.

## Start Here

1. Read [README.md](README.md) for the product overview and local setup paths.
2. Read [CONTRIBUTING.md](CONTRIBUTING.md) for contribution expectations and review hygiene.
3. Read [DEVELOPERS.md](DEVELOPERS.md) for the shortest workflow map.
4. Read [scripts/README.md](scripts/README.md) for the canonical task-runner behavior.
5. Read [DEPLOYMENT.md](DEPLOYMENT.md) and [USER GUIDE.md](USER%20GUIDE.md) when the change touches runtime, setup, or deployment.

## Working Rules

- Start from the smallest file or service that actually owns the behavior.
- Prefer a single focused edit over broad refactors.
- Do not add new abstractions unless they reduce duplication or remove a real bug.
- Keep changes consistent with the surrounding service style.
- Do not overwrite user changes or unrelated work in the tree.
- Avoid destructive git operations.

## Repository Shape

This workspace is a multi-service observability platform, not a single app.

- `watchdog` is the main control plane and root bootstrap path.
- `gatekeeper` handles OTLP auth and ingress validation.
- `notifier` handles alerting, incidents, and integrations.
- `resolver` handles RCA and analysis workflows.
- `ui` is the React/Vite operator frontend.
- `charts/observantio` owns the Helm chart and Kubernetes installer path.
- `release` owns the production Compose release bundle scripts.
- `otel` owns the local telemetry generator and collector harness.
- `scripts` owns repo-wide quality gates and helper entrypoints.
- `configs` stores shared runtime templates and generated configs.
- `docker-compose.yml` and `docker-compose.prod.yml` define the local and release stack topologies.
- `test-reports` is generated output and should not be hand-edited.

Root-level docs are the source of truth for the high-level flow. Service folders and workspace roots own their own implementation, tests, and API contracts.

## Preferred Workflow

1. Find the owning service or root document.
2. Read only the smallest relevant slice of code or docs.
3. Make the smallest clean edit that fixes the issue.
4. Validate with the narrowest useful check first.
5. Expand only if the narrow check exposes a new problem.

## Quick Start Paths

- Use `make quickstart` for the shortest local bootstrap path.
- Use `scripts/run_global_mypy.sh` for type checking.
- Use `scripts/run_global_pylint.sh` for linting.
- Use `scripts/run_global_pytests.sh` for tests.
- Use `scripts/run_global_mutations.sh` for mutation testing.
- Use `scripts/run_schemathesis.sh <service>` for contract and fuzz testing.

If you only changed one backend service, pass one of `resolver`, `gatekeeper`, `notifier`, or `watchdog` to the quality scripts. For `ui` or `showcase`, use the package scripts in those folders.

## Setup And Runtime Notes

- Local development starts from [install.py](install.py) or the manual compose flow in the README.
- The root `.env.example` is the environment contract.
- `docker-compose.yml` is the local reference deployment.
- `docker-compose.prod.yml` and [DEPLOYMENT.md](DEPLOYMENT.md) describe the release bundle path.
- The Helm chart under `charts/observantio` is the Kubernetes path.

## Generated Artifacts

- Treat `test-reports/` as generated output.
- Update OpenAPI snapshots when endpoint contracts change.
- Keep generated files out of hand-edited changes unless the generator itself changed.
- Regenerate runtime config files only when the change actually affects sizing or configuration output.

## Validation Order

Use the cheapest check that can falsify the change first.

1. Targeted unit or service test.
2. Narrow lint or typecheck for the touched service.
3. Broader quality gate if the change spans shared code.
4. Full repo sweep only when the change is cross-cutting or risk is high.

## Safety And Security

- Never commit secrets, tokens, or private keys.
- Be careful with auth, tenancy, rate limiting, proxy behavior, and generated credentials.
- If a change affects deployment or security posture, call that out explicitly in the summary.

## When To Update Docs

- Update [README.md](README.md) for root workflow or setup changes.
- Update [DEVELOPERS.md](DEVELOPERS.md) for developer-task shortcuts and workflow map changes.
- Update [CONTRIBUTING.md](CONTRIBUTING.md) for review or contribution policy changes.
- Update [USER GUIDE.md](USER%20GUIDE.md) or [DEPLOYMENT.md](DEPLOYMENT.md) for runtime or release behavior changes.