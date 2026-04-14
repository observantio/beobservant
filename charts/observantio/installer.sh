#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RELEASE_NAME="${RELEASE_NAME:-observantio-prod}"
NAMESPACE="${NAMESPACE:-observantio}"
CHART_PATH="${CHART_PATH:-${SCRIPT_DIR}}"
VALUES_FILE="${VALUES_FILE:-${SCRIPT_DIR}/values-production.yaml}"
COMPACT_VALUES_FILE="${COMPACT_VALUES_FILE:-${SCRIPT_DIR}/values-compact.yaml}"
INSTALL_PROFILE="${INSTALL_PROFILE:-production}" # production | compact
HELM_TIMEOUT="${HELM_TIMEOUT:-20m}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-600s}"
LOCAL_API_PORT="${LOCAL_API_PORT:-4319}"
API_FORWARD_PORT="${API_FORWARD_PORT:-$LOCAL_API_PORT}"
GRAFANA_PROXY_FORWARD_PORT="${GRAFANA_PROXY_FORWARD_PORT:-8080}"
UI_FORWARD_PORT="${UI_FORWARD_PORT:-5173}"
PORT_FORWARD_LOG_DIR="${PORT_FORWARD_LOG_DIR:-/tmp/observantio-port-forward}"
PORT_FORWARD_MODE="${PORT_FORWARD_MODE:-detached}" # detached | foreground | disabled
START_PORT_FORWARDS="${START_PORT_FORWARDS:-false}"
RUN_POST_DEPLOY_CHECKS="${RUN_POST_DEPLOY_CHECKS:-true}"
REUSE_EXISTING_SECRETS="${REUSE_EXISTING_SECRETS:-true}"
MANAGE_APP_SECRET="${MANAGE_APP_SECRET:-true}"
REMOVE_MODE="false"
PURGE_MODE="false"

APP_SECRET_NAME="${APP_SECRET_NAME:-}"
EXISTING_SECRET_NAME="${EXISTING_SECRET_NAME:-}"
INTERNAL_TLS_SECRET_NAME="${INTERNAL_TLS_SECRET_NAME:-}"

OBSERVANTIO_USERNAME="${OBSERVANTIO_USERNAME:-}"
OBSERVANTIO_EMAIL="${OBSERVANTIO_EMAIL:-}"
OBSERVANTIO_PASSWORD="${OBSERVANTIO_PASSWORD:-}"

POSTGRES_USER="${POSTGRES_USER:-watchdog}"
POSTGRES_DB="${POSTGRES_DB:-watchdog}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

OBSERVANTIO_USERNAME="${OBSERVANTIO_USERNAME:-}"
OBSERVANTIO_EMAIL="${OBSERVANTIO_EMAIL:-}"
OBSERVANTIO_PASSWORD="${OBSERVANTIO_PASSWORD:-}"

GRAFANA_USERNAME="${GRAFANA_USERNAME:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-}"
GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"

NOTIFIER_IMAGE_REPOSITORY="${NOTIFIER_IMAGE_REPOSITORY:-}"
NOTIFIER_IMAGE_TAG="${NOTIFIER_IMAGE_TAG:-}"
NOTIFIER_IMAGE_PULL_POLICY="${NOTIFIER_IMAGE_PULL_POLICY:-IfNotPresent}"

TEMP_API_PF_PID=""
TEMP_GATEKEEPER_PF_PID=""
API_PF_PID=""
GRAFANA_PF_PID=""
UI_PF_PID=""

JWT_PRIVATE_KEY=""
JWT_PUBLIC_KEY=""
JWT_SECRET_KEY=""
DEFAULT_OTLP_TOKEN=""
OTEL_OTLP_TOKEN=""
INBOUND_WEBHOOK_TOKEN=""
OTLP_INGEST_TOKEN=""
GATEWAY_TOKEN=""
GATEWAY_STATUS_TOKEN=""
NOTIFIER_TOKEN=""
RESOLVER_TOKEN=""
NOTIFIER_CONTEXT_SIGNING_KEY=""
NOTIFIER_CONTEXT_VERIFY_KEY=""
RESOLVER_CONTEXT_SIGNING_KEY=""
RESOLVER_CONTEXT_VERIFY_KEY=""
DATA_ENCRYPTION_KEY=""

ACTIVE_SECRET_NAME=""
OBSERVANTIO_SVC=""
NOTIFIER_SVC=""
RESOLVER_SVC=""
EFFECTIVE_PROFILE=""
CLUSTER_NODE_COUNT="0"
CLUSTER_ALLOCATABLE_CPU_M="0"
CLUSTER_ALLOCATABLE_MEMORY_MIB="0"
INTERNAL_TLS_REQUIRED="true"
GATEKEEPER_REQUIRED="true"

EXTRA_VALUES_FILES=()

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

random_hex() {
  openssl rand -hex "$1"
}

random_b64_32() {
  openssl rand -base64 32 | tr -d '\n'
}

is_valid_username() {
  local candidate="$1"
  [[ "$candidate" =~ ^[A-Za-z0-9._-]{3,64}$ ]]
}

