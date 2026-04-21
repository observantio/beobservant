#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RELEASE="${RELEASE:-observantio-prod}"
NAMESPACE="${NAMESPACE:-observantio}"
CHART="${CHART:-${SCRIPT_DIR}}"
PROFILE="${PROFILE:-production}"
HELM_TIMEOUT="${HELM_TIMEOUT:-20m}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-600s}"

MODE="install"
EXTRA_VALUES=()
PORT_FORWARD_MODE="none"
BACKGROUND_PIDS=()
API_PROXY_PORT="${API_PROXY_PORT:-4319}"
API_UPSTREAM_PORT="${API_UPSTREAM_PORT:-14319}"
API_PROXY_LOG="/tmp/observantio-api-proxy.log"
API_UPSTREAM_LOG="/tmp/observantio-api-upstream.log"
GRAFANA_PORT_FORWARD_LOG="/tmp/observantio-grafana-auth-gateway-port-forward.log"
UI_PORT_FORWARD_LOG="/tmp/observantio-ui-port-forward.log"

OBSERVANTIO_USERNAME="${OBSERVANTIO_USERNAME:-}"
OBSERVANTIO_EMAIL="${OBSERVANTIO_EMAIL:-}"
OBSERVANTIO_PASSWORD="${OBSERVANTIO_PASSWORD:-}"

POSTGRES_USER="watchdog"
POSTGRES_DB="watchdog"
POSTGRES_PASSWORD="" GRAFANA_USERNAME="" GRAFANA_PASSWORD="" GRAFANA_API_KEY=""
JWT_PRIVATE_KEY="" JWT_PUBLIC_KEY="" JWT_SECRET_KEY="" DATA_ENCRYPTION_KEY=""
DEFAULT_OTLP_TOKEN="" OTEL_OTLP_TOKEN="" INBOUND_WEBHOOK_TOKEN="" OTLP_INGEST_TOKEN=""
GATEWAY_TOKEN="" GATEWAY_STATUS_TOKEN="" NOTIFIER_TOKEN="" RESOLVER_TOKEN=""
NOTIFIER_CONTEXT_SIGNING_KEY="" NOTIFIER_CONTEXT_VERIFY_KEY=""
RESOLVER_CONTEXT_SIGNING_KEY="" RESOLVER_CONTEXT_VERIFY_KEY=""

cleanup() {
  local pid
  for pid in "${BACKGROUND_PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

usage() {
  cat <<EOF
Observantio Helm installer

Usage:
  bash installer.sh [mode] [options]

Modes (default: --install):
  --install         Deploy or upgrade the chart with credential setup
  --restart         Upgrade chart only, reuse existing secrets (no prompts)
  --remove          Uninstall the Helm release
  --purge           Uninstall, delete all PVCs, and remove the namespace

Port-forward modes:
  --foreground      Start local API proxy and port-forwards, then wait
  --detach          Start local API proxy and port-forwards in background
  --no-port-forward Do not start any local proxy or port-forwards

Options:
  --release <n>     Helm release name    (default: ${RELEASE})
  --namespace <n>   Kubernetes namespace (default: ${NAMESPACE})
  --chart <path>    Chart directory      (default: script directory)
  --profile <p>     Profile: production|compact  (default: ${PROFILE})
  --values <file>   Extra values file, repeatable
  -h, --help        Show this help

Environment:
  OBSERVANTIO_USERNAME  Admin username (interactive prompt if unset)
  OBSERVANTIO_EMAIL     Admin email    (interactive prompt if unset)
  OBSERVANTIO_PASSWORD  Admin password (interactive prompt if unset)

Examples:
  bash installer.sh
  bash installer.sh --profile compact
  bash installer.sh --restart
  bash installer.sh --remove
  bash installer.sh --purge
  bash installer.sh --values /tmp/my-overrides.yaml
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)   MODE="install";  shift ;;
    --restart)   MODE="restart";  shift ;;
    --remove)    MODE="remove";   shift ;;
    --purge)     MODE="purge";    shift ;;
    --release)   RELEASE="$2";   shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --chart)     CHART="$2";     shift 2 ;;
    --profile)   PROFILE="$2";   shift 2 ;;
    --values)    EXTRA_VALUES+=("$2"); shift 2 ;;
    --foreground) PORT_FORWARD_MODE="foreground"; shift ;;
    --detach)    PORT_FORWARD_MODE="detach"; shift ;;
    --no-port-forward) PORT_FORWARD_MODE="none"; shift ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }; }
random_hex()  { openssl rand -hex "$1"; }
random_b64()  { openssl rand -base64 32 | tr -d '\n'; }

SECRET_NAME="${RELEASE}-observantio-secrets"
INTERNAL_TLS_SECRET="${RELEASE}-observantio-internal-tls"
OBSERVANTIO_SVC="${RELEASE}-observantio-observantio"
GATEKEEPER_SVC="${RELEASE}-observantio-gatekeeper"
NOTIFIER_SVC="${RELEASE}-observantio-notifier"
RESOLVER_SVC="${RELEASE}-observantio-resolver"

for cmd in kubectl helm openssl curl python3; do
  require_cmd "$cmd"
done

kubectl cluster-info >/dev/null

# ── Remove / Purge ────────────────────────────────────────────────────────────

