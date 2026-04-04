<div align="center">

# Observantio Canary OTEL Guide

  <img src="../assets/scripts.png" alt="Observantio scripts icon" width="150" />

  <p>
    <img src="https://img.shields.io/badge/Purpose-Canary%20Telemetry-1f2937?style=flat-square" alt="Purpose" />
    <img src="https://img.shields.io/badge/Signals-Logs%20%7C%20Traces%20%7C%20Metrics-0f766e?style=flat-square" alt="Signals" />
    <img src="https://img.shields.io/badge/Collector-OTEL%20Agent-0ea5e9?style=flat-square" alt="Collector" />
  </p>
</div>

This `tests/` folder contains the root-level OTEL canary agent setup used to generate and forward **logs, traces, and metrics**.

## What This Canary Does

- Runs `otelcol-contrib` with [`tests/configs/otel-agent.yaml`](./configs/otel-agent.yaml).
- Generates traces using [`tests/traces.py`](./traces.py).
- Generates logs using [`tests/logs.py`](./logs.py).
- Ships host metrics via the OTEL `hostmetrics` receiver in the collector config.

## Main Entry Point

Use [`tests/start.sh`](./start.sh) to launch the collector and generators.

```bash
bash tests/start.sh
```

## Control Log and Trace Rate (`start.sh`)

`start.sh` already supports env-based tuning for traffic rate and volume. You can either:

- Export env vars before running `tests/start.sh`.
- Or update default values inside `tests/start.sh`.

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
bash tests/start.sh
```

## Create the Dashboard (Mimir + OTEL Template)

To visualize canary metrics/log behavior in Grafana:

1. Open Grafana and create/import a dashboard.
2. Choose the default datasource: **`Mimir`**.
3. Import the OTEL-native dashboard template provided in this repo:
   `tests/configs/grafana-high-cpu-systems-otel.json`.
4. Save the dashboard and verify panels populate while `tests/start.sh` is running.

## Related Files

- Collector config: [`tests/configs/otel-agent.yaml`](./configs/otel-agent.yaml)
- OTEL dashboard template: [`tests/configs/grafana-high-cpu-systems-otel.json`](./configs/grafana-high-cpu-systems-otel.json)
- Startup script: [`tests/start.sh`](./start.sh)
- Generators: [`tests/logs.py`](./logs.py), [`tests/traces.py`](./traces.py)