is_valid_email() {
  local candidate="$1"
  [[ "$candidate" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]
}

prompt_admin_credentials() {
  if [[ ! -t 0 ]]; then
    [[ -n "$OBSERVANTIO_USERNAME" ]] || OBSERVANTIO_USERNAME="admin"
    [[ -n "$OBSERVANTIO_EMAIL" ]] || OBSERVANTIO_EMAIL="${OBSERVANTIO_USERNAME}@example.com"
    [[ -n "$OBSERVANTIO_PASSWORD" ]] || {
      echo "OBSERVANTIO_PASSWORD is required in non-interactive mode" >&2
      exit 1
    }
    return
  fi

  if [[ -z "$OBSERVANTIO_USERNAME" ]]; then
    while true; do
      read -r -p "Observantio admin username [admin]: " OBSERVANTIO_USERNAME
      OBSERVANTIO_USERNAME="${OBSERVANTIO_USERNAME:-admin}"
      if is_valid_username "$OBSERVANTIO_USERNAME"; then
        break
      fi
      echo "Username must be 3-64 chars using letters, numbers, dot, underscore, or hyphen."
    done
  fi

  if [[ -z "$OBSERVANTIO_EMAIL" ]]; then
    local email_default
    email_default="${OBSERVANTIO_USERNAME}@example.com"
    while true; do
      read -r -p "Observantio admin email [${email_default}]: " OBSERVANTIO_EMAIL
      OBSERVANTIO_EMAIL="${OBSERVANTIO_EMAIL:-$email_default}"
      if is_valid_email "$OBSERVANTIO_EMAIL"; then
        break
      fi
      echo "Please enter a valid email address."
    done
  fi

  if [[ -z "$OBSERVANTIO_PASSWORD" ]]; then
    local password_confirm
    while true; do
      read -r -s -p "Observantio admin password (min 16 chars): " OBSERVANTIO_PASSWORD
      echo
      [[ ${#OBSERVANTIO_PASSWORD} -ge 16 ]] || {
        echo "Password too short for production baseline."
        continue
      }

      read -r -s -p "Confirm admin password: " password_confirm
      echo
      if [[ "$OBSERVANTIO_PASSWORD" != "$password_confirm" ]]; then
        echo "Passwords do not match. Please try again."
        OBSERVANTIO_PASSWORD=""
        continue
      fi
      break
    done
  fi
}

secret_key_or_empty() {
  local secret_name="$1"
  local key="$2"
  kubectl -n "$NAMESPACE" get secret "$secret_name" -o "jsonpath={.data.${key}}" 2>/dev/null | base64 -d 2>/dev/null || true
}

detect_cluster_capacity() {
  local nodes_payload
  local summary
  nodes_payload="$(kubectl get nodes -o json)"
  summary="$(python3 - "$nodes_payload" <<'PY'
import json
import re
import sys


def cpu_to_m(value: str) -> int:
    value = value.strip()
    if value.endswith("m"):
        return int(float(value[:-1]))
    return int(float(value) * 1000)


def mem_to_mib(value: str) -> int:
    value = value.strip()
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)([A-Za-z]+)?$", value)
    if not match:
        raise ValueError(f"unsupported memory quantity: {value}")
    number = float(match.group(1))
    unit = match.group(2) or ""

    binary = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
        "Pi": 1024 * 1024 * 1024,
        "Ei": 1024 * 1024 * 1024 * 1024,
    }
    decimal = {
        "K": 1000 / 1024 / 1024,
        "M": 1000**2 / 1024 / 1024,
        "G": 1000**3 / 1024 / 1024,
        "T": 1000**4 / 1024 / 1024,
        "P": 1000**5 / 1024 / 1024,
        "E": 1000**6 / 1024 / 1024,
    }

    if unit in binary:
        return int(number * binary[unit])
    if unit in decimal:
        return int(number * decimal[unit])
    if unit == "":
        return int(number / (1024 * 1024))
    raise ValueError(f"unsupported memory unit: {unit}")


payload = json.loads(sys.argv[1])
nodes = payload.get("items", [])
total_cpu_m = 0
total_mem_mib = 0
for node in nodes:
    allocatable = (node.get("status") or {}).get("allocatable") or {}
    total_cpu_m += cpu_to_m(str(allocatable.get("cpu", "0")))
    total_mem_mib += mem_to_mib(str(allocatable.get("memory", "0")))

print(f"{len(nodes)},{total_cpu_m},{total_mem_mib}")
PY
)"

  IFS=',' read -r CLUSTER_NODE_COUNT CLUSTER_ALLOCATABLE_CPU_M CLUSTER_ALLOCATABLE_MEMORY_MIB <<<"$summary"
}

select_install_profile() {
  case "$INSTALL_PROFILE" in
    production|compact) ;;
    *)
      echo "Invalid profile: $INSTALL_PROFILE (expected production|compact)" >&2
      exit 1
      ;;
  esac

  detect_cluster_capacity
  EFFECTIVE_PROFILE="$INSTALL_PROFILE"

  if [[ "$EFFECTIVE_PROFILE" == "compact" ]] && [[ ! -f "$COMPACT_VALUES_FILE" ]]; then
    echo "Compact profile selected but values file not found: $COMPACT_VALUES_FILE" >&2
    exit 1
  fi

  # TLS and gatekeeper are now profile-driven through values files.
  INTERNAL_TLS_REQUIRED="false"
  GATEKEEPER_REQUIRED="false"

  echo "Install profile: ${EFFECTIVE_PROFILE} (requested=${INSTALL_PROFILE}; allocatable=${CLUSTER_ALLOCATABLE_CPU_M}m CPU, ${CLUSTER_ALLOCATABLE_MEMORY_MIB}Mi memory, nodes=${CLUSTER_NODE_COUNT})"
}

cleanup() {
  if [[ -n "$TEMP_API_PF_PID" ]]; then kill "$TEMP_API_PF_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "$TEMP_GATEKEEPER_PF_PID" ]]; then kill "$TEMP_GATEKEEPER_PF_PID" >/dev/null 2>&1 || true; fi

  if [[ "$PORT_FORWARD_MODE" == "foreground" ]]; then
    if [[ -n "$API_PF_PID" ]]; then kill "$API_PF_PID" >/dev/null 2>&1 || true; fi
    if [[ -n "$GRAFANA_PF_PID" ]]; then kill "$GRAFANA_PF_PID" >/dev/null 2>&1 || true; fi
    if [[ -n "$UI_PF_PID" ]]; then kill "$UI_PF_PID" >/dev/null 2>&1 || true; fi
  fi
}
trap cleanup EXIT

usage() {
  cat <<USAGE
Production installer for Observantio Helm chart.

Usage:
  bash charts/observantio/installer.sh [options]

Options:
  --release <name>         Helm release name (default: ${RELEASE_NAME})
  --namespace <name>       Kubernetes namespace (default: ${NAMESPACE})
  --chart <path>           Chart path (default: ${CHART_PATH})
  --values <file>          Additional values file (repeatable)
  --profile <mode>         Install profile: production|compact (default: ${INSTALL_PROFILE})
  --existing-secret <name> Use existing app secret and skip app secret generation
  --skip-secret-management Do not create/update app secret
  --remove                 Uninstall release
  --purge                  Uninstall and fully remove namespace PVC/PV assets
  --run-checks             Run post-deploy checks (default)
  --no-checks              Skip post-deploy checks
  --detach                 Start final port-forwards in detached mode
  --foreground             Start final port-forwards in foreground mode
  --no-port-forward        Do not start final port-forwards
  -h, --help               Show help

Environment knobs:
  OBSERVANTIO_USERNAME / OBSERVANTIO_EMAIL / OBSERVANTIO_PASSWORD
  REUSE_EXISTING_SECRETS=true|false
  INSTALL_PROFILE=production|compact
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release) RELEASE_NAME="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --chart) CHART_PATH="$2"; shift 2 ;;
    --values) EXTRA_VALUES_FILES+=("$2"); shift 2 ;;
    --profile) INSTALL_PROFILE="$2"; shift 2 ;;
    --existing-secret) EXISTING_SECRET_NAME="$2"; MANAGE_APP_SECRET="false"; shift 2 ;;
    --skip-secret-management) MANAGE_APP_SECRET="false"; shift ;;
    --remove) REMOVE_MODE="true"; shift ;;
    --purge) PURGE_MODE="true"; REMOVE_MODE="true"; shift ;;
    --run-checks) RUN_POST_DEPLOY_CHECKS="true"; shift ;;
    --no-checks) RUN_POST_DEPLOY_CHECKS="false"; shift ;;
    --detach) START_PORT_FORWARDS="true"; PORT_FORWARD_MODE="detached"; shift ;;
    --foreground) START_PORT_FORWARDS="true"; PORT_FORWARD_MODE="foreground"; shift ;;
    --no-port-forward) START_PORT_FORWARDS="false"; PORT_FORWARD_MODE="disabled"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$APP_SECRET_NAME" ]]; then
  APP_SECRET_NAME="${RELEASE_NAME}-observantio-secrets"
fi
if [[ -z "$INTERNAL_TLS_SECRET_NAME" ]]; then
  INTERNAL_TLS_SECRET_NAME="${RELEASE_NAME}-observantio-internal-tls"
fi
if [[ -n "$EXISTING_SECRET_NAME" ]]; then
  ACTIVE_SECRET_NAME="$EXISTING_SECRET_NAME"