if [[ "$MODE" == "remove" || "$MODE" == "purge" ]]; then
  echo "Uninstalling ${RELEASE} from ${NAMESPACE}..."
  helm -n "$NAMESPACE" uninstall "$RELEASE" 2>/dev/null || true

  if [[ "$MODE" == "purge" ]]; then
    echo "Purging namespace ${NAMESPACE}..."
    if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
      kubectl -n "$NAMESPACE" delete pvc --all --wait=false 2>/dev/null || true
      kubectl get pv --no-headers \
        -o custom-columns=NAME:.metadata.name,NS:.spec.claimRef.namespace 2>/dev/null \
        | awk -v ns="$NAMESPACE" '$2==ns{print $1}' \
        | xargs -r kubectl delete pv --wait=false 2>/dev/null || true
      kubectl delete ns "$NAMESPACE" --wait=true --timeout=300s 2>/dev/null || true
    fi
  fi

  echo "Done."
  exit 0
fi

# ── Validate ──────────────────────────────────────────────────────────────────

case "$PROFILE" in
  production|compact) ;;
  *) echo "Unknown profile: $PROFILE (expected: production|compact)" >&2; exit 1 ;;
esac

CHART="$(cd "$CHART" && pwd)"
[[ -f "$CHART/Chart.yaml" ]] || { echo "Invalid chart path: $CHART" >&2; exit 1; }

kubectl get ns "$NAMESPACE" >/dev/null 2>&1 || kubectl create ns "$NAMESPACE" >/dev/null

# ── Credentials ──────────────────────────────────────────────────────────────

