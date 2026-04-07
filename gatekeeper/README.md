<div align="center">

# Gatekeeeper

  <img src="../assets/shield.png" alt="Gatekeeper shield icon" width="150" />


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
</div>

Gatekeeper is Watchdog's gateway authorization service for OTLP ingest.
It receives auth checks from the gateway path, validates the token, confirms org scope,
and returns an allow/deny decision before telemetry reaches the backend stack.

In plain terms: Gatekeeper is the policy guard that keeps ingest secure,
tenant-aware, and consistent for logs, metrics, and traces.

## How Watchdog Uses Gatekeeper

1. A collector sends OTLP traffic with `x-otlp-token`.
2. Gateway auth calls Gatekeeper to validate token + org scope.
3. Gatekeeper returns the auth result and scoped context.
4. Only valid requests continue to Tempo, Loki, and Mimir.

## Local Tests

```bash
python -m pytest -q
```

If you commit from the repository root, `.pre-commit-config.yaml` runs this suite
alongside other service and UI checks.
