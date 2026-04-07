<div align="center">

# Observantio UI

  <img src="public/wolf.png" alt="Observantio UI wolf icon" width="150" />

  <p>
    <a href="https://github.com/observantio/resolver">
      <img src="https://img.shields.io/badge/RCA-Resolver-7c3aed?style=flat-square" alt="Resolver" />
    </a>
    <a href="https://github.com/observantio/ojo">
      <img src="https://img.shields.io/badge/Telemetry-Ojo-0f766e?style=flat-square" alt="Ojo" />
    </a>
    <a href="https://github.com/observantio/notifier">
      <img src="https://img.shields.io/badge/Alerting-Notifier-1f2937?style=flat-square" alt="Notifier" />
    </a>
    <a href="https://github.com/observantio/watchdog/tree/main/gatekeeper">
      <img src="https://img.shields.io/badge/Security-Gatekeeper-0ea5e9?style=flat-square" alt="Gatekeeper" />
    </a>
  </p>
  <p>
    <a href="https://github.com/observantio/watchdog/blob/main/USER%20GUIDE.md">
      <img src="https://img.shields.io/badge/📘%20User%20Guide-Read%20Docs-16a34a?style=flat-square&logo=readthedocs&logoColor=white" alt="User Guide" />
    </a>
    <a href="https://github.com/observantio/watchdog/blob/main/DEPLOYMENT.md">
      <img src="https://img.shields.io/badge/🚀%20Deploy-Stack%20Guide-0284c7?style=flat-square&logo=docker&logoColor=white" alt="Deploy" />
    </a>
  </p>
</div>

The UI is the operator workspace for Watchdog.
It is where teams observe system health, investigate incidents, manage access, and run RCA workflows without jumping across disconnected tools.

## What This UI Does

- Provides one authenticated interface for logs, traces, dashboards, alerting, incidents, integrations, and RCA.
- Enforces permission-aware routing so users only see what they are allowed to access.
- Applies tenant/API-key context so queries and actions stay scoped to the correct organization.
- Connects to Watchdog, Notifier, and Resolver through the control plane model.

## Main Functional Areas

- `Dashboard`: status cards, activity summaries, and operational overview.
- `Logs` (`/loki`): LogQL queries, label discovery, filtering, and browsing.
- `Traces` (`/tempo`): trace search, span analysis, and dependency graph support.
- `RCA` (`/rca`): job creation, report review, ranked causes, and evidence views.
- `Alert Manager` (`/alertmanager`): active alerts, rules, silences, and rule import/testing.
- `Incidents` (`/incidents`): assignment, notes, lifecycle updates, and Jira-linked operations.
- `Grafana` (`/grafana`): controlled dashboard/datasource workflows through the auth model.
- `API Keys`, `Users`, `Groups`, `Integrations`, `Audit/Compliance`, `Docs`, `Quotas`, `Agents`.

## What You Can Try Out

1. Log in and switch theme modes to verify dark/light behavior.
2. Set an active API key scope, then run logs and traces queries.
3. Create or import alert rules, trigger alerts, and review incident creation flow.
4. Open RCA and run a job after telemetry exists.
5. Validate permission behavior by testing route visibility with different users/groups.

## Why This UI Is Useful

- Reduces context switching by combining observability, alert operations, and RCA in one place.
- Keeps security and tenancy boundaries visible during day-to-day operations.
- Makes onboarding easier for operators who need a practical workflow, not just backend primitives.
- Supports gradual adoption: start with logs/traces, then layer alerts, incidents, and RCA.

## Local Development

From the `ui` folder:

```bash
npm install
npm run dev
```

Useful scripts:

- `npm run build`
- `npm run test:run`
- `npm run lint`

Default local URL:

- `http://localhost:5173`

## Related Docs

- Root product README: [../README.md](../README.md)
- User guide: [../USER GUIDE.md](../USER%20GUIDE.md)
- Deployment guide: [../DEPLOYMENT.md](../DEPLOYMENT.md)
