# User Guide

## 1) Sign in

1. Open `http://localhost:8080/grafana/` (or your hosted URL).
2. Log in with your beObservant user.
3. If first run, use the bootstrap admin from environment (`DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD`).

## 2) Core areas

- **Dashboards**: View/create/update dashboards based on your permissions.
- **Datasources**: Query and manage allowed datasources.
- **Logs (Loki)**: Run log queries and filtering.
- **Traces (Tempo)**: Search traces and inspect spans.
- **Alerts (Alertmanager)**: Review alerts/silences and manage rules/channels.
- **Users/Groups/API Keys**: Admin area for access management.

## 3) Visibility model

Most shared resources use one of:

- `private`: only owner
- `group`: owner + selected groups
- `tenant`: everyone in tenant

If you cannot see a resource, check its visibility and your group membership.

## 4) OTLP ingestion tokens

For app/agent ingest through the gateway (`:4320`):

- Send token as header: `x-otlp-token: <token>`
- Gateway validates token and maps tenant/org automatically.

## 5) Common operations

### Create a dashboard

1. Go to dashboards.
2. Create/save dashboard.
3. Set visibility (`private`, `group`, `tenant`).
4. For `group`, choose one or more groups.

### Silence noisy alerts

1. Go to silences.
2. Create silence with matchers and time range.
3. Choose visibility and optional shared groups.

### Manage API keys

1. Open API keys page.
2. Create key for service/user workflows.
3. Disable or delete old keys immediately.

## 6) Troubleshooting

- **401/403 errors**: token expired, missing permission, or wrong tenant scope.
- **No data in dashboards**: datasource visibility/ownership mismatch or backend unavailable.
- **Missing alerts/logs/traces**: verify OTLP token, tenant header mapping, and backend health.
- **Webhook/gateway rejected**: check allowlist and shared token configuration.

## 7) Best practices

- Use least privilege permissions.
- Prefer group-level access over tenant-wide when possible.
- Rotate API keys and OTLP tokens regularly.
- Keep default credentials disabled in hosted/production environments.
