# Be Observant

Observability control plane for Grafana, Loki, Tempo, Alertmanager, and Mimir.

## What this runs

- Backend API: `server` (FastAPI) on `http://localhost:4319`
- Grafana via reverse proxy: `http://localhost:8080/grafana/`
- OTLP gateway (auth + org mapping): `http://localhost:4320`
- Postgres + Loki + Tempo + Mimir + Alertmanager

## Quick start (Docker Compose)

1. Create environment overrides (optional but strongly recommended):

```bash
cp .env.example .env 2>/dev/null || true
```

Example `.env` contents are provided in the repository root (`.env.example`). Edit values marked `replace_...` or `changeme` before starting in a non-development environment. Important variables you should set at minimum:

- `POSTGRES_PASSWORD` — Postgres password used by docker-compose
- `JWT_SECRET_KEY` — strong JWT signing secret (do **not** use the default)
- `DEFAULT_ADMIN_PASSWORD` — initial admin password (rotate immediately)
- `DATA_ENCRYPTION_KEY` — Fernet key for encrypting channel config at rest
- `DEFAULT_OTLP_TOKEN`, `INBOUND_WEBHOOK_TOKEN` — tokens for agent/ingest/webhook protection

You can generate a Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The repository also contains a `ui/.env.example` for frontend defaults.


2. Set at least these values in `.env` for non-dev usage:

- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_OTLP_TOKEN`
- `INBOUND_WEBHOOK_TOKEN`
- `DATA_ENCRYPTION_KEY`

3. Start stack:

```bash
docker compose up -d --build
```

4. Verify health:

```bash
curl -s http://localhost:4319/health
```

5. Open UI/Grafana:

- API docs: `http://localhost:4319/docs`
- Grafana proxy: `http://localhost:8080/grafana/`

## Local backend run (without Docker for API process)

From `server/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Required services (Postgres + Loki/Tempo/Mimir/Alertmanager/Grafana) must still be reachable via env URLs.

## UI development

From `ui/`:

```bash
npm install
npm run dev
```

Build production UI:

```bash
npm run build
npm run start
```

## Hosting notes

- Keep `TRUST_PROXY_HEADERS=false` unless behind a trusted reverse proxy.
- Set IP allowlists for public inbound endpoints:
  - `WEBHOOK_IP_ALLOWLIST`
  - `GATEWAY_IP_ALLOWLIST`
  - `AUTH_PUBLIC_IP_ALLOWLIST`
- Use strong secrets for all tokens/passwords; do not keep compose defaults in production.
- Terminate TLS at your edge proxy/load balancer.

## Testing and load generation

The repo includes telemetry generators under `tests/`:

```bash
bash tests/generator.sh
bash tests/logs.sh localhost:4318 5 0.05
bash tests/traces.sh localhost:4318 200 0.03
```

These scripts require Docker and generate synthetic traces/logs for validation.

## Stop and cleanup

```bash
docker compose down
docker compose down -v   
```