else
  ACTIVE_SECRET_NAME="$APP_SECRET_NAME"
fi

CHART_PATH="$(cd "$CHART_PATH" && pwd)"
if [[ ! -f "$CHART_PATH/Chart.yaml" ]]; then
  echo "Chart path does not look valid: $CHART_PATH" >&2
  exit 1
fi

for cmd in kubectl helm openssl awk sed grep curl base64 mktemp python3; do
  require_cmd "$cmd"
done

kubectl cluster-info >/dev/null

if [[ "$REMOVE_MODE" == "true" ]]; then
  echo "Uninstalling release=${RELEASE_NAME} namespace=${NAMESPACE}"
  helm -n "$NAMESPACE" uninstall "$RELEASE_NAME" >/dev/null 2>&1 || true

  if [[ "$PURGE_MODE" == "true" ]]; then
    echo "Purging namespace and persistent data for namespace=${NAMESPACE}"
    if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
      kubectl -n "$NAMESPACE" delete pvc --all --wait=false >/dev/null 2>&1 || true
      kubectl get pv -o custom-columns=NAME:.metadata.name,NS:.spec.claimRef.namespace --no-headers 2>/dev/null \
        | awk -v ns="$NAMESPACE" '$2==ns{print $1}' \
        | while read -r pv; do
            [[ -n "$pv" ]] && kubectl delete pv "$pv" --wait=false >/dev/null 2>&1 || true
          done
      kubectl delete ns "$NAMESPACE" --wait=true --timeout=300s >/dev/null 2>&1 || true
    fi
  fi

  echo "Release removal complete."
  exit 0
fi

if [[ -z "$OBSERVANTIO_PASSWORD" ]]; then
  prompt_admin_credentials
fi

if [[ -z "$OBSERVANTIO_EMAIL" || -z "$OBSERVANTIO_USERNAME" ]]; then
  prompt_admin_credentials
fi

