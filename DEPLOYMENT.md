# Deployment Guide

This guide explains how to deploy Observantio from the release tarball, what to open on the host firewall/security group, and what to harden after first boot.

This page covers the release-bundle compose path only. For local development, use [install.py](install.py); for Kubernetes, use [charts/observantio/installer.sh](charts/observantio/installer.sh) or the separate `observantio-${BUNDLE_VERSION}-helm-charts.tar.gz` release asset.

## Prerequisites

- Linux host with Docker Engine installed
- Docker Compose plugin (`docker compose`) or `docker-compose`
- Internet egress from host to pull container images from `ghcr.io` and from other docker repos

## Install From Release Tarball

Quick install:

```bash
curl -fsSL https://raw.githubusercontent.com/observantio/watchdog/main/download.sh -o download.sh
bash download.sh

# Optional:
# bash download.sh v0.0.6 arm64
# bash download.sh v0.0.6 amd64
```

`download.sh` defaults to the latest GitHub release and `multi` architecture. Before it downloads anything, it checks that:

- Docker is installed and usable by the current user
- Docker Compose is available as `docker compose` or `docker-compose`
- Docker and Compose do not require `sudo` for this install flow

If Docker or Compose only work through `sudo`, the script exits early with a clear error so the host can be fixed before install.

The installer will:
- Create `.env` from `.env.example` if missing
- Randomize important secrets if defaults/placeholders are detected
- Ask for UI host and admin bootstrap values
- Detect host CPU/RAM and render Loki/Tempo/Mimir limits plus generated config files
- Pull images and optionally start the stack

## Day-2 Operations

From the extracted release directory:

- Restart:
  `./restart.sh`
- Re-render adaptive observability sizing without restarting:
  `./scripts/run_optimal_config.sh`
- Stop/uninstall:
  `./uninstall.sh`
- Uninstall and remove named volumes:
  `./uninstall.sh --purge`

Set `OBS_RESOURCE_PROFILE=manual` in `.env` if you want to keep hand-tuned `LOKI_*`, `TEMPO_*`, and `MIMIR_*` sizing values instead of auto-detecting from the host.

## Ojo Agent (Telemetry Collection)

To collect and ship host/service telemetry into this platform, you can run the Ojo agent.

- Ojo repository: https://github.com/observantio/ojo
- Configure Ojo (or your collector) to send OTLP data to this deployment's gateway (`http://<host>:4320`) using your `x-otlp-token`.

### Ojo Agent Setup Wizard (UI)

From the UI header, open **Download Ojo Agent** and follow the 5-slide wizard.

- Slide 1: pick `Linux`, `Windows`, or `Extra services`.
- Slide 2: download from GitHub releases and select a matching asset. The wizard now auto-uses the first matching asset in the install command when none is explicitly selected.
- Slide 2 expected behavior: for the current `v0.0.2` core release flow, seeing **Matching assets (2)** for core binaries is normal.
- Slide 3+: generate config, bind API key token, and run connectivity verification.

## Required Network Ports

Open only what you actually need.

- `5173/tcp` UI
- `8080/tcp` Grafana proxy
- `4320/tcp` OTLP gateway ingest
- `4319/tcp` Watchdog API direct access (recommended to keep private and front with reverse proxy instead)
- `4323/tcp` Notifier API (if accessed directly)

## Recommended Public Exposure Model

For internet-facing deployments, prefer exposing only `80/443` through a reverse proxy and routing:

- `/` to UI
- `/api` to Watchdog
- `/grafana` to Grafana proxy

This removes most cross-origin complexity and lets you keep `4319` private.

## Post-Install Hardening Checklist

Apply these before production usage.

1. Set `APP_ENV=production` and `ENVIRONMENT=production`.
2. Set `DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false` after initial admin setup.
3. Keep strong, unique values for all service tokens and signing keys.
4. Set `ALLOWLIST_FAIL_OPEN=false` and `GATEWAY_ALLOWLIST_FAIL_OPEN=false`.
5. Configure concrete allowlists instead of empty values:
   `AUTH_PUBLIC_IP_ALLOWLIST`, `GATEWAY_IP_ALLOWLIST`, `GRAFANA_PROXY_IP_ALLOWLIST`.
6. Keep `GF_AUTH_PROXY_WHITELIST` correct for your proxy path.
7. Use TLS termination at the edge and set secure cookie behavior (`FORCE_SECURE_COOKIES=true` when applicable).
8. Rotate bootstrap/default credentials and remove any placeholder values.
9. Use persistent backups for PostgreSQL and observability data volumes.

## Local Passwords vs OIDC

You can run with local auth, but for production teams OIDC is recommended.

Local auth:
- Simpler bootstrap
- More operational burden (password lifecycle, reset, MFA policy management)

OIDC:
- Centralized identity, MFA, deprovisioning
- Better audit/compliance posture

If moving to OIDC later:
1. Configure OIDC settings in `.env` (`AUTH_PROVIDER`, issuer, client id/secret, scopes, JWKS).
2. Validate login flow with a test account.
3. Keep at least one break-glass admin path documented.

## Verification

After startup, check:

- `docker compose -f docker-compose.prod.yml ps`
- `curl http://localhost:4319/health`
- `curl http://localhost:4319/ready`
- `curl http://localhost:4323/health`

If host port `4319` is private, run the health check on the host itself or from inside the Docker network.

## Grafana Proxy Auth Note

If `GRAFANA_PROXY_IP_ALLOWLIST` or `GF_AUTH_PROXY_WHITELIST` is empty/incorrect, Grafana proxy auth will not be trusted and users will see the native Grafana login page.

Minimum recommended values:

- `GRAFANA_PROXY_IP_ALLOWLIST=127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`
- `GF_AUTH_PROXY_WHITELIST=127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`

Also ensure users access Grafana through the proxy path (`/grafana` on port `8080`) rather than direct port `3000`.
