# observantio Helm chart

This chart now covers the main `docker-compose.prod.yml` topology:
- core services: `observantio`, `gatekeeper`, `notifier`, `resolver`, optional `ui`
- telemetry gateway: `otlp-gateway`, optional `otel-agent`
- data services: optional in-cluster `postgres`, `redis`
- observability stack: `loki`, `tempo`, `mimir`, `alertmanager`, `grafana`, `grafana-auth-gateway`
- secret wiring via existing Kubernetes Secret or External Secrets Operator

## Render

```bash
helm template observantio charts/observantio
```

## Install

```bash
helm upgrade --install observantio charts/observantio -n observantio --create-namespace
```

`values.yaml` now defaults to hardened runtime values:
- `APP_ENV=production`
- `ENVIRONMENT=production`
- `HOST=0.0.0.0`
- `JWT_ALGORITHM=RS256`
- `JWT_AUTO_GENERATE_KEYS=false`
- `DB_AUTO_CREATE_SCHEMA=false`
- `CORS_ALLOW_CREDENTIALS=false`
- `GATEWAY_ALLOWLIST_FAIL_OPEN=false`
- NetworkPolicy / PDB / HPA enabled by default
- internal-only services (`ClusterIP`) by default, with optional dedicated public OTLP gateway

## Secrets (Production)

Production path uses an existing Kubernetes Secret (or External Secrets Operator) instead of inline chart-managed secrets.

```bash
helm upgrade --install observantio charts/observantio \
  -n observantio --create-namespace \
  -f charts/observantio/values-production.yaml
```

If you prefer chart-managed secret creation, enable it explicitly and provide all required values:

```bash
helm upgrade --install observantio charts/observantio \
  -n observantio --create-namespace \
  --set secrets.create=true \
  --set-string secrets.POSTGRES_USER='watchdog' \
  --set-string secrets.POSTGRES_PASSWORD='<strong-db-password>' \
  --set-string secrets.POSTGRES_DB='watchdog' \
  --set-string secrets.JWT_SECRET_KEY='<strong-random-string>' \
  --set-string secrets.DATA_ENCRYPTION_KEY='<fernet-key>' \
  --set-string secrets.INBOUND_WEBHOOK_TOKEN='<webhook-token>' \
  --set-string secrets.DEFAULT_OTLP_TOKEN='<otlp-token>' \
  --set-string secrets.OTEL_OTLP_TOKEN='<otlp-token>' \
  --set-string secrets.OTLP_INGEST_TOKEN='<otlp-ingest-token>' \
  --set-string secrets.GATEWAY_INTERNAL_SERVICE_TOKEN='<gateway-internal-token>' \
  --set-string secrets.GATEWAY_STATUS_OTLP_TOKEN='<gateway-health-token>' \
  --set-string secrets.NOTIFIER_SERVICE_TOKEN='<token>' \
  --set-string secrets.NOTIFIER_EXPECTED_SERVICE_TOKEN='<token>' \
  --set-string secrets.NOTIFIER_CONTEXT_SIGNING_KEY='<key>' \
  --set-string secrets.NOTIFIER_CONTEXT_VERIFY_KEY='<key>' \
  --set-string secrets.RESOLVER_SERVICE_TOKEN='<token>' \
  --set-string secrets.RESOLVER_EXPECTED_SERVICE_TOKEN='<token>' \
  --set-string secrets.RESOLVER_CONTEXT_SIGNING_KEY='<key>' \
  --set-string secrets.RESOLVER_CONTEXT_VERIFY_KEY='<key>' \
  --set-string secrets.GRAFANA_USERNAME='admin' \
  --set-string secrets.GRAFANA_PASSWORD='<strong-password>'
```

To expose only Envoy OTLP publicly:

```bash
helm upgrade --install observantio charts/observantio \
  -n observantio --create-namespace \
  --set otlpGateway.publicService.enabled=true
```

## Access

```bash
~/.local/bin/kubectl -n observantio port-forward svc/observantio-observantio-observantio 4319:4319
~/.local/bin/kubectl -n observantio port-forward svc/observantio-observantio-ui 5173:80
~/.local/bin/kubectl -n observantio port-forward svc/observantio-observantio-grafana-auth-gateway 8080:8080
```

## Notes

- By default, all components are enabled except `otel-agent`.
- Use feature flags in `values.yaml` to disable parts of the stack, for example `loki.enabled=false` or `gatekeeper.enabled=false`.
- `values-production.yaml` is included as a baseline for hardened cluster deployments.