if [[ ${#OBSERVANTIO_PASSWORD} -lt 16 ]]; then
  echo "OBSERVANTIO_PASSWORD must be at least 16 characters for production installer." >&2
  exit 1
fi

if [[ -z "$OBSERVANTIO_EMAIL" ]]; then
  OBSERVANTIO_EMAIL="${OBSERVANTIO_USERNAME}@example.com"
fi

if ! is_valid_username "$OBSERVANTIO_USERNAME"; then
  echo "OBSERVANTIO_USERNAME must be 3-64 chars using letters, numbers, dot, underscore, or hyphen." >&2
  exit 1
fi

if ! is_valid_email "$OBSERVANTIO_EMAIL"; then
  echo "OBSERVANTIO_EMAIL must be a valid email address." >&2
  exit 1
fi

if ! kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
  kubectl create ns "$NAMESPACE" >/dev/null
fi

select_install_profile

OBSERVANTIO_SVC="${RELEASE_NAME}-observantio-observantio"
NOTIFIER_SVC="${RELEASE_NAME}-observantio-notifier"
RESOLVER_SVC="${RELEASE_NAME}-observantio-resolver"

load_existing_app_secret_values() {
  local secret_name="$1"

  POSTGRES_USER="$(secret_key_or_empty "$secret_name" POSTGRES_USER)"
  POSTGRES_PASSWORD="$(secret_key_or_empty "$secret_name" POSTGRES_PASSWORD)"
  POSTGRES_DB="$(secret_key_or_empty "$secret_name" POSTGRES_DB)"

  JWT_PRIVATE_KEY="$(secret_key_or_empty "$secret_name" JWT_PRIVATE_KEY)"
  JWT_PUBLIC_KEY="$(secret_key_or_empty "$secret_name" JWT_PUBLIC_KEY)"
  JWT_SECRET_KEY="$(secret_key_or_empty "$secret_name" JWT_SECRET_KEY)"
  DATA_ENCRYPTION_KEY="$(secret_key_or_empty "$secret_name" DATA_ENCRYPTION_KEY)"

  NOTIFIER_TOKEN="$(secret_key_or_empty "$secret_name" NOTIFIER_SERVICE_TOKEN)"
  RESOLVER_TOKEN="$(secret_key_or_empty "$secret_name" RESOLVER_SERVICE_TOKEN)"
  GATEWAY_TOKEN="$(secret_key_or_empty "$secret_name" GATEWAY_INTERNAL_SERVICE_TOKEN)"
  GATEWAY_STATUS_TOKEN="$(secret_key_or_empty "$secret_name" GATEWAY_STATUS_OTLP_TOKEN)"

  DEFAULT_OTLP_TOKEN="$(secret_key_or_empty "$secret_name" DEFAULT_OTLP_TOKEN)"
  OTEL_OTLP_TOKEN="$(secret_key_or_empty "$secret_name" OTEL_OTLP_TOKEN)"
  INBOUND_WEBHOOK_TOKEN="$(secret_key_or_empty "$secret_name" INBOUND_WEBHOOK_TOKEN)"
  OTLP_INGEST_TOKEN="$(secret_key_or_empty "$secret_name" OTLP_INGEST_TOKEN)"

  NOTIFIER_CONTEXT_SIGNING_KEY="$(secret_key_or_empty "$secret_name" NOTIFIER_CONTEXT_SIGNING_KEY)"
  NOTIFIER_CONTEXT_VERIFY_KEY="$(secret_key_or_empty "$secret_name" NOTIFIER_CONTEXT_VERIFY_KEY)"
  RESOLVER_CONTEXT_SIGNING_KEY="$(secret_key_or_empty "$secret_name" RESOLVER_CONTEXT_SIGNING_KEY)"
  RESOLVER_CONTEXT_VERIFY_KEY="$(secret_key_or_empty "$secret_name" RESOLVER_CONTEXT_VERIFY_KEY)"

  GRAFANA_USERNAME="$(secret_key_or_empty "$secret_name" GRAFANA_USERNAME)"
  GRAFANA_PASSWORD="$(secret_key_or_empty "$secret_name" GRAFANA_PASSWORD)"
  GRAFANA_API_KEY="$(secret_key_or_empty "$secret_name" GRAFANA_API_KEY)"
}

generate_missing_app_secret_values() {
  if [[ -z "$JWT_PRIVATE_KEY" || -z "$JWT_PUBLIC_KEY" ]]; then
    JWT_PRIVATE_KEY="$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 2>/dev/null)"
    JWT_PUBLIC_KEY="$(printf '%s' "$JWT_PRIVATE_KEY" | openssl rsa -pubout 2>/dev/null)"
  fi

  POSTGRES_USER="${POSTGRES_USER:-watchdog}"
  POSTGRES_DB="${POSTGRES_DB:-watchdog}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pg_$(random_hex 16)}"

  JWT_SECRET_KEY="${JWT_SECRET_KEY:-jwt_$(random_hex 24)}"
  DATA_ENCRYPTION_KEY="${DATA_ENCRYPTION_KEY:-$(random_b64_32)}"

  NOTIFIER_TOKEN="${NOTIFIER_TOKEN:-svc_notifier_$(random_hex 16)}"
  RESOLVER_TOKEN="${RESOLVER_TOKEN:-svc_resolver_$(random_hex 16)}"
  GATEWAY_TOKEN="${GATEWAY_TOKEN:-svc_gateway_$(random_hex 16)}"
  GATEWAY_STATUS_TOKEN="${GATEWAY_STATUS_TOKEN:-svc_status_$(random_hex 16)}"

  DEFAULT_OTLP_TOKEN="${DEFAULT_OTLP_TOKEN:-otlp_$(random_hex 16)}"
  OTEL_OTLP_TOKEN="${OTEL_OTLP_TOKEN:-$DEFAULT_OTLP_TOKEN}"
  INBOUND_WEBHOOK_TOKEN="${INBOUND_WEBHOOK_TOKEN:-wh_$(random_hex 16)}"
  OTLP_INGEST_TOKEN="${OTLP_INGEST_TOKEN:-ingest_$(random_hex 16)}"

  NOTIFIER_CONTEXT_SIGNING_KEY="${NOTIFIER_CONTEXT_SIGNING_KEY:-ctx_notifier_$(random_hex 16)}"
  NOTIFIER_CONTEXT_VERIFY_KEY="${NOTIFIER_CONTEXT_VERIFY_KEY:-$NOTIFIER_CONTEXT_SIGNING_KEY}"
  RESOLVER_CONTEXT_SIGNING_KEY="${RESOLVER_CONTEXT_SIGNING_KEY:-ctx_resolver_$(random_hex 16)}"
  RESOLVER_CONTEXT_VERIFY_KEY="${RESOLVER_CONTEXT_VERIFY_KEY:-$RESOLVER_CONTEXT_SIGNING_KEY}"

  GRAFANA_USERNAME="${GRAFANA_USERNAME:-admin}"
  GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-grafana_$(random_hex 24)}"
}

apply_app_secret() {
  local secret_name="$1"
  local tmpdir
  tmpdir="$(mktemp -d)"

  write_secret_file() {
    local key="$1"
    local value="$2"
    printf '%s' "$value" >"${tmpdir}/${key}"
  }

  write_secret_file POSTGRES_USER "$POSTGRES_USER"
  write_secret_file POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
  write_secret_file POSTGRES_DB "$POSTGRES_DB"
  write_secret_file JWT_SECRET_KEY "$JWT_SECRET_KEY"
  write_secret_file JWT_PRIVATE_KEY "$JWT_PRIVATE_KEY"
  write_secret_file JWT_PUBLIC_KEY "$JWT_PUBLIC_KEY"
  write_secret_file DATA_ENCRYPTION_KEY "$DATA_ENCRYPTION_KEY"
  write_secret_file DEFAULT_OTLP_TOKEN "$DEFAULT_OTLP_TOKEN"
  write_secret_file OTEL_OTLP_TOKEN "$OTEL_OTLP_TOKEN"
  write_secret_file INBOUND_WEBHOOK_TOKEN "$INBOUND_WEBHOOK_TOKEN"
  write_secret_file OTLP_INGEST_TOKEN "$OTLP_INGEST_TOKEN"
  write_secret_file GATEWAY_INTERNAL_SERVICE_TOKEN "$GATEWAY_TOKEN"
  write_secret_file GATEWAY_STATUS_OTLP_TOKEN "$GATEWAY_STATUS_TOKEN"
  write_secret_file NOTIFIER_SERVICE_TOKEN "$NOTIFIER_TOKEN"
  write_secret_file NOTIFIER_EXPECTED_SERVICE_TOKEN "$NOTIFIER_TOKEN"
  write_secret_file NOTIFIER_CONTEXT_SIGNING_KEY "$NOTIFIER_CONTEXT_SIGNING_KEY"
  write_secret_file NOTIFIER_CONTEXT_VERIFY_KEY "$NOTIFIER_CONTEXT_VERIFY_KEY"
  write_secret_file RESOLVER_SERVICE_TOKEN "$RESOLVER_TOKEN"
  write_secret_file RESOLVER_EXPECTED_SERVICE_TOKEN "$RESOLVER_TOKEN"
  write_secret_file RESOLVER_CONTEXT_SIGNING_KEY "$RESOLVER_CONTEXT_SIGNING_KEY"
  write_secret_file RESOLVER_CONTEXT_VERIFY_KEY "$RESOLVER_CONTEXT_VERIFY_KEY"
  write_secret_file GRAFANA_USERNAME "$GRAFANA_USERNAME"
  write_secret_file GRAFANA_PASSWORD "$GRAFANA_PASSWORD"
  write_secret_file GRAFANA_API_KEY "$GRAFANA_API_KEY"

  kubectl -n "$NAMESPACE" create secret generic "$secret_name" \
    --from-file=POSTGRES_USER="${tmpdir}/POSTGRES_USER" \
    --from-file=POSTGRES_PASSWORD="${tmpdir}/POSTGRES_PASSWORD" \
    --from-file=POSTGRES_DB="${tmpdir}/POSTGRES_DB" \
    --from-file=JWT_SECRET_KEY="${tmpdir}/JWT_SECRET_KEY" \
    --from-file=JWT_PRIVATE_KEY="${tmpdir}/JWT_PRIVATE_KEY" \
    --from-file=JWT_PUBLIC_KEY="${tmpdir}/JWT_PUBLIC_KEY" \
    --from-file=DATA_ENCRYPTION_KEY="${tmpdir}/DATA_ENCRYPTION_KEY" \
    --from-file=DEFAULT_OTLP_TOKEN="${tmpdir}/DEFAULT_OTLP_TOKEN" \
    --from-file=OTEL_OTLP_TOKEN="${tmpdir}/OTEL_OTLP_TOKEN" \
    --from-file=INBOUND_WEBHOOK_TOKEN="${tmpdir}/INBOUND_WEBHOOK_TOKEN" \
    --from-file=OTLP_INGEST_TOKEN="${tmpdir}/OTLP_INGEST_TOKEN" \
    --from-file=GATEWAY_INTERNAL_SERVICE_TOKEN="${tmpdir}/GATEWAY_INTERNAL_SERVICE_TOKEN" \
    --from-file=GATEWAY_STATUS_OTLP_TOKEN="${tmpdir}/GATEWAY_STATUS_OTLP_TOKEN" \
    --from-file=NOTIFIER_SERVICE_TOKEN="${tmpdir}/NOTIFIER_SERVICE_TOKEN" \
    --from-file=NOTIFIER_EXPECTED_SERVICE_TOKEN="${tmpdir}/NOTIFIER_EXPECTED_SERVICE_TOKEN" \
    --from-file=NOTIFIER_CONTEXT_SIGNING_KEY="${tmpdir}/NOTIFIER_CONTEXT_SIGNING_KEY" \
    --from-file=NOTIFIER_CONTEXT_VERIFY_KEY="${tmpdir}/NOTIFIER_CONTEXT_VERIFY_KEY" \
    --from-file=RESOLVER_SERVICE_TOKEN="${tmpdir}/RESOLVER_SERVICE_TOKEN" \
    --from-file=RESOLVER_EXPECTED_SERVICE_TOKEN="${tmpdir}/RESOLVER_EXPECTED_SERVICE_TOKEN" \
    --from-file=RESOLVER_CONTEXT_SIGNING_KEY="${tmpdir}/RESOLVER_CONTEXT_SIGNING_KEY" \
    --from-file=RESOLVER_CONTEXT_VERIFY_KEY="${tmpdir}/RESOLVER_CONTEXT_VERIFY_KEY" \
    --from-file=GRAFANA_USERNAME="${tmpdir}/GRAFANA_USERNAME" \
    --from-file=GRAFANA_PASSWORD="${tmpdir}/GRAFANA_PASSWORD" \
    --from-file=GRAFANA_API_KEY="${tmpdir}/GRAFANA_API_KEY" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null

  rm -rf "$tmpdir"
}

ensure_application_secret() {
  if [[ "$MANAGE_APP_SECRET" == "false" ]]; then
    if [[ -z "$EXISTING_SECRET_NAME" ]]; then
      echo "--skip-secret-management requires --existing-secret <name>" >&2
      exit 1
    fi
    kubectl -n "$NAMESPACE" get secret "$EXISTING_SECRET_NAME" >/dev/null
    ACTIVE_SECRET_NAME="$EXISTING_SECRET_NAME"
    load_existing_app_secret_values "$ACTIVE_SECRET_NAME"
    return
  fi

  ACTIVE_SECRET_NAME="$APP_SECRET_NAME"

  if [[ "$REUSE_EXISTING_SECRETS" == "true" ]] && kubectl -n "$NAMESPACE" get secret "$ACTIVE_SECRET_NAME" >/dev/null 2>&1; then
    load_existing_app_secret_values "$ACTIVE_SECRET_NAME"
  fi

  generate_missing_app_secret_values
  apply_app_secret "$ACTIVE_SECRET_NAME"
}

ensure_internal_tls_secret() {
  if [[ "$REUSE_EXISTING_SECRETS" == "true" ]] && kubectl -n "$NAMESPACE" get secret "$INTERNAL_TLS_SECRET_NAME" >/dev/null 2>&1; then
    local missing
    local secret_payload
    secret_payload="$(kubectl -n "$NAMESPACE" get secret "$INTERNAL_TLS_SECRET_NAME" -o json)"
    missing="$(python3 - "$secret_payload" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
keys = set((payload.get("data") or {}).keys())
required = {
    "ca.crt",
    "observantio.crt",
    "observantio.key",
    "notifier.crt",
    "notifier.key",
    "resolver.crt",
    "resolver.key",
}
missing = sorted(required - keys)
print(",".join(missing))
PY
)"
    if [[ -z "$missing" ]]; then
      return
    fi
    echo "Existing internal TLS secret is missing keys (${missing}); regenerating..."
  fi

  local tmpdir ca_key ca_crt
  tmpdir="$(mktemp -d)"
  ca_key="${tmpdir}/ca.key"
  ca_crt="${tmpdir}/ca.crt"

  openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
    -keyout "$ca_key" -out "$ca_crt" \
    -subj "/CN=observantio-internal-ca" >/dev/null 2>&1

  make_cert() {
    local name="$1"
    local svc="$2"
    local key="${tmpdir}/${name}.key"
    local csr="${tmpdir}/${name}.csr"
    local crt="${tmpdir}/${name}.crt"
    local ext="${tmpdir}/${name}.ext"

    cat >"$ext" <<EXT
subjectAltName=DNS:${svc},DNS:${svc}.${NAMESPACE},DNS:${svc}.${NAMESPACE}.svc,DNS:${svc}.${NAMESPACE}.svc.cluster.local
extendedKeyUsage=serverAuth
EXT

    # Keep CN short enough for OpenSSL/X.509 limits; full service names are in SAN.
    openssl req -new -newkey rsa:2048 -nodes -keyout "$key" -out "$csr" \
      -subj "/CN=${name}" >/dev/null 2>&1
    openssl x509 -req -in "$csr" -CA "$ca_crt" -CAkey "$ca_key" -CAcreateserial \
      -out "$crt" -days 365 -extfile "$ext" >/dev/null 2>&1
  }

  make_cert observantio "$OBSERVANTIO_SVC"
  make_cert notifier "$NOTIFIER_SVC"
  make_cert resolver "$RESOLVER_SVC"

  kubectl -n "$NAMESPACE" create secret generic "$INTERNAL_TLS_SECRET_NAME" \
    --from-file=ca.crt="${tmpdir}/ca.crt" \
    --from-file=observantio.crt="${tmpdir}/observantio.crt" \
    --from-file=observantio.key="${tmpdir}/observantio.key" \
    --from-file=notifier.crt="${tmpdir}/notifier.crt" \
    --from-file=notifier.key="${tmpdir}/notifier.key" \
    --from-file=resolver.crt="${tmpdir}/resolver.crt" \
    --from-file=resolver.key="${tmpdir}/resolver.key" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null

  rm -rf "$tmpdir"
}

wait_ready_deployment() {
  local deployment="$1"
  if kubectl -n "$NAMESPACE" get deployment "$deployment" >/dev/null 2>&1; then
    if ! kubectl -n "$NAMESPACE" rollout status deployment "$deployment" --timeout="$ROLLOUT_TIMEOUT"; then
      echo "Rollout failed for deployment/${deployment}. Recent pod state and events:" >&2
      kubectl -n "$NAMESPACE" get pods -l "app.kubernetes.io/instance=${RELEASE_NAME}" -o wide >&2 || true
      kubectl -n "$NAMESPACE" describe deployment "$deployment" >&2 || true
      kubectl -n "$NAMESPACE" get events --sort-by=.lastTimestamp | tail -n 60 >&2 || true
      exit 1
    fi
  fi
}

fail_fast_if_tls_requested_but_unsupported_images() {
  local payload
  payload="$(kubectl -n "$NAMESPACE" get deploy \
    "$OBSERVANTIO_SVC" \
    "$NOTIFIER_SVC" \
    "$RESOLVER_SVC" \
    -o json 2>/dev/null || true)"

  [[ -n "$payload" ]] || return 0

  python3 - "$payload" <<'PY'
import json
import sys

doc = json.loads(sys.argv[1])
items = doc.get("items", [])

checks = [
    ("observantio", "SSL_ENABLED"),
    ("notifier", "NOTIFIER_SSL_ENABLED"),
    ("resolver", "RESOLVER_SSL_ENABLED"),
]

problems = []
for item in items:
    name = item.get("metadata", {}).get("name", "")
    containers = item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        continue
    c = containers[0]
    image = str(c.get("image", ""))
    env_map = {str(e.get("name", "")): str(e.get("value", "")) for e in c.get("env", [])}
    for service_name, env_key in checks:
        if service_name in name:
            tls_on = env_map.get(env_key, "").strip().lower() in {"1", "true", "yes", "on"}
            if tls_on and (":v0.0.3" in image or image.endswith("@sha256:7b4a02ed425ce9b79f7e445f3549a79f89a443ad64961e4d4db9ed8a5a89c6e8") or image.endswith("@sha256:2bc49a816d6a54f2f53d799f775ab46420a240d91d462031831d995640996650")):
                problems.append((service_name, image, env_key))

if problems:
    print("TLS is enabled but one or more services are using older images without runtime TLS support:", file=sys.stderr)
    for service_name, image, env_key in problems:
        print(f"  - {service_name}: image={image} with {env_key}=true", file=sys.stderr)
    print("", file=sys.stderr)
    print("Use TLS-capable image tags (newer than v0.0.3) for observantio/notifier/resolver, or disable TLS in values.", file=sys.stderr)
    sys.exit(2)
PY
}

get_ready_pod_name() {
  local component="$1"
  kubectl -n "$NAMESPACE" get pods -l "app.kubernetes.io/component=${component}" \
    -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" "}{range .status.conditions[?(@.type=="Ready")]}{.status}{end}{"\n"}{end}' 2>/dev/null \
    | awk '$2=="Running" && $3=="True" {print $1; exit}'
}

