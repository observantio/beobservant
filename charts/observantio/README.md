<div align="center">

# Observantio Helm Chart

<img src="../../assets/kubernetes.png" alt="Kubernetes" width="120" />

<p>
  <a href="../../charts/observantio/installer.sh">
    <img src="https://img.shields.io/badge/Installer-Production-0ea5e9?style=flat-square&logo=kubernetes&logoColor=white" alt="Installer" />
  </a>
  <a href="../../charts/observantio/values-production.yaml">
    <img src="https://img.shields.io/badge/Profile-production-16a34a?style=flat-square" alt="Production Profile" />
  </a>
  <a href="../../charts/observantio/values-compact.yaml">
    <img src="https://img.shields.io/badge/Profile-compact-1f2937?style=flat-square" alt="Compact Profile" />
  </a>
</p>

<p>Simple production installer for Kubernetes with sane defaults.</p>

</div>

The same chart is also published in release assets as `observantio-${BUNDLE_VERSION}-helm-charts.tar.gz`. If you download that tarball, extract it and run `installer.sh` from the chart root.

## Quick Start

Run from repo root:

```bash
bash charts/observantio/installer.sh --profile production --foreground
```

What this does:
- Prompts for admin username, email, and password.
- Prepares secrets.
- Deploys the chart.
- Waits for rollout.
- Starts local port-forwards in foreground mode.

Use detached or no port-forward mode if preferred:

```bash
bash charts/observantio/installer.sh --profile production --detach
bash charts/observantio/installer.sh --profile production --no-port-forward
```

## Profiles

- `production`: Uses [`values-production.yaml`](values-production.yaml) and leaves TLS to the selected values files.
- `compact`: Uses production values plus [`values-compact.yaml`](values-compact.yaml) for smaller clusters, with TLS off in the bundled values.

Examples:

```bash
bash charts/observantio/installer.sh --profile production
bash charts/observantio/installer.sh --profile compact
```

## Install Model

The wrapper script is intentionally self-contained.

- It disables `externalSecrets` and creates or reuses a cluster secret for the app credentials.
- It generates the internal TLS secret when the selected profile needs it.
- It can also reuse an existing secret with `--existing-secret <name>` or skip secret management entirely with `--skip-secret-management`.

If you want the chart to consume ExternalSecrets directly, install with plain `helm` and your own values file instead of the wrapper script.

## Common Flags

- `--release <name>` set Helm release (default: `observantio-prod`)
- `--namespace <name>` set namespace (default: `observantio`)
- `--chart <path>` set chart path
- `--values <file>` add extra values file (repeatable)
- `--profile production|compact`
- `--existing-secret <name>` use existing app secret
- `--skip-secret-management` skip secret create/update
- `--run-checks` run post-deploy checks
- `--no-checks` skip post-deploy checks
- `--remove` uninstall release
- `--purge` uninstall and purge namespace PVC/PV data
- `--detach` detached port-forwards
- `--foreground` foreground port-forwards
- `--no-port-forward` disable port-forwards
- `-h`, `--help` show help

## Change Image Tags

Recommended approach: extra values file.

```yaml
# /tmp/observantio-image-overrides.yaml
observantio:
  image:
    repository: ghcr.io/observantio/watchdog
    tag: latest-build-20260414
notifier:
  image:
    repository: ghcr.io/observantio/notifier
    tag: latest-build-20260414
resolver:
  image:
    repository: ghcr.io/observantio/resolver
    tag: latest-build-20260414
```

```bash
bash charts/observantio/installer.sh \
  --profile production \
  --values /tmp/observantio-image-overrides.yaml
```

Notifier-only env override shortcut:

```bash
NOTIFIER_IMAGE_REPOSITORY=ghcr.io/observantio/notifier \
NOTIFIER_IMAGE_TAG=latest-build-20260414 \
bash charts/observantio/installer.sh --profile production
```

## Make It Yours

Start with `values-production.yaml`, then adapt for your environment:
- Resource requests/limits
- Replica counts and autoscaling
- Network policy rules
- TLS and secret management strategy
- Service exposure and ingress choices

Tip: keep your org-specific config in a separate values file and pass it with `--values`.

## Validate

Useful checks while iterating on the chart:

- `helm lint charts/observantio`
- `helm template demo charts/observantio -f charts/observantio/values-production.yaml`
- `helm template demo charts/observantio -f charts/observantio/values-compact.yaml`
- `kubectl get events -n observantio --sort-by=.lastTimestamp`
- `kubectl describe pod -n observantio <pod-name>`

## Cleanup

```bash
bash charts/observantio/installer.sh --remove
bash charts/observantio/installer.sh --purge
```
