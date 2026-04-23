<div align="center">

# Observantio Release Operations

  <img src="../assets/stack.png" alt="Observantio release stack icon" width="150" />

  <p>
    <img src="https://img.shields.io/badge/Mode-Release%20Bundle-1f2937?style=flat-square" alt="Release bundle" />
    <img src="https://img.shields.io/badge/Runtime-Docker%20Compose-0f766e?style=flat-square" alt="Docker Compose" />
    <img src="https://img.shields.io/badge/Focus-Install%20%7C%20Restart%20%7C%20Uninstall-0ea5e9?style=flat-square" alt="Operations" />
  </p>
</div>

This folder contains release runtime scripts for deploying and operating the production compose stack (`docker-compose.prod.yml`). The release workflow also publishes a separate Helm chart bundle as `observantio-${BUNDLE_VERSION}-helm-charts.tar.gz`, which contains the chart root, values files, templates, and `installer.sh`.

This is the release-bundle counterpart to the experimental developer installer ([install.py](../install.py)) and the Kubernetes chart installer ([charts/observantio/installer.sh](../charts/observantio/installer.sh)).

## Why Docker Compose Matters Here

The release scripts are built around Compose lifecycle operations:

- Install bootstraps `.env`, secrets, and runtime sizing.
- Restart reapplies optimal config and recreates services.
- Uninstall tears down services (optionally volumes).

If Compose is unavailable, the scripts exit early.

## Docker Compose Requirement (Minimum)

Hard requirement in scripts:

- `docker compose` plugin **or** `docker-compose` binary must exist.

Repository reality:

- The scripts validate availability, but do not pin an exact semver minimum.
- In practice, use modern Compose v2 (recommended: v2.20+ on Linux) for consistent behavior with current compose-spec features.

## Scripts In This Folder

### `install.sh`

```bash
./release/install.sh
./release/install.sh --help
```

What it does:

- Ensures Docker + Compose are available.
- Creates `.env` from `.env.example` if missing.
- Randomizes insecure/default secret values.
- Prompts for UI host + bootstrap admin details.
- Runs `scripts/run_optimal_config.sh` for host-aware sizing.
- Starts stack with `docker-compose.prod.yml` when selected in flow.

The installer is interactive and should be run from a terminal session.

### `restart.sh`

```bash
./release/restart.sh
./release/restart.sh --purge
```

What it does:

- Re-runs `scripts/run_optimal_config.sh`.
- Performs compose down/up sequence for the production stack.
- Useful after config changes or host resizing.
- `--purge` removes named volumes before restarting, so the stack comes back up with fresh data volumes.

### `uninstall.sh`

```bash
./release/uninstall.sh
./release/uninstall.sh --purge
```

What it does:

- Stops and removes services (`down --remove-orphans`).
- `--purge` also removes named volumes.

## Safe `.env` Setup Before Production Use

At minimum, set/verify these before internet-facing use:

- `APP_ENV=production`
- `ENVIRONMENT=production`
- `DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false` (after initial bootstrap)
- `DEFAULT_ADMIN_USERNAME`, `DEFAULT_ADMIN_PASSWORD`, `DEFAULT_ADMIN_EMAIL`
- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY` (or asymmetric JWT keys if configured)
- `DATA_ENCRYPTION_KEY`
- `DEFAULT_OTLP_TOKEN`, `OTEL_OTLP_TOKEN`
- `GATEWAY_INTERNAL_SERVICE_TOKEN`
- `NOTIFIER_SERVICE_TOKEN`, `NOTIFIER_EXPECTED_SERVICE_TOKEN`
- `NOTIFIER_CONTEXT_SIGNING_KEY`, `NOTIFIER_CONTEXT_VERIFY_KEY`
- `RESOLVER_SERVICE_TOKEN`, `RESOLVER_EXPECTED_SERVICE_TOKEN`
- `RESOLVER_CONTEXT_SIGNING_KEY`, `RESOLVER_CONTEXT_VERIFY_KEY`
- `ALLOWLIST_FAIL_OPEN=false`
- `GATEWAY_ALLOWLIST_FAIL_OPEN=false`
- concrete allowlists:
  - `AUTH_PUBLIC_IP_ALLOWLIST`
  - `GATEWAY_IP_ALLOWLIST`
  - `GRAFANA_PROXY_IP_ALLOWLIST`
  - `GF_AUTH_PROXY_WHITELIST`

## Basic Run Sequence

1. Configure `.env` safely.
2. Run `./release/install.sh`.
3. Verify:
   - `docker compose -f docker-compose.prod.yml ps`
   - `curl http://localhost:4319/health`
   - `curl http://localhost:4319/ready`
4. Use `./release/restart.sh` after changing sizing/config.
5. Use `./release/restart.sh --purge` when you want to refresh the stack with new empty volumes.
6. Use `./release/uninstall.sh` (or `--purge`) for teardown.

## Read This Next

For complete deployment, network exposure, hardening, and post-install verification details:

- [../DEPLOYMENT.md](../DEPLOYMENT.md)
