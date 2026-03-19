# Observantio User Guide

This guide explains how to deploy and operate the full Observantio stack in this repository.

## 1. What You Are Running

This is a multi-service product, not a single app.

### Core services

| Service | Default Port | Role |
| --- | --- | --- |
| `watchdog` | `4319` | Main control plane API (auth, users, groups, API keys, observability proxying) |
| `gatekeeper` (`gateway-auth`) | `4321` (internal) | OTLP token validation service for Envoy `ext_authz` |
| `notifier` | `4323` | Alert rules, channels, silences, incidents, Jira integrations |
| `resolver` | `4322` (internal) | RCA and analysis engine across logs, metrics, traces |
| `ui` | `5173` | Operator frontend |

### Supporting services

| Service | Role |
| --- | --- |
| `postgres` | Persistent storage for watchdog, notifier, and resolver |
| `redis` | Rate-limiting and token/cache state |
| `otlp-gateway` | Envoy OTLP ingress (`4320`) |
| `loki` | Logs backend |
| `tempo` | Traces backend |
| `mimir` | Metrics and rule evaluation backend |
| `alertmanager` | Alert routing backend |
| `grafana` | Dashboard backend |
| `grafana-proxy` | Browser-facing Grafana proxy (`8080`) |
| `otel-agent` | Built-in telemetry generator for local testing |

## 2. Network and Port Model

Host-published endpoints in the default `docker-compose.yml`:

- `http://localhost:5173` (`ui`)
- `http://localhost:4319` (`watchdog`)
- `http://localhost:4320` (`otlp-gateway`)
- `http://localhost:4323` (`notifier`)
- `http://localhost:8080` (`grafana-proxy`)

Internal-only services (Docker network only):

- `gateway-auth` (`4321`)
- `resolver` (`4322`)

## 3. How Requests Flow

### User/API flow

1. User signs in via `ui` to `watchdog`.
2. `watchdog` resolves identity, permissions, and scope.
3. `watchdog` proxies signed/scoped requests to observability backends, notifier, and resolver.

### Telemetry ingestion flow

1. Collector/app sends OTLP HTTP to `http://localhost:4320`.
2. Envoy calls `gateway-auth` for authorization.
3. `gateway-auth` validates `x-otlp-token` and resolves tenant/org context.
4. Envoy forwards to Loki, Tempo, or Mimir with scoped headers.

### Alerting flow

1. Rules/channels/silences are managed through the UI.
2. `watchdog` sends alert-domain actions to `notifier`.
3. `notifier` syncs rule definitions to Mimir.
4. Alertmanager webhook events return to notifier.
5. Notifier creates/updates incidents and exposes them to the UI.

### RCA flow

1. User starts an RCA job in UI.
2. `watchdog` forwards signed request to `resolver`.
3. `resolver` analyzes Loki/Mimir/Tempo data.
4. UI retrieves report results through watchdog.

## 4. Prerequisites

- Docker with `docker compose`
- Git
- Python 3.11+ (for installer)
- Free host ports: `5173`, `4319`, `4320`, `4323`, `8080`

## 5. Setup Paths

### Option A: Installer (evaluation)

```bash
python3 install.py
```

Installer behavior (current script):

- Validates required tooling.
- Clones missing `resolver` and `notifier` repos if absent.
- Creates/updates `.env`.
- Generates bootstrap admin and secrets.
- Starts the compose stack.

### Option B: Manual

```bash
git clone https://github.com/observantio/watchdog Observantio
cd Observantio
cp .env.example .env
docker compose up -d --build
```

## 6. Required `.env` Values for First Run

Set these deliberately:

- `DEFAULT_ADMIN_USERNAME`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_ADMIN_EMAIL`
- `DATA_ENCRYPTION_KEY`
- `DEFAULT_OTLP_TOKEN`
- `GATEWAY_INTERNAL_SERVICE_TOKEN`
- `NOTIFIER_SERVICE_TOKEN` and `NOTIFIER_EXPECTED_SERVICE_TOKEN`
- `RESOLVER_SERVICE_TOKEN` and `RESOLVER_EXPECTED_SERVICE_TOKEN`
- `NOTIFIER_CONTEXT_SIGNING_KEY` and `NOTIFIER_CONTEXT_VERIFY_KEY`
- `RESOLVER_CONTEXT_SIGNING_KEY` and `RESOLVER_CONTEXT_VERIFY_KEY`

Auth baseline:

```env
AUTH_PROVIDER=local
AUTH_PASSWORD_FLOW_ENABLED=true
```

## 7. Verify Stack Health

```bash
docker compose ps
curl http://localhost:4319/health
curl http://localhost:4319/ready
curl http://localhost:4323/health
```

Internal services (`gateway-auth`, `resolver`) are not host-published by default. Check them via:

```bash
docker compose logs gateway-auth resolver
```

## 8. First Operator Workflow

1. Open `http://localhost:5173`.
2. Sign in with bootstrap admin.
3. Create at least one API key.
4. Set active scope in the UI.
5. Send telemetry with `x-otlp-token` to `http://localhost:4320`.
6. Confirm logs and traces arrive.
7. Create/test alert channels and rules.
8. Review incidents.
9. Run an RCA job.

## 9. OTLP Collector Pattern

Use one exporter endpoint per signal:

```yaml
exporters:
  otlphttp/logs:
    endpoint: http://localhost:4320/loki
    headers:
      x-otlp-token: YOUR_OTLP_TOKEN

  otlphttp/traces:
    endpoint: http://localhost:4320/tempo
    headers:
      x-otlp-token: YOUR_OTLP_TOKEN

  otlphttp/metrics:
    endpoint: http://localhost:4320/mimir
    headers:
      x-otlp-token: YOUR_OTLP_TOKEN
```

## 10. Troubleshooting Quick Map

| Symptom | Likely Cause | What To Check |
| --- | --- | --- |
| UI loads but login fails | Auth/bootstrap mismatch | `.env`, auth provider, bootstrap values |
| No logs/traces | Wrong token or wrong OTLP endpoint | `x-otlp-token`, `http://localhost:4320/*` |
| `/ready` stays not ready | Downstream service not healthy | `docker compose ps` + `docker compose logs` |
| Grafana proxy access fails | Auth/proxy mismatch | browser session + `grafana-proxy` logs |
| Alerts not firing | Rule/scope/data mismatch | org/product scope + expression + metric presence |
| RCA report is weak | Not enough cross-signal data | verify logs/metrics/traces density and time range |

## 11. Security Baseline Checklist

1. Replace all placeholder secrets.
2. Restrict CORS to real frontend origins.
3. Enable secure cookies and TLS in non-local environments.
4. Set trusted proxy headers/cidrs correctly if behind reverse proxy.
5. Add IP allowlists for sensitive endpoints.
6. Back up Postgres before destructive operations.

## 12. Source of Truth Order

If docs and runtime differ, trust in this order:

1. `docker-compose.yml`
2. `.env.example`
3. service `config.py` and route code (`watchdog`, `gatekeeper`, `notifier`, `resolver`)
4. UI API client/route behavior
