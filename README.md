# Be Observant

Be Observant is a comprehensive observability control plane that integrates Grafana, Loki, Tempo, Alertmanager, and Mimir into a unified platform for monitoring, logging, tracing, and alerting.

## Architecture Overview

This platform provides:

- **Backend API** (`server`, FastAPI): Core REST API running on `http://localhost:4319`
- **Grafana Integration**: Reverse proxy access at `http://localhost:8080/grafana/`
- **OTLP Gateway**: Authentication and organization mapping on `http://localhost:4320`
- **Data Services**: Postgres database, Loki for logs, Tempo for traces, Mimir for metrics, and Alertmanager for alerts

## Quick Start with Docker Compose

1. **Configure Environment Variables** (strongly recommended for production):

   Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` to set secure values. Key variables to configure:

   - `POSTGRES_PASSWORD`: Database password
   - `JWT_SECRET_KEY`: Strong JWT signing key (generate securely)
   - `DEFAULT_ADMIN_PASSWORD`: Initial admin credentials (change immediately)
   - `DATA_ENCRYPTION_KEY`: Fernet key for data encryption (generate with Python)
   - `DEFAULT_OTLP_TOKEN`, `INBOUND_WEBHOOK_TOKEN`: Secure tokens for ingestion

   Generate a Fernet key:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   The repository includes `.env.example` and `ui/.env.example` for reference.

2. **Set Required Variables** for non-development environments:

   Ensure these are configured in `.env`:

   - `POSTGRES_PASSWORD`
   - `JWT_SECRET_KEY`
   - `DEFAULT_ADMIN_PASSWORD`
   - `DEFAULT_OTLP_TOKEN`
   - `INBOUND_WEBHOOK_TOKEN`
   - `DATA_ENCRYPTION_KEY`

3. **Launch the Stack**:

   ```bash
   docker compose up -d --build
   ```

4. **Verify Deployment**:

   Check service health:

   ```bash
   curl -s http://localhost:4319/health
   ```

5. **Access Interfaces**:

   - API Documentation: `http://localhost:4319/docs`
   - Grafana Dashboard: `http://localhost:8080/grafana/`

## Local Development Setup

### Backend Development

To run the API server locally (requires external services):

```bash
cd server/
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Ensure Postgres, Loki, Tempo, Mimir, Alertmanager, and Grafana are accessible via environment URLs.

### Frontend Development

For UI development:

```bash
cd ui/
npm install
npm run dev
```

Build for production:

```bash
npm run build
npm run start
```

## Production Deployment Considerations

- **Proxy Configuration**: Set `TRUST_PROXY_HEADERS=false` unless behind a verified reverse proxy
- **Security**: Configure IP allowlists for public endpoints:
  - `WEBHOOK_IP_ALLOWLIST`
  - `GATEWAY_IP_ALLOWLIST`
  - `AUTH_PUBLIC_IP_ALLOWLIST`
- **Secrets Management**: Use strong, unique secrets for all tokens and passwords; avoid default values
- **TLS Termination**: Handle SSL/TLS at your load balancer or edge proxy

## Keycloak / OIDC auth mode

Be Observant supports external auth using Keycloak (including Microsoft SSO federated through Keycloak).

- Set `AUTH_PROVIDER=keycloak`
- Set `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID` (and `OIDC_CLIENT_SECRET` for confidential clients)
- Optional: `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `OIDC_SCOPES`
- Keep password grant disabled by default: `AUTH_PASSWORD_FLOW_ENABLED=false`
- Optional fallback (legacy/migration only): `AUTH_PASSWORD_FLOW_ENABLED=true`

OIDC endpoints:

- `POST /api/auth/oidc/authorize-url` (build authorization URL)
- `POST /api/auth/oidc/exchange` (authorization-code exchange)
- `GET /api/auth/mode` (UI/runtime auth capability discovery)

When Keycloak mode is enabled, local self-registration is disabled and app users are resolved by email from the OIDC token. Optional admin-driven Keycloak provisioning is available with `KEYCLOAK_USER_PROVISIONING_ENABLED=true` and Keycloak admin client credentials.

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