verify_service_token_alignment() {
  local watchdog_pod="$1"
  local notifier_pod="$2"
  local resolver_pod="$3"

  local wd_notifier_sha wd_resolver_sha no_expected_sha re_expected_sha
  wd_notifier_sha="$(kubectl -n "$NAMESPACE" exec "$watchdog_pod" -- sh -lc 'v=$(printenv NOTIFIER_SERVICE_TOKEN||true); printf %s "$v" | sha256sum | cut -d" " -f1')"
  wd_resolver_sha="$(kubectl -n "$NAMESPACE" exec "$watchdog_pod" -- sh -lc 'v=$(printenv RESOLVER_SERVICE_TOKEN||true); printf %s "$v" | sha256sum | cut -d" " -f1')"
  no_expected_sha="$(kubectl -n "$NAMESPACE" exec "$notifier_pod" -- sh -lc 'v=$(printenv NOTIFIER_EXPECTED_SERVICE_TOKEN||true); printf %s "$v" | sha256sum | cut -d" " -f1')"
  re_expected_sha="$(kubectl -n "$NAMESPACE" exec "$resolver_pod" -- sh -lc 'v=$(printenv RESOLVER_EXPECTED_SERVICE_TOKEN||true); printf %s "$v" | sha256sum | cut -d" " -f1')"

  [[ "$wd_notifier_sha" == "$no_expected_sha" ]] || {
    echo "Notifier token mismatch between observantio and notifier" >&2
    exit 1
  }
  [[ "$wd_resolver_sha" == "$re_expected_sha" ]] || {
    echo "Resolver token mismatch between observantio and resolver" >&2
    exit 1
  }
}

