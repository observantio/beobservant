<div align="center">

# Observantio Watchdog Service

  <img src="../assets/wolf.png" alt="Watchdog wolf icon" width="150" />

  <p>
    <img src="https://img.shields.io/badge/Service-Control%20Plane-1f2937?style=flat-square" alt="Control Plane" />
    <img src="https://img.shields.io/badge/API-FastAPI-0f766e?style=flat-square" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Security-RBAC%20%7C%20Tenancy-0ea5e9?style=flat-square" alt="Security" />
  </p>
</div>

Watchdog is the main control-plane API for Observantio.
It sits in front of the LGTM stack and turns raw observability backends into a secure, multi-user operational product.

## What Watchdog Offers

- Authentication, sessions, MFA, OIDC exchange, and permission-aware user context.
- User/group/API-key lifecycle management with tenant scoping.
- Gateway validation endpoint used by Gatekeeper for OTLP token authorization.
- Proxy-style APIs for logs, traces, Grafana operations, alert flows, and resolver analysis.
- System-level runtime endpoints (health, readiness, metrics, agent/quota views).

## Proxy & Security Model

Watchdog does more than route requests. It enforces platform boundaries:

- RBAC: routes are permission-gated by role and resolved identity.
- Tenancy: operations are scoped to org/API-key context.
- Internal auth: service-to-service calls expect shared tokens and signed context.
- Ingestion auth chain: Gatekeeper calls `/api/internal/otlp/validate` before telemetry is accepted.
- Runtime hardening: request-size limits, concurrency limits, CORS policy, and security headers are applied centrally.

## Route Inventory (OpenAPI)

Current OpenAPI surface includes 92 paths:

```text
/ [get]
/api/agents/ [get]
/api/agents/active [get]
/api/agents/heartbeat [post]
/api/agents/volume [get]
/api/alertmanager/public/rules [get]
/api/alertmanager/{path} [delete, get, patch, post, put]
/api/auth/api-keys [get, post]
/api/auth/api-keys/{key_id} [delete, patch]
/api/auth/api-keys/{key_id}/hide [post]
/api/auth/api-keys/{key_id}/otlp-token/regenerate [post]
/api/auth/api-keys/{key_id}/shares [get, put]
/api/auth/api-keys/{key_id}/shares/{shared_user_id} [delete]
/api/auth/audit-logs [get]
/api/auth/audit-logs/export [get]
/api/auth/groups [get, post]
/api/auth/groups/{group_id} [delete, get, put]
/api/auth/groups/{group_id}/members [put]
/api/auth/groups/{group_id}/permissions [put]
/api/auth/login [post]
/api/auth/logout [post]
/api/auth/me [get, put]
/api/auth/mfa/disable [post]
/api/auth/mfa/enroll [post]
/api/auth/mfa/verify [post]
/api/auth/mode [get]
/api/auth/oidc/authorize-url [post]
/api/auth/oidc/exchange [post]
/api/auth/permissions [get]
/api/auth/register [post]
/api/auth/role-defaults [get]
/api/auth/users [get, post]
/api/auth/users/{user_id} [delete, put]
/api/auth/users/{user_id}/mfa/reset [post]
/api/auth/users/{user_id}/password [put]
/api/auth/users/{user_id}/password/reset-temp [post]
/api/auth/users/{user_id}/permissions [put]
/api/grafana/auth [get]
/api/grafana/bootstrap-session [post]
/api/grafana/dashboards [post]
/api/grafana/dashboards/db [post]
/api/grafana/dashboards/db/ [post]
/api/grafana/dashboards/meta/filters [get]
/api/grafana/dashboards/search [get]
/api/grafana/dashboards/{uid} [delete, get, put]
/api/grafana/dashboards/{uid}/hide [post]
/api/grafana/datasources [get, post]
/api/grafana/datasources/meta/filters [get]
/api/grafana/datasources/name/{name} [get]
/api/grafana/datasources/{uid} [delete, get, put]
/api/grafana/datasources/{uid}/hide [post]
/api/grafana/ds/query [post]
/api/grafana/folders [get, post]
/api/grafana/folders/{uid} [delete, get, put]
/api/grafana/folders/{uid}/hide [post]
/api/internal/otlp/validate [get, post]
/api/loki/aggregate [get]
/api/loki/filter [post]
/api/loki/label/{label}/values [get]
/api/loki/labels [get]
/api/loki/query [get]
/api/loki/query_instant [get]
/api/loki/search [post]
/api/loki/volume [get]
/api/resolver/analyze/config-template [get]
/api/resolver/analyze/jobs [get, post]
/api/resolver/analyze/jobs/{job_id} [get]
/api/resolver/analyze/jobs/{job_id}/result [get]
/api/resolver/anomalies/logs/bursts [post]
/api/resolver/anomalies/logs/patterns [post]
/api/resolver/anomalies/metrics [post]
/api/resolver/anomalies/traces [post]
/api/resolver/causal/bayesian [post]
/api/resolver/causal/granger [post]
/api/resolver/correlate [post]
/api/resolver/events/deployments [get]
/api/resolver/forecast/trajectory [post]
/api/resolver/ml/weights [get]
/api/resolver/ml/weights/feedback [post]
/api/resolver/ml/weights/reset [post]
/api/resolver/reports/{report_id} [delete, get]
/api/resolver/slo/burn [post]
/api/resolver/topology/blast-radius [post]
/api/system/metrics [get]
/api/system/ojo/releases [get]
/api/system/quotas [get]
/api/tempo/services [get]
/api/tempo/services/{service}/operations [get]
/api/tempo/traces/search [get]
/api/tempo/traces/{trace_id} [get]
/health [get]
/ready [get]
```

## Local Run & Verification

From repo root (recommended):

```bash
docker compose up -d watchdog
curl http://localhost:4319/health
curl http://localhost:4319/ready
```

To inspect full API schema:

- `watchdog/openapi.json`
- `watchdog/openapi.yaml`

## Related Docs

- Root system overview: [../README.md](../README.md)
- Deployment and hardening: [../DEPLOYMENT.md](../DEPLOYMENT.md)
- End-user operations: [../USER GUIDE.md](../USER%20GUIDE.md)
