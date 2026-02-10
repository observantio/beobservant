# BeObservant — Sales Pitch & Technical Analysis

## Elevator Pitch
BeObservant is a self-hosted, multi-tenant observability platform that unifies logs (Loki), traces (Tempo), and metrics (Mimir) with secure per-key OTLP ingestion, a management API, and a developer-friendly UI for key lifecycle and agent configuration. It enables secure, low-friction instrumentation for teams and customers while keeping tenant isolation, token revocation, and usage metering simple.

## One-liner for Sales
Secure, tenant-isolated observability — deploy in your environment or our managed offering, instrument easily with per-key OTLP tokens and get instant logs, traces, and metrics with predictable pricing.

---

## Problem We Solve
- Teams need unified visibility across logs, traces and metrics but want tenant isolation and safe onboarding for collectors.
- Raw organization keys in agents create a large blast radius if compromised.
- Operability and predictable cost control are difficult without per-tenant metering and token-level revocation.

## Our Solution
- Per-API-key OTLP tokens validated at an OTLP Gateway; agents never see raw org keys. Revoke a single token without impacting others.
- One-click OTEL agent YAML generation from UI with the gateway host and token embedded as `x-otlp-token`.
- Integrated full-stack: Loki (logs), Tempo (traces), Mimir (metrics), plus Grafana provisioning and a backend API for user & key management.

---

## Key Functionality
- API key lifecycle: create, enable/disable, set default, rotate, delete (server: `server/services/database_auth_service.py`, UI: `ui/src/pages/ApiKeyPage.jsx`).
- OTLP ingest flow: clients send telemetry to `otlp-gateway` using `x-otlp-token`; gateway maps token → tenant (`server/routers/gateway_router.py`).
- Agent config generation: UI builds agent YAML using gateway host constant (`ui/src/utils/constants.js`) and token (masked by default), with copy/download actions.
- Grafana provisioning: datasources pre-configured to use tenant-aware endpoints.
- Metering hooks: endpoints and DB model include `otlp_token` enabling per-token metrics.

---

## Security & Compliance
- Token-based ingress (per-API-key `otlp_token`) minimizes blast radius.
- Tokens can be backfilled and rotated (`database_auth_service.py`).
- Default secrets appear in `docker-compose.yml` for convenience; production must use secret stores (Vault, cloud secrets, k8s secrets).
- Recommendations:
  - Terminate TLS at OTLP Gateway and enforce TLS backend-to-backend.
  - Store secrets in a secure secret manager; remove defaults from `docker-compose.yml`.
  - Add audit logs for API key operations and token rotation events.
  - Add RBAC and SSO for UI and Grafana for enterprise customers.

---

## Architecture Overview
- Docker-compose orchestrated stack: `beobservant` API, `otlp-gateway` (Nginx), `otel-agent` (collector), `loki`, `tempo`, `mimir`, `grafana`.
- UI: React app with agent YAML generator and token UX.
- DB: Postgres storing users and API keys including `otlp_token` and indexing for token lookup.
- Gatekeeper: Nginx gateway or custom gateway validates `x-otlp-token` and injects `X-Scope-OrgID` for downstream services.

---

## Deployment Options
- Self-hosted (customer-managed): deploy via `docker-compose` or provide Helm/K8s manifests (recommended for production scale).
- Managed (vendor-managed): we run and operate the cluster for the customer with SLA, backups, and monitoring.

---

## Cost & Pricing Guidance
Billing model options:
- Base + usage (recommended): monthly base fee + ingest (GB/day) + storage (GB-month) + retention tiering.
- Per-tenant metering: charge based on combined usage of a tenant's `otlp_token`.

Example tiers (illustrative):
- Starter: $500/mo — up to 10GB/day ingest, 7d retention, community support.
- Growth: $2,000/mo — up to 100GB/day ingest, 30d retention, standard support.
- Enterprise: Custom — high ingest, long retention, SLA, security/compliance features, dedicated support.

Cost considerations:
- Mimir storage dominates cost — plan for object store and retention tiers.
- Loki and Tempo cost scale with retention and query rates.
- Offer data lifecycle policies: hot/cold tiering, archive to lower-cost object storage.

---

## Business Impact & ROI
- Faster incident response: unified logs/traces/metrics reduce MTTD/MTTR — direct operational savings.
- Lower security risk: per-token revocation reduces incident scope and lowers remediation cost.
- Monetization: platform can be sold as Managed SaaS or licensed Self-Hosted with support; upsell long-term retention and compliance support.

Quantitative example (conservative):
- If a customer reduces MTTR by 30% and spends average $200/hr on incident response across teams, saved hours across incidents can quickly justify platform subscription fees.

---

## Competitive Differentiators
- Per-key OTLP tokens and gateway-based mapping with token rotation — easy, secure onboarding.
- Full open-source stack integration; customers can self-host or buy managed service.
- Built-in UI for generating safe agent configs — reduces friction for engineers.

---

## Sales Playbook & Demo Script
1. Quick intro (1–2 mins): pain points — onboarding, keys, blast radius, unpredictable cost.
2. Live demo (5–7 mins):
   - Show `API Keys` page: create key, show masked OTLP token, Show/Hide, Copy.
   - Generate OTEL agent YAML and explain that the agent uses `x-otlp-token`. Mention that org key is not present.
   - Simulate revoke: rotate token and show that ingestion with old token stops while other tokens continue.
   - Open Grafana to run a query and show combined logs/traces/metrics.
3. Security & Ops (2–3 mins): token revocation, secrets advice, TLS.
4. Pricing & next steps (2–3 mins): propose PoC or pilot.

Sales assets to prepare:
- 1‑page pricing sheets for Self-hosted and Managed.
- A short security briefing and runbook for token compromise.
- A 10–15 minute recorded demo video.

---

## Common Objections & Responses
- "We already use hosted Grafana/Datadog": Position self-hosted for compliance, data residency, or cost predictability; or offer integration with existing tools.
- "How do you handle scale?": Recommend K8s and managed object storage for Mimir for production-scale; present managed offering for customers who prefer we operate it.
- "What if a token is leaked?": Revoke that token only; other tokens are unaffected. Show the UI and API for rotation.

---

## Tech Prerequisites & Runbook (Quick)
- Minimum production checklist:
  - Move secrets to a secret manager (Vault / cloud secrets / k8s secrets).
  - Configure TLS on `otlp-gateway` and internal services.
  - Use object storage (S3/GCS) with lifecycle policies for Mimir.
  - Run Grafana behind SSO and enable RBAC.
  - Add monitoring and alerting for ingestion/backpressure.

---

## Next Steps & Deliverables
- Provide a 30-day PoC plan: infra estimate, data retention, basic SLOs, onboarding steps.
- Create a one-page sales sheet and a 10–15 minute demo recording.
- Harden deployment: generate a secure `helm` chart and a production runbook.

---

## Files & Code References (useful for engineering follow-up)
- `docker-compose.yml` — deployment and default envs
- `ui/src/pages/ApiKeyPage.jsx` — token & YAML generation UI
- `ui/src/utils/constants.js` — UI constants (gateway host env var)
- `server/services/database_auth_service.py` — token generation/backfill
- `server/routers/gateway_router.py` — token validation and mapping
- `server/db_models.py` — `otlp_token` storage

---

If you want, I can now:
- Create a concise one-page sales sheet derived from this pitch.
- Draft an email outreach template and pricing tiers for leads.
- Generate a secure-deployment checklist and sample Helm manifests for production.

Which of these should I do next?