enforce_admin_with_mfa_setup() {
  local watchdog_pod="$1"

  kubectl -n "$NAMESPACE" exec -i "$watchdog_pod" -- \
    env OBS_USER="$OBSERVANTIO_USERNAME" OBS_EMAIL="$OBSERVANTIO_EMAIL" OBS_PASS="$OBSERVANTIO_PASSWORD" \
    python - <<'PY'
import os
import uuid
from sqlalchemy import func

from config import config
from database import init_database, get_db_session
from db_models import Tenant, User
from services.database_auth_service import DatabaseAuthService

username = os.environ["OBS_USER"].strip()
email = os.environ["OBS_EMAIL"].strip()
password = os.environ["OBS_PASS"]

init_database(config.DATABASE_URL)
service = DatabaseAuthService()
password_hash = service.hash_password(password)

with get_db_session() as db:
    tenant_name = (getattr(config, "DEFAULT_ADMIN_TENANT", "") or "default").strip() or "default"
    tenant = db.query(Tenant).filter(func.lower(Tenant.name) == tenant_name.lower()).first()
    if tenant is None:
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=tenant_name,
            display_name=tenant_name,
            is_active=True,
        )
        db.add(tenant)
        db.flush()

    admin_org_id = getattr(config, "DEFAULT_ORG_ID", "default")
    user = db.query(User).filter(func.lower(User.username) == username.lower()).first()

    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            org_id=admin_org_id,
            username=username,
            email=email,
            hashed_password=password_hash,
            full_name="Observantio Admin",
            role="admin",
            is_active=True,
            is_superuser=True,
            needs_password_change=False,
            mfa_enabled=False,
            must_setup_mfa=True,
            auth_provider="local",
        )
        db.add(user)
        db.flush()
    else:
        user.tenant_id = tenant.id
        user.org_id = user.org_id or admin_org_id
        user.email = email
        user.hashed_password = password_hash
        user.role = "admin"
        user.is_active = True
        user.is_superuser = True
        user.needs_password_change = False
        user.auth_provider = "local"
        if not bool(user.mfa_enabled):
            user.must_setup_mfa = True
        db.flush()

    service.ensure_default_api_key(db, user)
PY
}

run_post_deploy_checks() {
  local watchdog_pod="$1"
  local api_scheme="http"
  local curl_health_opts=(-fsS)

  if [[ "$INTERNAL_TLS_REQUIRED" == "true" ]]; then
    api_scheme="https"
    curl_health_opts=(-kfsS)
  fi

  mkdir -p "$PORT_FORWARD_LOG_DIR"

  kubectl -n "$NAMESPACE" port-forward svc/"$OBSERVANTIO_SVC" "$LOCAL_API_PORT":4319 >"${PORT_FORWARD_LOG_DIR}/tmp-api-health.log" 2>&1 &
  TEMP_API_PF_PID=$!
  if [[ "$GATEKEEPER_REQUIRED" == "true" ]] && kubectl -n "$NAMESPACE" get svc "${RELEASE_NAME}-observantio-gatekeeper" >/dev/null 2>&1; then
    kubectl -n "$NAMESPACE" port-forward svc/"${RELEASE_NAME}-observantio-gatekeeper" 14321:4321 >"${PORT_FORWARD_LOG_DIR}/tmp-gatekeeper-health.log" 2>&1 &
    TEMP_GATEKEEPER_PF_PID=$!
  fi
  sleep 2

  curl "${curl_health_opts[@]}" "${api_scheme}://127.0.0.1:${LOCAL_API_PORT}/health" >/dev/null
  curl "${curl_health_opts[@]}" "${api_scheme}://127.0.0.1:${LOCAL_API_PORT}/ready" >/dev/null
  if [[ -n "$TEMP_GATEKEEPER_PF_PID" ]]; then
    curl -fsS "http://127.0.0.1:14321/api/gateway/health" >/dev/null
  fi

    kubectl -n "$NAMESPACE" exec -i "$watchdog_pod" -- \
    env GF_URL="http://${RELEASE_NAME}-observantio-grafana:3000" python - <<'PY'
import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

username = os.environ.get("GRAFANA_USERNAME", "").strip()
password = os.environ.get("GRAFANA_PASSWORD", "")
grafana_url = os.environ["GF_URL"].rstrip("/")

if not username or not password:
    raise SystemExit("Grafana credentials are missing in observantio runtime environment")

auth = base64.b64encode(f"{username}:{password}".encode()).decode()
headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}

def request(path: str):
    req = Request(f"{grafana_url}{path}", headers=headers)
    with urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8", errors="ignore")

try:
    status_user, _ = request("/api/user")
    if status_user >= 400:
        raise SystemExit(f"Grafana credentials rejected with status={status_user}")

    status_ds, body_ds = request("/api/datasources")
    if status_ds >= 400:
        raise SystemExit(f"Grafana datasource listing failed with status={status_ds}")

    parsed = json.loads(body_ds or "[]")
    if not isinstance(parsed, list):
        raise SystemExit("Unexpected Grafana datasource response payload")

