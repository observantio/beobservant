<div align="center">

# Observantio Canary OTEL Guide

  <img src="../assets/star.png" alt="Observantio scripts icon" width="150" />

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

This `otel/` folder contains the root-level OTEL canary agent setup used to generate and forward **logs, traces, and metrics**.

For a simpler collector-only experience, including basic scraping and Ojo-compatible OTEL flow, see the root-level [`OTEL.md`](../OTEL.md) guide.

## What This Canary Does

- Runs `otelcol-contrib` with [`otel/configs/otel-agent.yaml`](./configs/otel-agent.yaml).
- Generates traces using [`otel/traces.py`](./traces.py).
- Generates logs using [`otel/logs.py`](./logs.py).
- Ships host metrics via the OTEL `hostmetrics` receiver in the collector config.

## Main Entry Point

Use [`otel/start.sh`](./start.sh) to launch the collector and generators.

```bash
bash otel/start.sh
```

## Control Log and Trace Rate (`start.sh`)

`start.sh` already supports env-based tuning for traffic rate and volume. You can either:

- Export env vars before running `otel/start.sh`.
- Or update default values inside `otel/start.sh`.

### Trace controls

- `TRACE_COUNT`: traces emitted per loop.
- `TRACE_PARALLEL`: concurrent trace workers.
- `TRACE_LOOPS`: number of loops (`0` means infinite).
- `TRACE_DELAY`: delay in seconds between trace launches.

### Log controls

- `LOG_COUNT`: logs emitted per loop.
- `LOG_PARALLEL`: concurrent log workers.
- `LOG_LOOPS`: number of loops (`0` means infinite).
- `LOG_DELAY`: delay in seconds between log launches.

### Generator sequencing

- `GENERATOR_START_DELAY`: delay between starting trace and log generators.

Example tuned run:

```bash
TRACE_COUNT=200 TRACE_PARALLEL=20 TRACE_LOOPS=0 TRACE_DELAY=0.01 \
LOG_COUNT=400 LOG_PARALLEL=30 LOG_LOOPS=0 LOG_DELAY=0.005 \
GENERATOR_START_DELAY=0.5 \
bash otel/start.sh
```

## Create the Dashboard (Mimir + OTEL Template)

To visualize canary metrics/log behavior in Grafana:

1. Open Grafana and create/import a dashboard.
2. Choose the default datasource: **`Mimir`**.
3. Import the OTEL-native dashboard template provided in this repo:
   `otel/configs/grafana-high-cpu-systems-otel.json`.
4. Save the dashboard and verify panels populate while `otel/start.sh` is running.

## Related Files

- Collector config: [`otel/configs/otel-agent.yaml`](./configs/otel-agent.yaml)
- Collector startup script: [`otel/start.sh`](./start.sh)
- Root OTEL guide: [`../OTEL.md`](../OTEL.md)
- Ojo config: [`otel/configs/ojo.yaml`](./configs/ojo.yaml)
- Generators: [`otel/logs.py`](./logs.py), [`otel/traces.py`](./traces.py)
