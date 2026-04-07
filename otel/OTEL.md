# Running the OpenTelemetry Collector for Observantio

This document explains how to run the repository's OpenTelemetry Collector wrapper script.

## What it does

`otel/run_otel_collector.sh` installs or uses a local `otelcol-contrib` binary and loads the collector config from the `otel/configs/` directory.

The script expects the monitoring config file to be located at:

- `otel/configs/otelcollector.yaml`

## Get the OTLP token

In Watchdog, copy the OTLP token — not the tenant key. The token is only shown once, so regenerate it if it is not available in the UI.

## Run the collector

From the repository root, use:

```bash
bash otel/run_otel_collector.sh -t <MIMIR_OTLP_TOKEN>
```

Example:

```bash
bash otel/run_otel_collector.sh -t bo_....
```

## How it runs

The script installs `otelcol-contrib` if it is not yet available, then executes:

```bash
otelcol-contrib --config "$CONFIG_FILE"
```

## Notes

- You do not need to create a separate `otelcollector.yaml` file in the repo root.
- Do not mount directories onto the config file path; the script uses a regular file.
- If you need to update the collector config, edit `otel/configs/otelcollector.yaml`.

## Troubleshooting

- If the script reports that the config file is missing, confirm the path exists and is a regular file:

```bash
ls -l otel/configs/otelcollector.yaml
```

- If the file is missing or not readable, fix that before re-running the script.