except HTTPError as exc:
    if exc.code == 401:
        raise SystemExit(
            "Grafana rejected configured credentials (401). Check shared secret parity and reset Grafana state if it was initialized with an old admin password."
        )
    raise SystemExit(f"Grafana credential validation failed: HTTP {exc.code}")
except URLError as exc:
    raise SystemExit(f"Grafana credential validation failed: {exc}")

print("Grafana credential validation passed for observantio runtime.")
PY

  kubectl -n "$NAMESPACE" exec -i "$watchdog_pod" -- \
    env OBS_USER="$OBSERVANTIO_USERNAME" python - <<'PY'
import os
from sqlalchemy import func

from config import config
from database import init_database, get_db_session
from db_models import User

username = os.environ["OBS_USER"].strip()
init_database(config.DATABASE_URL)

with get_db_session() as db:
    user = db.query(User).filter(func.lower(User.username) == username.lower()).first()
    if user is None:
        raise SystemExit("Admin user not found after bootstrap enforcement")

    mfa_enabled = bool(user.mfa_enabled)
    must_setup_mfa = bool(user.must_setup_mfa)
    if (not mfa_enabled) and (not must_setup_mfa):
        raise SystemExit("Admin MFA bootstrap policy not enforced")

    print(f"admin_mfa_enabled={mfa_enabled} admin_must_setup_mfa={must_setup_mfa}")
PY
  echo "MFA policy validation passed for admin account."

  local allowlist_fail_open gateway_allowlist_fail_open
  allowlist_fail_open="$(kubectl -n "$NAMESPACE" exec "$watchdog_pod" -- sh -lc 'printenv ALLOWLIST_FAIL_OPEN || true')"
  [[ "$allowlist_fail_open" == "false" ]] || {
    echo "ALLOWLIST_FAIL_OPEN is not false inside observantio" >&2
    exit 1
  }
  if [[ "$GATEKEEPER_REQUIRED" == "true" ]]; then
    gateway_allowlist_fail_open="$(kubectl -n "$NAMESPACE" exec "$watchdog_pod" -- sh -lc 'printenv GATEWAY_ALLOWLIST_FAIL_OPEN || true')"
    [[ "$gateway_allowlist_fail_open" == "false" ]] || {
      echo "GATEWAY_ALLOWLIST_FAIL_OPEN is not false inside observantio" >&2
      exit 1
    }
  fi

  if [[ -n "$TEMP_API_PF_PID" ]]; then kill "$TEMP_API_PF_PID" >/dev/null 2>&1 || true; TEMP_API_PF_PID=""; fi
  if [[ -n "$TEMP_GATEKEEPER_PF_PID" ]]; then kill "$TEMP_GATEKEEPER_PF_PID" >/dev/null 2>&1 || true; TEMP_GATEKEEPER_PF_PID=""; fi
}

stop_existing_port_forwards() {
  pkill -f "port-forward svc/${OBSERVANTIO_SVC} ${API_FORWARD_PORT}:4319" >/dev/null 2>&1 || true
  pkill -f "port-forward svc/${RELEASE_NAME}-observantio-grafana-auth-gateway ${GRAFANA_PROXY_FORWARD_PORT}:8080" >/dev/null 2>&1 || true
  pkill -f "port-forward svc/${RELEASE_NAME}-observantio-ui ${UI_FORWARD_PORT}:80" >/dev/null 2>&1 || true
}

echo "Preparing secrets and internal TLS for release=${RELEASE_NAME} namespace=${NAMESPACE}"
ensure_application_secret
ensure_internal_tls_secret

POSTGRES_SERVICE="${RELEASE_NAME}-postgres"
WATCHDOG_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_SERVICE}:5432/${POSTGRES_DB}"
NOTIFIER_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_SERVICE}:5432/watchdog_notified"
RESOLVER_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_SERVICE}:5432/watchdog_resolver"

echo "Deploying ${EFFECTIVE_PROFILE} release ${RELEASE_NAME} in namespace ${NAMESPACE}"
helm_args=(
  upgrade --install "$RELEASE_NAME" "$CHART_PATH"
  -n "$NAMESPACE"
  --create-namespace
  --timeout "$HELM_TIMEOUT"
)

if [[ -f "$VALUES_FILE" ]]; then
  helm_args+=( -f "$VALUES_FILE" )
fi
if [[ "$EFFECTIVE_PROFILE" == "compact" ]]; then
  helm_args+=( -f "$COMPACT_VALUES_FILE" )
fi
for extra_values in "${EXTRA_VALUES_FILES[@]}"; do
  helm_args+=( -f "$extra_values" )
done

helm_args+=(
  --set externalSecrets.enabled=false
  --set secrets.create=false
  --set-string secrets.existingSecretName="$ACTIVE_SECRET_NAME"
  --set-string internalTLS.secretName="$INTERNAL_TLS_SECRET_NAME"
  --set networkPolicy.enabled=true
  --set podDisruptionBudget.enabled=true
  --set-string observantio.env.APP_ENV=production
  --set-string observantio.env.ENVIRONMENT=production
  --set-string observantio.env.DATABASE_URL="$WATCHDOG_DATABASE_URL"
  --set-string observantio.env.DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false
  --set-string observantio.env.DEFAULT_ADMIN_USERNAME="$OBSERVANTIO_USERNAME"
  --set-string observantio.env.DEFAULT_ADMIN_EMAIL="$OBSERVANTIO_EMAIL"
  --set-string observantio.env.DEFAULT_ADMIN_PASSWORD="$OBSERVANTIO_PASSWORD"
  --set-string observantio.env.FORCE_SECURE_COOKIES=true
  --set-string observantio.env.ALLOWLIST_FAIL_OPEN=false
  --set-string observantio.env.REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS=true
  --set-string observantio.env.REQUIRE_TOTP_ENCRYPTION_KEY=true
  --set-string observantio.env.SKIP_LOCAL_MFA_FOR_EXTERNAL=false
  --set-string gatekeeper.env.DATABASE_URL="$WATCHDOG_DATABASE_URL"
  --set-string notifier.env.APP_ENV=production
  --set-string notifier.env.ENVIRONMENT=production
  --set-string notifier.env.DATABASE_URL="$WATCHDOG_DATABASE_URL"
  --set-string notifier.env.NOTIFIER_DATABASE_URL="$NOTIFIER_DATABASE_URL"
  --set-string resolver.env.APP_ENV=production
  --set-string resolver.env.ENVIRONMENT=production
  --set-string resolver.env.RESOLVER_DATABASE_URL="$RESOLVER_DATABASE_URL"
)

if [[ -n "$NOTIFIER_IMAGE_REPOSITORY" ]]; then
  helm_args+=( --set-string notifier.image.repository="$NOTIFIER_IMAGE_REPOSITORY" )
fi
if [[ -n "$NOTIFIER_IMAGE_TAG" ]]; then
  helm_args+=( --set-string notifier.image.tag="$NOTIFIER_IMAGE_TAG" )
fi
if [[ -n "$NOTIFIER_IMAGE_REPOSITORY" || -n "$NOTIFIER_IMAGE_TAG" ]]; then
  helm_args+=( --set-string notifier.image.pullPolicy="$NOTIFIER_IMAGE_PULL_POLICY" )
fi

