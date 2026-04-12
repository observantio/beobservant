# observantio Helm chart

This chart now covers the main `docker-compose.prod.yml` topology:
- core services: `observantio`, `gatekeeper`, `notifier`, `resolver`, optional `ui`
- telemetry gateway: `otlp-gateway`, optional `otel-agent`
- data services: optional in-cluster `postgres`, `redis`
- observability stack: `loki`, `tempo`, `mimir`, `alertmanager`, `grafana`, `grafana-auth-gateway`
- secret wiring for token/password values

## Render

```bash
helm template observantio charts/observantio
```

## Install

```bash
helm upgrade --install observantio charts/observantio -n observantio --create-namespace
```

`values.yaml` already includes these non-sensitive runtime defaults:
- `APP_ENV=development`
- `ENVIRONMENT=development`
- `HOST=0.0.0.0`
- `JWT_ALGORITHM=RS256`
- `JWT_AUTO_GENERATE_KEYS=true`
- `DB_AUTO_CREATE_SCHEMA=true`
- `CORS_ALLOW_CREDENTIALS=false`
- internal-only services (`ClusterIP`) by default, including OTLP gateway
- optional dedicated public OTLP gateway service toggle via `otlpGateway.publicService.enabled`

Only override sensitive values at install time (or via a private values file), for example:

```bash
helm upgrade --install observantio charts/observantio \
  -n observantio --create-namespace \
  --set-string secrets.POSTGRES_PASSWORD='<strong-db-password>' \
  --set-string secrets.JWT_SECRET_KEY='<strong-random-string>' \
  --set-string secrets.INBOUND_WEBHOOK_TOKEN='<webhook-token>' \
  --set-string secrets.DEFAULT_OTLP_TOKEN='<otlp-token>' \
  --set-string secrets.OTEL_OTLP_TOKEN='<otlp-token>' \
  --set-string secrets.OTLP_INGEST_TOKEN='<otlp-ingest-token>' \
  --set-string secrets.GATEWAY_INTERNAL_SERVICE_TOKEN='<gateway-internal-token>' \
  --set-string secrets.GATEWAY_STATUS_OTLP_TOKEN='<gateway-health-token>'
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
- The chart is production-oriented but defaults to single-replica components for easier local/kind bring-up.
