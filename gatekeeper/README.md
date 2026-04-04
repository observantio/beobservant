<div align="center">

# Gatekeeeper

  <img src="../assets/shield.png" alt="Gatekeeper shield icon" width="150" />

  <p>
    <img src="https://img.shields.io/badge/Role-OTLP%20Gateway%20Auth-1f2937?style=flat-square" alt="Role" />
    <img src="https://img.shields.io/badge/Used%20by-Watchdog-0f766e?style=flat-square" alt="Used by Watchdog" />
    <img src="https://img.shields.io/badge/Protocol-OTLP-0ea5e9?style=flat-square" alt="Protocol" />
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