helm "${helm_args[@]}" >/dev/null
fail_fast_if_tls_requested_but_unsupported_images

wait_ready_deployment "${OBSERVANTIO_SVC}"
wait_ready_deployment "${RELEASE_NAME}-observantio-gatekeeper"
wait_ready_deployment "${NOTIFIER_SVC}"
wait_ready_deployment "${RESOLVER_SVC}"
wait_ready_deployment "${RELEASE_NAME}-observantio-grafana"
wait_ready_deployment "${RELEASE_NAME}-observantio-grafana-auth-gateway"
wait_ready_deployment "${RELEASE_NAME}-observantio-otlp-gateway"
wait_ready_deployment "${RELEASE_NAME}-observantio-ui"

WATCHDOG_POD="$(get_ready_pod_name observantio)"
NOTIFIER_POD="$(get_ready_pod_name notifier)"
RESOLVER_POD="$(get_ready_pod_name resolver)"

[[ -n "$WATCHDOG_POD" ]] || { echo "No ready observantio pod found" >&2; exit 1; }
[[ -n "$NOTIFIER_POD" ]] || { echo "No ready notifier pod found" >&2; exit 1; }
[[ -n "$RESOLVER_POD" ]] || { echo "No ready resolver pod found" >&2; exit 1; }

verify_service_token_alignment "$WATCHDOG_POD" "$NOTIFIER_POD" "$RESOLVER_POD"
enforce_admin_with_mfa_setup "$WATCHDOG_POD"

if [[ "$RUN_POST_DEPLOY_CHECKS" == "true" ]]; then
  run_post_deploy_checks "$WATCHDOG_POD"
fi

if [[ "$START_PORT_FORWARDS" == "true" ]]; then
  stop_existing_port_forwards
  if [[ "$PORT_FORWARD_MODE" != "foreground" && "$PORT_FORWARD_MODE" != "detached" && "$PORT_FORWARD_MODE" != "disabled" ]]; then
    echo "Invalid PORT_FORWARD_MODE: $PORT_FORWARD_MODE" >&2
    exit 1
  fi
  if [[ "$PORT_FORWARD_MODE" == "disabled" ]]; then
    START_PORT_FORWARDS="false"
  fi
fi

if [[ "$START_PORT_FORWARDS" == "true" ]]; then
  mkdir -p "$PORT_FORWARD_LOG_DIR"
  if [[ "$PORT_FORWARD_MODE" == "detached" ]]; then
    nohup kubectl -n "$NAMESPACE" port-forward svc/"$OBSERVANTIO_SVC" "${API_FORWARD_PORT}:4319" >"${PORT_FORWARD_LOG_DIR}/api.log" 2>&1 &
    API_PF_PID=$!
    nohup kubectl -n "$NAMESPACE" port-forward svc/"${RELEASE_NAME}-observantio-grafana-auth-gateway" "${GRAFANA_PROXY_FORWARD_PORT}:8080" >"${PORT_FORWARD_LOG_DIR}/grafana-gateway.log" 2>&1 &
    GRAFANA_PF_PID=$!
    nohup kubectl -n "$NAMESPACE" port-forward svc/"${RELEASE_NAME}-observantio-ui" "${UI_FORWARD_PORT}:80" >"${PORT_FORWARD_LOG_DIR}/ui.log" 2>&1 &
    UI_PF_PID=$!
  else
    kubectl -n "$NAMESPACE" port-forward svc/"$OBSERVANTIO_SVC" "${API_FORWARD_PORT}:4319" >"${PORT_FORWARD_LOG_DIR}/api.log" 2>&1 &
    API_PF_PID=$!
    kubectl -n "$NAMESPACE" port-forward svc/"${RELEASE_NAME}-observantio-grafana-auth-gateway" "${GRAFANA_PROXY_FORWARD_PORT}:8080" >"${PORT_FORWARD_LOG_DIR}/grafana-gateway.log" 2>&1 &
    GRAFANA_PF_PID=$!
    kubectl -n "$NAMESPACE" port-forward svc/"${RELEASE_NAME}-observantio-ui" "${UI_FORWARD_PORT}:80" >"${PORT_FORWARD_LOG_DIR}/ui.log" 2>&1 &
    UI_PF_PID=$!
  fi

  sleep 2
  if [[ "$INTERNAL_TLS_REQUIRED" == "true" ]]; then
    curl -kfsS "https://127.0.0.1:${API_FORWARD_PORT}/health" >/dev/null
  else
    curl -fsS "http://127.0.0.1:${API_FORWARD_PORT}/health" >/dev/null
  fi
  curl -fsS "http://127.0.0.1:${UI_FORWARD_PORT}/" >/dev/null
fi

echo
echo "Install complete"
echo "  Namespace:            ${NAMESPACE}"
echo "  Release:              ${RELEASE_NAME}"
echo "  Secret:               ${ACTIVE_SECRET_NAME}"
if [[ "$INTERNAL_TLS_REQUIRED" == "true" ]]; then
  echo "  Internal TLS secret:  ${INTERNAL_TLS_SECRET_NAME}"
else
  echo "  Internal TLS secret:  disabled by profile values"
fi
echo "  Install profile:      ${EFFECTIVE_PROFILE}"
echo "  Admin username:       ${OBSERVANTIO_USERNAME}"
echo "  Admin email:          ${OBSERVANTIO_EMAIL}"
echo "  MFA policy:           enforced (must_setup_mfa for non-enrolled admin)"
echo

if [[ "$START_PORT_FORWARDS" == "true" ]]; then
  API_DISPLAY_SCHEME="http"
  if [[ "$INTERNAL_TLS_REQUIRED" == "true" ]]; then
    API_DISPLAY_SCHEME="https"
  fi
  echo "Port-forwards:"
  echo "  API:           ${API_DISPLAY_SCHEME}://127.0.0.1:${API_FORWARD_PORT}"
  echo "  Grafana proxy: http://127.0.0.1:${GRAFANA_PROXY_FORWARD_PORT}/grafana/"
  echo "  UI:            http://127.0.0.1:${UI_FORWARD_PORT}/"
  echo "  Logs:          ${PORT_FORWARD_LOG_DIR}"
  if [[ "$PORT_FORWARD_MODE" == "foreground" ]]; then
    echo
    echo "Foreground mode. Press Ctrl+C to stop forwards."
    wait "$API_PF_PID" "$GRAFANA_PF_PID" "$UI_PF_PID"
  fi
else
  API_DISPLAY_SCHEME="http"
  if [[ "$INTERNAL_TLS_REQUIRED" == "true" ]]; then
    API_DISPLAY_SCHEME="https"
  fi
  echo "Port-forwards disabled."
  echo "  kubectl -n ${NAMESPACE} port-forward svc/${OBSERVANTIO_SVC} ${API_FORWARD_PORT}:4319   # ${API_DISPLAY_SCHEME}://127.0.0.1:${API_FORWARD_PORT}"
  echo "  kubectl -n ${NAMESPACE} port-forward svc/${RELEASE_NAME}-observantio-grafana-auth-gateway ${GRAFANA_PROXY_FORWARD_PORT}:8080"
  echo "  kubectl -n ${NAMESPACE} port-forward svc/${RELEASE_NAME}-observantio-ui ${UI_FORWARD_PORT}:80"
fi