is_valid_username() { [[ "$1" =~ ^[A-Za-z0-9._-]{3,64}$ ]]; }
is_valid_email()    { [[ "$1" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; }

prompt_credentials() {
  if [[ ! -t 0 ]]; then
    OBSERVANTIO_USERNAME="${OBSERVANTIO_USERNAME:-admin}"
    OBSERVANTIO_EMAIL="${OBSERVANTIO_EMAIL:-${OBSERVANTIO_USERNAME}@example.com}"
    [[ -n "$OBSERVANTIO_PASSWORD" ]] || {
      echo "OBSERVANTIO_PASSWORD is required in non-interactive mode" >&2; exit 1
    }
    return
  fi

  if [[ -z "$OBSERVANTIO_USERNAME" ]]; then
    while true; do
      read -r -p "Admin username [admin]: " OBSERVANTIO_USERNAME
      OBSERVANTIO_USERNAME="${OBSERVANTIO_USERNAME:-admin}"
      is_valid_username "$OBSERVANTIO_USERNAME" && break
      echo "3-64 chars: letters, numbers, dot, underscore, or hyphen."
    done
  fi

  if [[ -z "$OBSERVANTIO_EMAIL" ]]; then
    while true; do
      read -r -p "Admin email [${OBSERVANTIO_USERNAME}@example.com]: " OBSERVANTIO_EMAIL
      OBSERVANTIO_EMAIL="${OBSERVANTIO_EMAIL:-${OBSERVANTIO_USERNAME}@example.com}"
      is_valid_email "$OBSERVANTIO_EMAIL" && break
      echo "Please enter a valid email address."
    done
  fi

  if [[ -z "$OBSERVANTIO_PASSWORD" ]]; then
    local confirm
    while true; do
      read -r -s -p "Admin password (min 16 chars): " OBSERVANTIO_PASSWORD; echo
      [[ ${#OBSERVANTIO_PASSWORD} -ge 16 ]] || { echo "Password too short."; continue; }
      read -r -s -p "Confirm password: " confirm; echo
      [[ "$OBSERVANTIO_PASSWORD" == "$confirm" ]] && break
      echo "Passwords do not match."; OBSERVANTIO_PASSWORD=""
    done
  fi
}

# ── Secrets ───────────────────────────────────────────────────────────────────

secret_field() {
  kubectl -n "$NAMESPACE" get secret "$1" \
    -o "jsonpath={.data.${2}}" 2>/dev/null | base64 -d 2>/dev/null || true
}

load_secret() {
  local s="$1"
  POSTGRES_USER="$(secret_field "$s" POSTGRES_USER)"
  POSTGRES_PASSWORD="$(secret_field "$s" POSTGRES_PASSWORD)"
  POSTGRES_DB="$(secret_field "$s" POSTGRES_DB)"
  JWT_PRIVATE_KEY="$(secret_field "$s" JWT_PRIVATE_KEY)"
  JWT_PUBLIC_KEY="$(secret_field "$s" JWT_PUBLIC_KEY)"
  JWT_SECRET_KEY="$(secret_field "$s" JWT_SECRET_KEY)"
  DATA_ENCRYPTION_KEY="$(secret_field "$s" DATA_ENCRYPTION_KEY)"
  DEFAULT_OTLP_TOKEN="$(secret_field "$s" DEFAULT_OTLP_TOKEN)"
  OTEL_OTLP_TOKEN="$(secret_field "$s" OTEL_OTLP_TOKEN)"
  INBOUND_WEBHOOK_TOKEN="$(secret_field "$s" INBOUND_WEBHOOK_TOKEN)"
  OTLP_INGEST_TOKEN="$(secret_field "$s" OTLP_INGEST_TOKEN)"
  GATEWAY_TOKEN="$(secret_field "$s" GATEWAY_INTERNAL_SERVICE_TOKEN)"
  GATEWAY_STATUS_TOKEN="$(secret_field "$s" GATEWAY_STATUS_OTLP_TOKEN)"
  NOTIFIER_TOKEN="$(secret_field "$s" NOTIFIER_SERVICE_TOKEN)"
  RESOLVER_TOKEN="$(secret_field "$s" RESOLVER_SERVICE_TOKEN)"
  NOTIFIER_CONTEXT_SIGNING_KEY="$(secret_field "$s" NOTIFIER_CONTEXT_SIGNING_KEY)"
  NOTIFIER_CONTEXT_VERIFY_KEY="$(secret_field "$s" NOTIFIER_CONTEXT_VERIFY_KEY)"
  RESOLVER_CONTEXT_SIGNING_KEY="$(secret_field "$s" RESOLVER_CONTEXT_SIGNING_KEY)"
  RESOLVER_CONTEXT_VERIFY_KEY="$(secret_field "$s" RESOLVER_CONTEXT_VERIFY_KEY)"
  GRAFANA_USERNAME="$(secret_field "$s" GRAFANA_USERNAME)"
  GRAFANA_PASSWORD="$(secret_field "$s" GRAFANA_PASSWORD)"
  GRAFANA_API_KEY="$(secret_field "$s" GRAFANA_API_KEY)"
}

fill_secret_defaults() {
  if [[ -z "$JWT_PRIVATE_KEY" || -z "$JWT_PUBLIC_KEY" ]]; then
    JWT_PRIVATE_KEY="$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 2>/dev/null)"
    JWT_PUBLIC_KEY="$(printf '%s' "$JWT_PRIVATE_KEY" | openssl rsa -pubout 2>/dev/null)"
  fi
  POSTGRES_USER="${POSTGRES_USER:-watchdog}"
  POSTGRES_DB="${POSTGRES_DB:-watchdog}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pg_$(random_hex 16)}"
  JWT_SECRET_KEY="${JWT_SECRET_KEY:-jwt_$(random_hex 24)}"
  DATA_ENCRYPTION_KEY="${DATA_ENCRYPTION_KEY:-$(random_b64)}"
  DEFAULT_OTLP_TOKEN="${DEFAULT_OTLP_TOKEN:-otlp_$(random_hex 16)}"
  OTEL_OTLP_TOKEN="${OTEL_OTLP_TOKEN:-$DEFAULT_OTLP_TOKEN}"
  INBOUND_WEBHOOK_TOKEN="${INBOUND_WEBHOOK_TOKEN:-wh_$(random_hex 16)}"
  OTLP_INGEST_TOKEN="${OTLP_INGEST_TOKEN:-ingest_$(random_hex 16)}"
  GATEWAY_TOKEN="${GATEWAY_TOKEN:-svc_gateway_$(random_hex 16)}"
  GATEWAY_STATUS_TOKEN="${GATEWAY_STATUS_TOKEN:-svc_status_$(random_hex 16)}"
  NOTIFIER_TOKEN="${NOTIFIER_TOKEN:-svc_notifier_$(random_hex 16)}"
  RESOLVER_TOKEN="${RESOLVER_TOKEN:-svc_resolver_$(random_hex 16)}"
  NOTIFIER_CONTEXT_SIGNING_KEY="${NOTIFIER_CONTEXT_SIGNING_KEY:-ctx_notifier_$(random_hex 16)}"
  NOTIFIER_CONTEXT_VERIFY_KEY="${NOTIFIER_CONTEXT_VERIFY_KEY:-$NOTIFIER_CONTEXT_SIGNING_KEY}"
  RESOLVER_CONTEXT_SIGNING_KEY="${RESOLVER_CONTEXT_SIGNING_KEY:-ctx_resolver_$(random_hex 16)}"
  RESOLVER_CONTEXT_VERIFY_KEY="${RESOLVER_CONTEXT_VERIFY_KEY:-$RESOLVER_CONTEXT_SIGNING_KEY}"
  GRAFANA_USERNAME="${GRAFANA_USERNAME:-admin}"
  GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-grafana_$(random_hex 24)}"
}

apply_secret() {
  local name="$1"
  local tmp
  tmp="$(mktemp -d)"

  printf '%s' "$POSTGRES_USER"                > "${tmp}/POSTGRES_USER"
  printf '%s' "$POSTGRES_PASSWORD"            > "${tmp}/POSTGRES_PASSWORD"
  printf '%s' "$POSTGRES_DB"                  > "${tmp}/POSTGRES_DB"
  printf '%s' "$JWT_SECRET_KEY"               > "${tmp}/JWT_SECRET_KEY"
  printf '%s' "$JWT_PRIVATE_KEY"              > "${tmp}/JWT_PRIVATE_KEY"
  printf '%s' "$JWT_PUBLIC_KEY"               > "${tmp}/JWT_PUBLIC_KEY"
  printf '%s' "$DATA_ENCRYPTION_KEY"          > "${tmp}/DATA_ENCRYPTION_KEY"
  printf '%s' "$DEFAULT_OTLP_TOKEN"           > "${tmp}/DEFAULT_OTLP_TOKEN"
  printf '%s' "$OTEL_OTLP_TOKEN"              > "${tmp}/OTEL_OTLP_TOKEN"
  printf '%s' "$INBOUND_WEBHOOK_TOKEN"        > "${tmp}/INBOUND_WEBHOOK_TOKEN"
  printf '%s' "$OTLP_INGEST_TOKEN"            > "${tmp}/OTLP_INGEST_TOKEN"
  printf '%s' "$GATEWAY_TOKEN"                > "${tmp}/GATEWAY_INTERNAL_SERVICE_TOKEN"
  printf '%s' "$GATEWAY_STATUS_TOKEN"         > "${tmp}/GATEWAY_STATUS_OTLP_TOKEN"
  printf '%s' "$NOTIFIER_TOKEN"               > "${tmp}/NOTIFIER_SERVICE_TOKEN"
  printf '%s' "$NOTIFIER_TOKEN"               > "${tmp}/NOTIFIER_EXPECTED_SERVICE_TOKEN"
  printf '%s' "$NOTIFIER_CONTEXT_SIGNING_KEY" > "${tmp}/NOTIFIER_CONTEXT_SIGNING_KEY"
  printf '%s' "$NOTIFIER_CONTEXT_VERIFY_KEY"  > "${tmp}/NOTIFIER_CONTEXT_VERIFY_KEY"
  printf '%s' "$RESOLVER_TOKEN"               > "${tmp}/RESOLVER_SERVICE_TOKEN"
  printf '%s' "$RESOLVER_TOKEN"               > "${tmp}/RESOLVER_EXPECTED_SERVICE_TOKEN"
  printf '%s' "$RESOLVER_CONTEXT_SIGNING_KEY" > "${tmp}/RESOLVER_CONTEXT_SIGNING_KEY"
  printf '%s' "$RESOLVER_CONTEXT_VERIFY_KEY"  > "${tmp}/RESOLVER_CONTEXT_VERIFY_KEY"
  printf '%s' "$GRAFANA_USERNAME"             > "${tmp}/GRAFANA_USERNAME"
  printf '%s' "$GRAFANA_PASSWORD"             > "${tmp}/GRAFANA_PASSWORD"
  printf '%s' "$GRAFANA_API_KEY"              > "${tmp}/GRAFANA_API_KEY"

  local args=()
  for f in "$tmp"/*; do args+=("--from-file=$(basename "$f")=$f"); done

  kubectl -n "$NAMESPACE" create secret generic "$name" \
    "${args[@]}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

  rm -rf "$tmp"
}

# ── TLS secret (only when internalTLS.enabled: true in values) ────────────────

tls_enabled_in_files() {
  local result="false"
  for f in "$@"; do
    [[ -f "$f" ]] || continue
    local val
    val="$(awk '/^internalTLS:/{f=1} f && /enabled:/{match($0,/(true|false)/); if(RLENGTH>0){print substr($0,RSTART,RLENGTH)}; exit}' "$f" 2>/dev/null || true)"
    [[ -n "$val" ]] && result="$val"
  done
  echo "$result"
}

ensure_tls_secret() {
  kubectl -n "$NAMESPACE" get secret "$INTERNAL_TLS_SECRET" >/dev/null 2>&1 && return

  echo "Generating internal TLS certificates..."
  local tmp ca_key ca_crt
  tmp="$(mktemp -d)"
  ca_key="${tmp}/ca.key" ca_crt="${tmp}/ca.crt"

  openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
    -keyout "$ca_key" -out "$ca_crt" \
    -subj "/CN=observantio-internal-ca" >/dev/null 2>&1

  make_cert() {
    local name="$1" svc="$2"
    printf 'subjectAltName=DNS:%s,DNS:%s.%s,DNS:%s.%s.svc,DNS:%s.%s.svc.cluster.local\nextendedKeyUsage=serverAuth\n' \
      "$svc" "$svc" "$NAMESPACE" "$svc" "$NAMESPACE" "$svc" "$NAMESPACE" > "${tmp}/${name}.ext"
    openssl req -new -newkey rsa:2048 -nodes \
      -keyout "${tmp}/${name}.key" -out "${tmp}/${name}.csr" \
      -subj "/CN=${name}" >/dev/null 2>&1
    openssl x509 -req \
      -in "${tmp}/${name}.csr" -CA "$ca_crt" -CAkey "$ca_key" -CAcreateserial \
      -out "${tmp}/${name}.crt" -days 365 -extfile "${tmp}/${name}.ext" >/dev/null 2>&1
  }

  make_cert observantio "$OBSERVANTIO_SVC"
  make_cert gatekeeper "$GATEKEEPER_SVC"
  make_cert notifier    "$NOTIFIER_SVC"
  make_cert resolver    "$RESOLVER_SVC"

  kubectl -n "$NAMESPACE" create secret generic "$INTERNAL_TLS_SECRET" \
    --from-file=ca.crt="${tmp}/ca.crt" \
    --from-file=observantio.crt="${tmp}/observantio.crt" \
    --from-file=observantio.key="${tmp}/observantio.key" \
    --from-file=gatekeeper.crt="${tmp}/gatekeeper.crt" \
    --from-file=gatekeeper.key="${tmp}/gatekeeper.key" \
    --from-file=notifier.crt="${tmp}/notifier.crt" \
    --from-file=notifier.key="${tmp}/notifier.key" \
    --from-file=resolver.crt="${tmp}/resolver.crt" \
    --from-file=resolver.key="${tmp}/resolver.key" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null

  rm -rf "$tmp"
}

# ── Rollout helpers ───────────────────────────────────────────────────────────

wait_for_rollout() {
  local dep="$1"
  kubectl -n "$NAMESPACE" get deployment "$dep" >/dev/null 2>&1 || return 0
  kubectl -n "$NAMESPACE" rollout status deployment "$dep" --timeout="$ROLLOUT_TIMEOUT" || {
    echo "Rollout failed: $dep" >&2
    kubectl -n "$NAMESPACE" get pods -l "app.kubernetes.io/instance=${RELEASE}" -o wide >&2 || true
    kubectl -n "$NAMESPACE" get events --sort-by=.lastTimestamp | tail -30 >&2 || true
    exit 1
  }
}

wait_for_http() {
  local desc="$1" url="$2" attempts="${3:-90}" interval="${4:-2}"
  shift 4
  local http_code body err
  body="$(mktemp)" err="$(mktemp)"
  for ((i=1; i<=attempts; i++)); do
    http_code="$(curl "$@" -o "$body" -w '%{http_code}' "$url" 2>"$err" || true)"
    [[ "$http_code" == 2* ]] && { rm -f "$body" "$err"; return 0; }
    (( i == 1 || i % 10 == 0 )) && echo "Waiting for ${desc} (${i}/${attempts}, status: ${http_code:-000})..."
    sleep "$interval"
  done
  echo "${desc} not ready after ${attempts} attempts." >&2
  [[ -s "$body" ]] && sed -n '1,20p' "$body" >&2
  rm -f "$body" "$err"
  return 1
}

get_ready_pod() {
  kubectl -n "$NAMESPACE" get pods -l "app.kubernetes.io/component=$1" \
    -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" "}{range .status.conditions[?(@.type=="Ready")]}{.status}{end}{"\n"}{end}' 2>/dev/null \
    | awk '$2=="Running" && $3=="True" {print $1; exit}'
}

start_managed_process() {
  local detached="$1"
  local log_file="$2"
  shift 2

  if [[ "$detached" == "true" ]]; then
    nohup "$@" >"$log_file" 2>&1 &
  else
    "$@" >"$log_file" 2>&1 &
    BACKGROUND_PIDS+=("$!")
  fi
}

start_foreground_port_forward() {
  local log_file="$1"
  local name="$2"
  shift 2

  (
    local child_pid=""
    local stop_requested="false"

    stop_child() {
      stop_requested="true"
      [[ -n "$child_pid" ]] && kill "$child_pid" 2>/dev/null || true
    }

    trap stop_child INT TERM

    while true; do
      "$@" >>"$log_file" 2>&1 &
      child_pid="$!"
      if wait "$child_pid"; then
        local child_status=0
      else
        local child_status="$?"
      fi
      child_pid=""

      if [[ "$stop_requested" == "true" ]]; then
        exit 0
      fi

      if [[ "$child_status" == 0 ]]; then
        exit 0
      fi

      printf '%s exited with status %s; restarting in 2 seconds...\n' "$name" "$child_status" >>"$log_file"
      sleep 2
    done
  ) &

  BACKGROUND_PIDS+=("$!")
}

kill_listeners_on_ports() {
  local port listener_output pids pid

  for port in "$@"; do
    listener_output="$(ss -H -ltnp "( sport = :${port} )" 2>/dev/null || true)"
    [[ -n "$listener_output" ]] || continue

    pids="$(printf '%s\n' "$listener_output" | grep -o 'pid=[0-9]\+' | cut -d= -f2 | sort -u || true)"
    for pid in $pids; do
      [[ -n "$pid" ]] || continue
      kill "$pid" 2>/dev/null || true
    done
  done
}

start_api_proxy() {
  local detached="$1"
  local upstream_is_https="$2"

  kill_listeners_on_ports "$API_PROXY_PORT" "$API_UPSTREAM_PORT"

  if [[ "$detached" == "true" ]]; then
    start_managed_process "$detached" "$API_UPSTREAM_LOG" \
      kubectl -n "$NAMESPACE" port-forward "svc/$OBSERVANTIO_SVC" "${API_UPSTREAM_PORT}:4319"
  else
    start_foreground_port_forward "$API_UPSTREAM_LOG" "API upstream port-forward" \
      kubectl -n "$NAMESPACE" port-forward "svc/$OBSERVANTIO_SVC" "${API_UPSTREAM_PORT}:4319"
  fi

  if [[ "$detached" == "true" ]]; then
    nohup python3 "$SCRIPT_DIR/api_proxy.py" "$API_PROXY_PORT" "$API_UPSTREAM_PORT" "$upstream_is_https" \
      >"$API_PROXY_LOG" 2>&1 &
  else
    python3 "$SCRIPT_DIR/api_proxy.py" "$API_PROXY_PORT" "$API_UPSTREAM_PORT" "$upstream_is_https" \
      >"$API_PROXY_LOG" 2>&1 &
    BACKGROUND_PIDS+=("$!")
  fi
}

start_user_port_forwards() {
  local detached="$1"

  kill_listeners_on_ports 8080 5173

  if [[ "$detached" == "true" ]]; then
    start_managed_process "$detached" "$GRAFANA_PORT_FORWARD_LOG" \
      kubectl -n "$NAMESPACE" port-forward "svc/${RELEASE}-observantio-grafana-auth-gateway" 8080:8080
    start_managed_process "$detached" "$UI_PORT_FORWARD_LOG" \
      kubectl -n "$NAMESPACE" port-forward "svc/${RELEASE}-observantio-ui" 5173:80
  else
    start_foreground_port_forward "$GRAFANA_PORT_FORWARD_LOG" "Grafana auth gateway port-forward" \
      kubectl -n "$NAMESPACE" port-forward "svc/${RELEASE}-observantio-grafana-auth-gateway" 8080:8080
    start_foreground_port_forward "$UI_PORT_FORWARD_LOG" "UI port-forward" \
      kubectl -n "$NAMESPACE" port-forward "svc/${RELEASE}-observantio-ui" 5173:80
  fi
}

print_port_forward_info() {
  if [[ "$PORT_FORWARD_MODE" == "none" ]]; then
    if [[ "$INTERNAL_TLS_ENABLED" == "true" ]]; then
      cat <<NOTE
  Local forwarding is disabled.
  Re-run with --foreground to start a local proxy that upgrades the API upstream to HTTPS automatically.
NOTE
    else
      cat <<EOF
  Port-forwards:
    kubectl -n ${NAMESPACE} port-forward svc/${OBSERVANTIO_SVC} 4319:4319
    kubectl -n ${NAMESPACE} port-forward svc/${RELEASE}-observantio-grafana-auth-gateway 8080:8080
    kubectl -n ${NAMESPACE} port-forward svc/${RELEASE}-observantio-ui 5173:80
EOF
    fi
  else
    cat <<EOF
  Local access:
    http://127.0.0.1:4319  (API proxy)
    http://127.0.0.1:8080  (Grafana auth gateway)
    http://127.0.0.1:5173  (UI)
EOF
  fi
}

# ── Deploy ────────────────────────────────────────────────────────────────────

deploy() {
  local pg_svc="${RELEASE}-postgres"
  local db_url="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${pg_svc}:5432/${POSTGRES_DB}"
  local notifier_db="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${pg_svc}:5432/watchdog_notified"
  local resolver_db="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${pg_svc}:5432/watchdog_resolver"
  local force_secure_cookies="true"
  local gatekeeper_enabled="true"

  # Local foreground/detached access is plain HTTP on localhost, so secure cookies
  # would be dropped by the browser and login would never persist.
  if [[ "$PORT_FORWARD_MODE" != "none" ]]; then
    force_secure_cookies="false"
  fi

  # Gatekeeper in production requires HTTPS auth API; keep it disabled unless
  # internal TLS is enabled for service-to-service traffic.
  if [[ "$INTERNAL_TLS_ENABLED" != "true" ]]; then
    gatekeeper_enabled="false"
  fi

  local args=(
    upgrade --install "$RELEASE" "$CHART"
    -n "$NAMESPACE" --create-namespace
    --timeout "$HELM_TIMEOUT"
    -f "$CHART/values-production.yaml"
  )
  [[ "$PROFILE" == "compact" ]] && args+=(-f "$CHART/values-compact.yaml")
  for f in "${EXTRA_VALUES[@]}"; do args+=(-f "$f"); done

  args+=(
    --set    externalSecrets.enabled=false
    --set    secrets.create=false
    --set    networkPolicy.enabled=true
    --set    podDisruptionBudget.enabled=true
    --set    gatekeeper.enabled="$gatekeeper_enabled"
    --set-string secrets.existingSecretName="$SECRET_NAME"
    --set-string internalTLS.secretName="$INTERNAL_TLS_SECRET"
    --set-string observantio.env.APP_ENV=production
    --set-string observantio.env.ENVIRONMENT=production
    --set-string observantio.env.DATABASE_URL="$db_url"
    --set-string observantio.env.ALLOWLIST_FAIL_OPEN=false
    --set-string observantio.env.FORCE_SECURE_COOKIES="$force_secure_cookies"
    --set-string observantio.env.REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS=true
    --set-string observantio.env.REQUIRE_TOTP_ENCRYPTION_KEY=true
    --set-string observantio.env.SKIP_LOCAL_MFA_FOR_EXTERNAL=false
    --set-string gatekeeper.env.DATABASE_URL="$db_url"
    --set-string notifier.env.APP_ENV=production
    --set-string notifier.env.ENVIRONMENT=production
    --set-string notifier.env.DATABASE_URL="$db_url"
    --set-string notifier.env.NOTIFIER_DATABASE_URL="$notifier_db"
    --set-string resolver.env.APP_ENV=production
    --set-string resolver.env.ENVIRONMENT=production
    --set-string resolver.env.RESOLVER_DATABASE_URL="$resolver_db"
  )

  if [[ "$MODE" == "install" ]]; then
    args+=(
      --set-string observantio.env.DEFAULT_ADMIN_BOOTSTRAP_ENABLED=false
      --set-string observantio.env.DEFAULT_ADMIN_USERNAME="$OBSERVANTIO_USERNAME"
      --set-string observantio.env.DEFAULT_ADMIN_EMAIL="$OBSERVANTIO_EMAIL"
      --set-string observantio.env.DEFAULT_ADMIN_PASSWORD="$OBSERVANTIO_PASSWORD"
    )
  fi

  echo "Deploying ${PROFILE} profile → ${RELEASE} in ${NAMESPACE}..."
  helm "${args[@]}" >/dev/null

  wait_for_rollout "$OBSERVANTIO_SVC"
  [[ "$gatekeeper_enabled" == "true" ]] && wait_for_rollout "${RELEASE}-observantio-gatekeeper"
  wait_for_rollout "$NOTIFIER_SVC"
  wait_for_rollout "$RESOLVER_SVC"
  wait_for_rollout "${RELEASE}-observantio-grafana"
  wait_for_rollout "${RELEASE}-observantio-grafana-auth-gateway"
  wait_for_rollout "${RELEASE}-observantio-otlp-gateway"
  wait_for_rollout "${RELEASE}-observantio-ui"
}

# ── Post-deploy ───────────────────────────────────────────────────────────────

verify_tokens() {
  local wd="$1" no="$2" re="$3"
  local wd_n wd_r no_e re_e
  wd_n="$(kubectl -n "$NAMESPACE" exec "$wd" -- sh -lc 'printf %s "${NOTIFIER_SERVICE_TOKEN}"  | sha256sum | cut -d" " -f1')"
  wd_r="$(kubectl -n "$NAMESPACE" exec "$wd" -- sh -lc 'printf %s "${RESOLVER_SERVICE_TOKEN}"  | sha256sum | cut -d" " -f1')"
  no_e="$(kubectl -n "$NAMESPACE" exec "$no" -- sh -lc 'printf %s "${NOTIFIER_EXPECTED_SERVICE_TOKEN}" | sha256sum | cut -d" " -f1')"
  re_e="$(kubectl -n "$NAMESPACE" exec "$re" -- sh -lc 'printf %s "${RESOLVER_EXPECTED_SERVICE_TOKEN}" | sha256sum | cut -d" " -f1')"
  [[ "$wd_n" == "$no_e" ]] || { echo "Notifier token mismatch between observantio and notifier" >&2; exit 1; }
  [[ "$wd_r" == "$re_e" ]] || { echo "Resolver token mismatch between observantio and resolver" >&2; exit 1; }
}

bootstrap_admin() {
  local pod="$1"
  kubectl -n "$NAMESPACE" exec -i "$pod" -- \
    env OBS_USER="$OBSERVANTIO_USERNAME" OBS_EMAIL="$OBSERVANTIO_EMAIL" OBS_PASS="$OBSERVANTIO_PASSWORD" \
    python - <<'PY'
import os, uuid
from sqlalchemy import func
from config import config
from database import init_database, get_db_session
from db_models import Tenant, User
from services.database_auth_service import DatabaseAuthService

username = os.environ["OBS_USER"].strip()
email    = os.environ["OBS_EMAIL"].strip()
password = os.environ["OBS_PASS"]

init_database(config.DATABASE_URL)
service       = DatabaseAuthService()
password_hash = service.hash_password(password)

with get_db_session() as db:
    tenant_name = (getattr(config, "DEFAULT_ADMIN_TENANT", "") or "default").strip() or "default"
    tenant = db.query(Tenant).filter(func.lower(Tenant.name) == tenant_name.lower()).first()
    if tenant is None:
        tenant = Tenant(id=str(uuid.uuid4()), name=tenant_name, display_name=tenant_name, is_active=True)
        db.add(tenant)
        db.flush()

    admin_org_id = getattr(config, "DEFAULT_ORG_ID", "default")
    user = db.query(User).filter(func.lower(User.username) == username.lower()).first()

    if user is None:
        user = User(
            id=str(uuid.uuid4()), tenant_id=tenant.id, org_id=admin_org_id,
            username=username, email=email, hashed_password=password_hash,
            full_name="Observantio Admin", role="admin", is_active=True,
            is_superuser=True, needs_password_change=False,
            mfa_enabled=False, must_setup_mfa=True, auth_provider="local",
        )
        db.add(user)
        db.flush()
    else:
        user.tenant_id        = tenant.id
        user.org_id           = user.org_id or admin_org_id
        user.email            = email
        user.hashed_password  = password_hash
        user.role             = "admin"
        user.is_active        = True
        user.is_superuser     = True
        user.needs_password_change = False
        user.auth_provider    = "local"
        if not bool(user.mfa_enabled):
            user.must_setup_mfa = True
        db.flush()

    service.ensure_default_api_key(db, user)
PY
}

post_deploy_checks() {
  local pod="$1"

  wait_for_http "API health"    "http://127.0.0.1:4319/health" 90 2 -sS
  wait_for_http "API readiness" "http://127.0.0.1:4319/ready"  90 2 -sS

  kubectl -n "$NAMESPACE" exec -i "$pod" -- \
    env GF_URL="http://${RELEASE}-observantio-grafana:3000" python - <<'PY'
import base64, json, os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

username    = os.environ.get("GRAFANA_USERNAME", "").strip()
password    = os.environ.get("GRAFANA_PASSWORD", "")
grafana_url = os.environ["GF_URL"].rstrip("/")

if not username or not password:
    raise SystemExit("Grafana credentials missing in observantio runtime environment")

auth    = base64.b64encode(f"{username}:{password}".encode()).decode()
headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}

def request(path):
    req = Request(f"{grafana_url}{path}", headers=headers)
    with urlopen(req, timeout=10) as r:
        return r.status, r.read().decode("utf-8", errors="ignore")

try:
    status, _ = request("/api/user")
    if status >= 400:
        raise SystemExit(f"Grafana credentials rejected (status={status})")
    status, body = request("/api/datasources")
    if status >= 400:
        raise SystemExit(f"Grafana datasource listing failed (status={status})")
    if not isinstance(json.loads(body or "[]"), list):
        raise SystemExit("Unexpected Grafana datasource response")
except HTTPError as e:
    raise SystemExit(f"Grafana validation failed: HTTP {e.code}")
except URLError as e:
    raise SystemExit(f"Grafana validation failed: {e}")

print("Grafana credentials validated.")
PY

  local fail_open
  fail_open="$(kubectl -n "$NAMESPACE" exec "$pod" -- sh -lc 'printenv ALLOWLIST_FAIL_OPEN || true')"
  [[ "$fail_open" == "false" ]] || { echo "ALLOWLIST_FAIL_OPEN is not false inside observantio" >&2; exit 1; }
}

verify_admin_mfa() {
  local pod="$1"
  kubectl -n "$NAMESPACE" exec -i "$pod" -- \
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
        raise SystemExit("Admin user not found after bootstrap")
    if not bool(user.mfa_enabled) and not bool(user.must_setup_mfa):
        raise SystemExit("Admin MFA policy not enforced")
    print(f"MFA policy: mfa_enabled={user.mfa_enabled} must_setup_mfa={user.must_setup_mfa}")
PY
}

# ── Main ──────────────────────────────────────────────────────────────────────

already_installed() {
  helm -n "$NAMESPACE" status "$RELEASE" >/dev/null 2>&1
}

if [[ "$MODE" == "install" ]] && already_installed; then
  cat <<EOF
Release '${RELEASE}' is already installed in namespace '${NAMESPACE}'.

  --restart   Upgrade the chart and reuse existing secrets (no prompts)
  --purge     Wipe everything and start fresh

EOF
  exit 1
fi

if [[ "$MODE" == "install" ]]; then
  prompt_credentials
  [[ ${#OBSERVANTIO_PASSWORD} -ge 16 ]] || { echo "Password must be at least 16 characters." >&2; exit 1; }
  is_valid_username "$OBSERVANTIO_USERNAME"  || { echo "Invalid username." >&2; exit 1; }
  is_valid_email    "$OBSERVANTIO_EMAIL"     || { echo "Invalid email."    >&2; exit 1; }
fi

echo "Preparing secrets..."
kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" >/dev/null 2>&1 && load_secret "$SECRET_NAME"

if [[ "$MODE" == "restart" ]]; then
  [[ -n "$POSTGRES_PASSWORD" ]] || {
    echo "Secret ${SECRET_NAME} not found. Run --install first." >&2; exit 1
  }
else
  fill_secret_defaults
  apply_secret "$SECRET_NAME"
fi

VALUES_FILES=("$CHART/values-production.yaml")
[[ "$PROFILE" == "compact" ]] && VALUES_FILES+=("$CHART/values-compact.yaml")
for f in "${EXTRA_VALUES[@]}"; do VALUES_FILES+=("$f"); done

INTERNAL_TLS_ENABLED="$(tls_enabled_in_files "${VALUES_FILES[@]}")"
if [[ "$INTERNAL_TLS_ENABLED" == "true" ]]; then
  ensure_tls_secret
fi

deploy

PF_DETACHED="false"
[[ "$PORT_FORWARD_MODE" == "detach" ]] && PF_DETACHED="true"

start_api_proxy "$PF_DETACHED" "$INTERNAL_TLS_ENABLED"

WD_POD="$(get_ready_pod observantio)"
NO_POD="$(get_ready_pod notifier)"
RE_POD="$(get_ready_pod resolver)"

[[ -n "$WD_POD" ]] || { echo "No ready observantio pod found." >&2; exit 1; }
[[ -n "$NO_POD" ]] || { echo "No ready notifier pod found."    >&2; exit 1; }
[[ -n "$RE_POD" ]] || { echo "No ready resolver pod found."    >&2; exit 1; }

verify_tokens "$WD_POD" "$NO_POD" "$RE_POD"

if [[ "$MODE" == "install" ]]; then
  bootstrap_admin  "$WD_POD"
  verify_admin_mfa "$WD_POD"
fi

post_deploy_checks "$WD_POD"

if [[ "$PORT_FORWARD_MODE" != "none" ]]; then
  start_user_port_forwards "$PF_DETACHED"
fi

cat <<EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Observantio deployed successfully
  Release:    ${RELEASE}
  Namespace:  ${NAMESPACE}
  Profile:    ${PROFILE}
$(if [[ "$MODE" == "install" ]]; then
  printf "  Admin:      %s (%s)\n" "$OBSERVANTIO_USERNAME" "$OBSERVANTIO_EMAIL"
  printf "  MFA:        enforced on first login\n"
fi)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
$(print_port_forward_info)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF

if [[ "$PORT_FORWARD_MODE" == "foreground" ]]; then
  echo
  echo "Foreground mode active. Press Ctrl+C to stop the API proxy and port-forwards."
  wait "${BACKGROUND_PIDS[@]}"
fi