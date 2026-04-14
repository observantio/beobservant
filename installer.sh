#!/usr/bin/env bash
set -euo pipefail

RELEASE_NAME="${RELEASE_NAME:-observantio-smoke}"
NAMESPACE="${NAMESPACE:-observantio-smoke}"
CHART_PATH="${CHART_PATH:-charts/observantio}"
HELM_TIMEOUT="${HELM_TIMEOUT:-15m}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-420s}"
LOCAL_API_PORT="${LOCAL_API_PORT:-4319}"
REUSE_EXISTING_SECRETS="${REUSE_EXISTING_SECRETS:-true}"
START_PORT_FORWARDS="${START_PORT_FORWARDS:-true}"
PORT_FORWARD_LOG_DIR="${PORT_FORWARD_LOG_DIR:-/tmp/observantio-port-forward}"
API_FORWARD_PORT="${API_FORWARD_PORT:-$LOCAL_API_PORT}"
GRAFANA_PROXY_FORWARD_PORT="${GRAFANA_PROXY_FORWARD_PORT:-8080}"
UI_FORWARD_PORT="${UI_FORWARD_PORT:-5173}"
PORT_FORWARD_MODE="${PORT_FORWARD_MODE:-detached}" # detached | foreground | disabled
GRAFANA_DIRECT_CHECK_PORT="${GRAFANA_DIRECT_CHECK_PORT:-13000}"
REMOVE_MODE="false"

OBSERVANTIO_USERNAME="${OBSERVANTIO_USERNAME:-}"
OBSERVANTIO_EMAIL="${OBSERVANTIO_EMAIL:-}"
OBSERVANTIO_PASSWORD="${OBSERVANTIO_PASSWORD:-}"

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

build_login_payload() {
  local username="$1"
  local password="$2"
  OBS_USER="$username" OBS_PASS="$password" python3 - <<'PY'
import json
import os
print(json.dumps({"username": os.environ["OBS_USER"], "password": os.environ["OBS_PASS"]}))
PY
}

secret_key_or_empty() {
  local secret_name="$1"
  local key="$2"
  kubectl -n "$NAMESPACE" get secret "$secret_name" -o "jsonpath={.data.${key}}" 2>/dev/null | base64 -d 2>/dev/null || true
}

parse_timeout_seconds() {
  local value="$1"
  if [[ "$value" =~ ^([0-9]+)s$ ]]; then
    echo "${BASH_REMATCH[1]}"
  elif [[ "$value" =~ ^([0-9]+)m$ ]]; then
    echo "$(( BASH_REMATCH[1] * 60 ))"
  elif [[ "$value" =~ ^([0-9]+)h$ ]]; then
    echo "$(( BASH_REMATCH[1] * 3600 ))"
  elif [[ "$value" =~ ^[0-9]+$ ]]; then
    echo "$value"
  else
    echo "Invalid timeout value: $value" >&2
    exit 1
  fi
}

wait_ready_pod_for_component() {
  local component="$1"
  local timeout_seconds
  timeout_seconds="$(parse_timeout_seconds "$ROLLOUT_TIMEOUT")"
  local elapsed=0
  local step=5
  local ready_count

  echo "Waiting for ${component}..."
  while (( elapsed < timeout_seconds )); do
    ready_count="$({
      kubectl -n "$NAMESPACE" get pods \
        -l "app.kubernetes.io/component=${component}" \
        -o jsonpath='{range .items[*]}{range .status.conditions[?(@.type=="Ready")]}{.status}{"\n"}{end}{end}' 2>/dev/null \
      | grep -c '^True$' || true
    })"
    if [[ "$ready_count" -ge 1 ]]; then
      return 0
    fi
    sleep "$step"
    elapsed=$((elapsed + step))
  done

  echo "Timed out waiting for component '${component}'" >&2
  kubectl -n "$NAMESPACE" get pods -l "app.kubernetes.io/component=${component}" >&2 || true
  return 1
}

get_ready_pod_name() {
  local component="$1"
  kubectl -n "$NAMESPACE" get pods -l "app.kubernetes.io/component=${component}" \
    -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" "}{range .status.conditions[?(@.type=="Ready")]}{.status}{end}{"\n"}{end}' 2>/dev/null \
    | awk '$2=="Running" && $3=="True" {print $1; exit}'
}

cleanup() {
  if [[ -n "${TEMP_API_PF_PID:-}" ]]; then kill "$TEMP_API_PF_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "${TEMP_GW_PF_PID:-}" ]]; then kill "$TEMP_GW_PF_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "${TEMP_GRAFANA_DIRECT_PF_PID:-}" ]]; then kill "$TEMP_GRAFANA_DIRECT_PF_PID" >/dev/null 2>&1 || true; fi

  if [[ "${PORT_FORWARD_MODE:-}" == "foreground" ]]; then
    if [[ -n "${API_PF_PID:-}" ]]; then kill "$API_PF_PID" >/dev/null 2>&1 || true; fi
    if [[ -n "${GRAFANA_PF_PID:-}" ]]; then kill "$GRAFANA_PF_PID" >/dev/null 2>&1 || true; fi
    if [[ -n "${UI_PF_PID:-}" ]]; then kill "$UI_PF_PID" >/dev/null 2>&1 || true; fi
  fi
}
trap cleanup EXIT

usage() {
  cat <<USAGE
Smoke installer for Observantio on Kubernetes.

Usage:
  bash installer.sh [options]

Options:
  --release <name>       Helm release name (default: ${RELEASE_NAME})
  --namespace <name>     Kubernetes namespace (default: ${NAMESPACE})
  --chart <path>         Chart path (default: ${CHART_PATH})
  --remove               Teardown smoke stack, namespace, and PVC/PV volumes
  --detach               Start port-forwards in detached mode
  --foreground           Start port-forwards in foreground mode
  --no-port-forward      Do not start port-forwards
  -h, --help             Show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release) RELEASE_NAME="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --chart) CHART_PATH="$2"; shift 2 ;;
    --remove) REMOVE_MODE="true"; shift ;;
    --detach) PORT_FORWARD_MODE="detached"; shift ;;
    --foreground) PORT_FORWARD_MODE="foreground"; shift ;;
    --no-port-forward) START_PORT_FORWARDS="false"; PORT_FORWARD_MODE="disabled"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

for cmd in kubectl helm openssl awk sed grep curl base64 mktemp python3; do
  require_cmd "$cmd"
done

kubectl cluster-info >/dev/null

stop_existing_port_forwards() {
  pkill -f "port-forward svc/${RELEASE_NAME}-observantio-observantio ${API_FORWARD_PORT}:4319" >/dev/null 2>&1 || true
  pkill -f "port-forward svc/${RELEASE_NAME}-observantio-grafana-auth-gateway ${GRAFANA_PROXY_FORWARD_PORT}:8080" >/dev/null 2>&1 || true
  pkill -f "port-forward svc/${RELEASE_NAME}-observantio-ui ${UI_FORWARD_PORT}:80" >/dev/null 2>&1 || true
}

remove_stack() {
  echo "Removing smoke stack: release=${RELEASE_NAME} namespace=${NAMESPACE}"
  stop_existing_port_forwards

  helm -n "$NAMESPACE" uninstall "$RELEASE_NAME" >/dev/null 2>&1 || true

  if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
    kubectl -n "$NAMESPACE" delete pvc --all --wait=false >/dev/null 2>&1 || true

    kubectl get pv -o custom-columns=NAME:.metadata.name,NS:.spec.claimRef.namespace --no-headers 2>/dev/null \
      | awk -v ns="$NAMESPACE" '$2==ns{print $1}' \
      | while read -r pv; do
          [[ -n "$pv" ]] && kubectl delete pv "$pv" --wait=false >/dev/null 2>&1 || true
        done

    kubectl delete ns "$NAMESPACE" --wait=true --timeout=180s >/dev/null 2>&1 || kubectl delete ns "$NAMESPACE" --wait=false >/dev/null 2>&1 || true
  fi

  echo "Smoke environment removed."
}

if [[ "$REMOVE_MODE" == "true" ]]; then
  remove_stack
  exit 0
fi

if ! kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
  kubectl create ns "$NAMESPACE" >/dev/null
fi

if [[ -z "$OBSERVANTIO_USERNAME" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Observantio username [observantio]: " OBSERVANTIO_USERNAME
    OBSERVANTIO_USERNAME="${OBSERVANTIO_USERNAME:-observantio}"
  else
    echo "OBSERVANTIO_USERNAME is required in non-interactive mode" >&2
    exit 1
  fi
fi

if [[ -z "$OBSERVANTIO_PASSWORD" ]]; then
  if [[ -t 0 ]]; then
    while true; do
      read -r -s -p "Observantio password (min 12 chars): " OBSERVANTIO_PASSWORD
      echo
      [[ ${#OBSERVANTIO_PASSWORD} -ge 12 ]] && break
      echo "Password too short."
    done
  else
    echo "OBSERVANTIO_PASSWORD is required in non-interactive mode" >&2
    exit 1
  fi
fi

if [[ -z "$OBSERVANTIO_EMAIL" ]]; then
  OBSERVANTIO_EMAIL="${OBSERVANTIO_USERNAME}@example.com"
fi

SECRET_NAME="${RELEASE_NAME}-observantio-secrets"
TLS_SECRET_NAME="${RELEASE_NAME}-internal-tls"

JWT_PRIVATE_KEY=""
JWT_PUBLIC_KEY=""
NOTIFIER_TOKEN=""
RESOLVER_TOKEN=""
GATEWAY_TOKEN=""
GATEWAY_STATUS_TOKEN=""
DEFAULT_OTLP_TOKEN=""
INBOUND_WEBHOOK_TOKEN=""
OTEL_OTLP_TOKEN=""
OTLP_INGEST_TOKEN=""
JWT_SECRET_KEY=""
DATA_ENCRYPTION_KEY=""
NOTIFIER_CONTEXT_SIGNING_KEY=""
NOTIFIER_CONTEXT_VERIFY_KEY=""
RESOLVER_CONTEXT_SIGNING_KEY=""
RESOLVER_CONTEXT_VERIFY_KEY=""
GRAFANA_PASSWORD=""
GRAFANA_USERNAME="admin"

if [[ "$REUSE_EXISTING_SECRETS" == "true" ]] && kubectl -n "$NAMESPACE" get secret "$SECRET_NAME" >/dev/null 2>&1; then
  JWT_PRIVATE_KEY="$(secret_key_or_empty "$SECRET_NAME" JWT_PRIVATE_KEY)"
  JWT_PUBLIC_KEY="$(secret_key_or_empty "$SECRET_NAME" JWT_PUBLIC_KEY)"
  NOTIFIER_TOKEN="$(secret_key_or_empty "$SECRET_NAME" NOTIFIER_SERVICE_TOKEN)"
  RESOLVER_TOKEN="$(secret_key_or_empty "$SECRET_NAME" RESOLVER_SERVICE_TOKEN)"
  GATEWAY_TOKEN="$(secret_key_or_empty "$SECRET_NAME" GATEWAY_INTERNAL_SERVICE_TOKEN)"
  GATEWAY_STATUS_TOKEN="$(secret_key_or_empty "$SECRET_NAME" GATEWAY_STATUS_OTLP_TOKEN)"
  DEFAULT_OTLP_TOKEN="$(secret_key_or_empty "$SECRET_NAME" DEFAULT_OTLP_TOKEN)"
  OTEL_OTLP_TOKEN="$(secret_key_or_empty "$SECRET_NAME" OTEL_OTLP_TOKEN)"
  INBOUND_WEBHOOK_TOKEN="$(secret_key_or_empty "$SECRET_NAME" INBOUND_WEBHOOK_TOKEN)"
  OTLP_INGEST_TOKEN="$(secret_key_or_empty "$SECRET_NAME" OTLP_INGEST_TOKEN)"
  JWT_SECRET_KEY="$(secret_key_or_empty "$SECRET_NAME" JWT_SECRET_KEY)"
  DATA_ENCRYPTION_KEY="$(secret_key_or_empty "$SECRET_NAME" DATA_ENCRYPTION_KEY)"
  NOTIFIER_CONTEXT_SIGNING_KEY="$(secret_key_or_empty "$SECRET_NAME" NOTIFIER_CONTEXT_SIGNING_KEY)"
  NOTIFIER_CONTEXT_VERIFY_KEY="$(secret_key_or_empty "$SECRET_NAME" NOTIFIER_CONTEXT_VERIFY_KEY)"
  RESOLVER_CONTEXT_SIGNING_KEY="$(secret_key_or_empty "$SECRET_NAME" RESOLVER_CONTEXT_SIGNING_KEY)"
  RESOLVER_CONTEXT_VERIFY_KEY="$(secret_key_or_empty "$SECRET_NAME" RESOLVER_CONTEXT_VERIFY_KEY)"
  GRAFANA_USERNAME="$(secret_key_or_empty "$SECRET_NAME" GRAFANA_USERNAME)"
  GRAFANA_PASSWORD="$(secret_key_or_empty "$SECRET_NAME" GRAFANA_PASSWORD)"
fi

if [[ -z "$JWT_PRIVATE_KEY" || -z "$JWT_PUBLIC_KEY" ]]; then
  JWT_PRIVATE_KEY="$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 2>/dev/null)"
  JWT_PUBLIC_KEY="$(printf '%s' "$JWT_PRIVATE_KEY" | openssl rsa -pubout 2>/dev/null)"
fi

NOTIFIER_TOKEN="${NOTIFIER_TOKEN:-svc_notifier_$(random_hex 16)}"
RESOLVER_TOKEN="${RESOLVER_TOKEN:-svc_resolver_$(random_hex 16)}"
GATEWAY_TOKEN="${GATEWAY_TOKEN:-svc_gateway_$(random_hex 16)}"
GATEWAY_STATUS_TOKEN="${GATEWAY_STATUS_TOKEN:-svc_status_$(random_hex 16)}"
DEFAULT_OTLP_TOKEN="${DEFAULT_OTLP_TOKEN:-otlp_$(random_hex 16)}"
OTEL_OTLP_TOKEN="${OTEL_OTLP_TOKEN:-$DEFAULT_OTLP_TOKEN}"
INBOUND_WEBHOOK_TOKEN="${INBOUND_WEBHOOK_TOKEN:-wh_$(random_hex 16)}"
OTLP_INGEST_TOKEN="${OTLP_INGEST_TOKEN:-ingest_$(random_hex 16)}"
JWT_SECRET_KEY="${JWT_SECRET_KEY:-jwt_$(random_hex 24)}"
DATA_ENCRYPTION_KEY="${DATA_ENCRYPTION_KEY:-$(random_b64_32)}"
NOTIFIER_CONTEXT_SIGNING_KEY="${NOTIFIER_CONTEXT_SIGNING_KEY:-ctx_notifier_$(random_hex 16)}"
NOTIFIER_CONTEXT_VERIFY_KEY="${NOTIFIER_CONTEXT_VERIFY_KEY:-$NOTIFIER_CONTEXT_SIGNING_KEY}"
RESOLVER_CONTEXT_SIGNING_KEY="${RESOLVER_CONTEXT_SIGNING_KEY:-ctx_resolver_$(random_hex 16)}"
RESOLVER_CONTEXT_VERIFY_KEY="${RESOLVER_CONTEXT_VERIFY_KEY:-$RESOLVER_CONTEXT_SIGNING_KEY}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-smoke-grafana-$(random_hex 8)}"

ensure_internal_tls_secret() {
  if [[ "$REUSE_EXISTING_SECRETS" == "true" ]] && kubectl -n "$NAMESPACE" get secret "$TLS_SECRET_NAME" >/dev/null 2>&1; then
    return
  fi

  local tmpdir notifier_svc resolver_svc ca_key ca_crt
  tmpdir="$(mktemp -d)"
  notifier_svc="${RELEASE_NAME}-observantio-notifier"
  resolver_svc="${RELEASE_NAME}-observantio-resolver"
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

    cat > "$ext" <<EXT
subjectAltName=DNS:${svc},DNS:${svc}.${NAMESPACE},DNS:${svc}.${NAMESPACE}.svc,DNS:${svc}.${NAMESPACE}.svc.cluster.local
extendedKeyUsage=serverAuth
EXT

    openssl req -new -newkey rsa:2048 -nodes -keyout "$key" -out "$csr" \
      -subj "/CN=${svc}.${NAMESPACE}.svc" >/dev/null 2>&1
    openssl x509 -req -in "$csr" -CA "$ca_crt" -CAkey "$ca_key" -CAcreateserial \
      -out "$crt" -days 365 -extfile "$ext" >/dev/null 2>&1
  }

  make_cert notifier "$notifier_svc"
  make_cert resolver "$resolver_svc"

  kubectl -n "$NAMESPACE" create secret generic "$TLS_SECRET_NAME" \
    --from-file=ca.crt="${tmpdir}/ca.crt" \
    --from-file=notifier.crt="${tmpdir}/notifier.crt" \
    --from-file=notifier.key="${tmpdir}/notifier.key" \
    --from-file=resolver.crt="${tmpdir}/resolver.crt" \
    --from-file=resolver.key="${tmpdir}/resolver.key" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null

  rm -rf "$tmpdir"
}

ensure_internal_tls_secret

NOTIFIER_SVC="${RELEASE_NAME}-observantio-notifier"
RESOLVER_SVC="${RELEASE_NAME}-observantio-resolver"

echo "Deploying smoke release ${RELEASE_NAME} in namespace ${NAMESPACE}"
helm upgrade --install "$RELEASE_NAME" "$CHART_PATH" \
  -n "$NAMESPACE" \
  --timeout "$HELM_TIMEOUT" \
  --set secrets.create=true \
  --set secrets.existingSecretName= \
  --set-string secrets.POSTGRES_USER=watchdog \
  --set-string secrets.POSTGRES_PASSWORD=watchdog \
  --set-string secrets.POSTGRES_DB=watchdog \
  --set-string secrets.JWT_SECRET_KEY="$JWT_SECRET_KEY" \
  --set-string secrets.JWT_PRIVATE_KEY="$JWT_PRIVATE_KEY" \
  --set-string secrets.JWT_PUBLIC_KEY="$JWT_PUBLIC_KEY" \
  --set-string secrets.DATA_ENCRYPTION_KEY="$DATA_ENCRYPTION_KEY" \
  --set-string secrets.DEFAULT_OTLP_TOKEN="$DEFAULT_OTLP_TOKEN" \
  --set-string secrets.OTEL_OTLP_TOKEN="$OTEL_OTLP_TOKEN" \
  --set-string secrets.INBOUND_WEBHOOK_TOKEN="$INBOUND_WEBHOOK_TOKEN" \
  --set-string secrets.OTLP_INGEST_TOKEN="$OTLP_INGEST_TOKEN" \
  --set-string secrets.GATEWAY_INTERNAL_SERVICE_TOKEN="$GATEWAY_TOKEN" \
  --set-string secrets.GATEWAY_STATUS_OTLP_TOKEN="$GATEWAY_STATUS_TOKEN" \
  --set-string secrets.NOTIFIER_SERVICE_TOKEN="$NOTIFIER_TOKEN" \
  --set-string secrets.NOTIFIER_EXPECTED_SERVICE_TOKEN="$NOTIFIER_TOKEN" \
  --set-string secrets.NOTIFIER_CONTEXT_SIGNING_KEY="$NOTIFIER_CONTEXT_SIGNING_KEY" \
  --set-string secrets.NOTIFIER_CONTEXT_VERIFY_KEY="$NOTIFIER_CONTEXT_VERIFY_KEY" \
  --set-string secrets.RESOLVER_SERVICE_TOKEN="$RESOLVER_TOKEN" \
  --set-string secrets.RESOLVER_EXPECTED_SERVICE_TOKEN="$RESOLVER_TOKEN" \
  --set-string secrets.RESOLVER_CONTEXT_SIGNING_KEY="$RESOLVER_CONTEXT_SIGNING_KEY" \
  --set-string secrets.RESOLVER_CONTEXT_VERIFY_KEY="$RESOLVER_CONTEXT_VERIFY_KEY" \
  --set-string secrets.GRAFANA_USERNAME="$GRAFANA_USERNAME" \
  --set-string secrets.GRAFANA_PASSWORD="$GRAFANA_PASSWORD" \
  --set observantio.replicaCount=1 \
  --set gatekeeper.replicaCount=1 \
  --set notifier.replicaCount=1 \
  --set resolver.replicaCount=1 \
  --set grafanaAuthGateway.replicaCount=1 \
  --set otlpGateway.replicaCount=1 \
  --set ui.replicaCount=1 \
  --set otelAgent.enabled=true \
  --set grafana.storage.enabled=false \
  --set internalTLS.enabled=false \
  --set-string internalTLS.secretName="$TLS_SECRET_NAME" \
  --set notifier.tls.enabled=false \
  --set resolver.tls.enabled=false \
  --set autoscaling.observantio.enabled=false \
  --set autoscaling.gatekeeper.enabled=false \
  --set autoscaling.notifier.enabled=false \
  --set autoscaling.resolver.enabled=false \
  --set observantio.resources.requests.cpu=50m \
  --set observantio.resources.requests.memory=256Mi \
  --set observantio.resources.limits.cpu=500m \
  --set observantio.resources.limits.memory=768Mi \
  --set gatekeeper.resources.requests.cpu=50m \
  --set gatekeeper.resources.requests.memory=128Mi \
  --set gatekeeper.resources.limits.cpu=300m \
  --set gatekeeper.resources.limits.memory=384Mi \
  --set notifier.resources.requests.cpu=50m \
  --set notifier.resources.requests.memory=192Mi \
  --set notifier.resources.limits.cpu=500m \
  --set notifier.resources.limits.memory=512Mi \
  --set resolver.resources.requests.cpu=100m \
  --set resolver.resources.requests.memory=256Mi \
  --set resolver.resources.limits.cpu=700m \
  --set resolver.resources.limits.memory=1Gi \
  --set loki.resources.requests.cpu=100m \
  --set loki.resources.requests.memory=256Mi \
  --set mimir.resources.requests.cpu=100m \
  --set mimir.resources.requests.memory=256Mi \
  --set tempo.resources.requests.cpu=100m \
  --set tempo.resources.requests.memory=256Mi \
  --set grafana.resources.requests.cpu=50m \
  --set grafana.resources.requests.memory=192Mi \
  --set alertmanager.resources.requests.cpu=50m \
  --set alertmanager.resources.requests.memory=128Mi \
  --set otlpGateway.resources.requests.cpu=50m \
  --set otlpGateway.resources.requests.memory=128Mi \
  --set otelAgent.resources.requests.cpu=50m \
  --set otelAgent.resources.requests.memory=128Mi \
  --set networkPolicy.enabled=false \
  --set grafanaAuthGateway.enabled=true \
  --set-string observantio.env.NOTIFIER_URL="http://${NOTIFIER_SVC}:4323" \
  --set-string observantio.env.NOTIFIER_TLS_ENABLED='false' \
  --set-string observantio.env.RESOLVER_URL="http://${RESOLVER_SVC}:4322" \
  --set-string observantio.env.RESOLVER_TLS_ENABLED='false' \
  --set-string observantio.env.CORS_ORIGINS='http://127.0.0.1:5173\,http://localhost:5173' \
  --set-string observantio.env.CORS_ALLOW_CREDENTIALS='true' \
  --set-string observantio.env.APP_ENV='development' \
  --set-string observantio.env.ENVIRONMENT='development' \
  --set-string observantio.env.DEFAULT_ADMIN_USERNAME="$OBSERVANTIO_USERNAME" \
  --set-string observantio.env.DEFAULT_ADMIN_EMAIL="$OBSERVANTIO_EMAIL" \
  --set-string observantio.env.DEFAULT_ADMIN_PASSWORD="$OBSERVANTIO_PASSWORD" \
  --set-string gatekeeper.env.APP_ENV='development' \
  --set-string gatekeeper.env.ENVIRONMENT='development' \
  --set-string notifier.env.APP_ENV='development' \
  --set-string notifier.env.ENVIRONMENT='development' \
  --set-string resolver.env.APP_ENV='development' \
  --set-string resolver.env.ENVIRONMENT='development' >/dev/null

wait_ready_pod_for_component "observantio"
wait_ready_pod_for_component "notifier"
wait_ready_pod_for_component "resolver"
wait_ready_pod_for_component "grafana"

WATCHDOG_POD="$(get_ready_pod_name observantio)"
NOTIFIER_POD="$(get_ready_pod_name notifier)"
RESOLVER_POD="$(get_ready_pod_name resolver)"

[[ -n "$WATCHDOG_POD" ]] || { echo "No ready observantio pod found" >&2; exit 1; }
[[ -n "$NOTIFIER_POD" ]] || { echo "No ready notifier pod found" >&2; exit 1; }
[[ -n "$RESOLVER_POD" ]] || { echo "No ready resolver pod found" >&2; exit 1; }

WD_NOTIFIER_SHA="$(kubectl -n "$NAMESPACE" exec "$WATCHDOG_POD" -- sh -lc 'v=$(printenv NOTIFIER_SERVICE_TOKEN||true); printf %s "$v" | sha256sum | cut -d" " -f1')"
WD_RESOLVER_SHA="$(kubectl -n "$NAMESPACE" exec "$WATCHDOG_POD" -- sh -lc 'v=$(printenv RESOLVER_SERVICE_TOKEN||true); printf %s "$v" | sha256sum | cut -d" " -f1')"
NO_EXPECTED_SHA="$(kubectl -n "$NAMESPACE" exec "$NOTIFIER_POD" -- sh -lc 'v=$(printenv NOTIFIER_EXPECTED_SERVICE_TOKEN||true); printf %s "$v" | sha256sum | cut -d" " -f1')"
RE_EXPECTED_SHA="$(kubectl -n "$NAMESPACE" exec "$RESOLVER_POD" -- sh -lc 'v=$(printenv RESOLVER_EXPECTED_SERVICE_TOKEN||true); printf %s "$v" | sha256sum | cut -d" " -f1')"

[[ "$WD_NOTIFIER_SHA" == "$NO_EXPECTED_SHA" ]] || { echo "Notifier token mismatch" >&2; exit 1; }
[[ "$WD_RESOLVER_SHA" == "$RE_EXPECTED_SHA" ]] || { echo "Resolver token mismatch" >&2; exit 1; }

kubectl -n "$NAMESPACE" exec -i "$WATCHDOG_POD" -- \
  env OBS_USER="$OBSERVANTIO_USERNAME" OBS_EMAIL="$OBSERVANTIO_EMAIL" OBS_PASS="$OBSERVANTIO_PASSWORD" \
  python - <<'PY'
import os
import uuid
from sqlalchemy import func

from config import config
from database import init_database, get_db_session
from db_models import Tenant, User
from services.database_auth_service import DatabaseAuthService

username = os.environ['OBS_USER']
email = os.environ['OBS_EMAIL']
password = os.environ['OBS_PASS']

init_database(config.DATABASE_URL)
service = DatabaseAuthService()
password_hash = service.hash_password(password)

with get_db_session() as db:
    admin = (
        db.query(User)
        .filter(User.is_superuser.is_(True))
        .order_by(User.created_at.asc())
        .first()
    )
    if admin is None:
        tenant_name = (getattr(config, "DEFAULT_ADMIN_TENANT", "") or "default").strip()
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
        admin_tenant_id = tenant.id
        admin_org_id = getattr(config, "DEFAULT_ORG_ID", "default")
    else:
        admin_tenant_id = admin.tenant_id
        admin_org_id = admin.org_id or config.DEFAULT_ORG_ID
    user = db.query(User).filter(func.lower(User.username) == username.lower()).first()
    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            tenant_id=admin_tenant_id,
            org_id=admin_org_id,
            username=username,
            email=email,
            hashed_password=password_hash,
            full_name='Observantio Admin',
            role='admin',
            is_active=True,
            is_superuser=True,
            needs_password_change=False,
            mfa_enabled=False,
            must_setup_mfa=False,
            auth_provider='local',
        )
        db.add(user)
        db.flush()
    else:
        user.tenant_id = admin_tenant_id
        user.org_id = admin_org_id
        user.email = email
        user.hashed_password = password_hash
        user.role = 'admin'
        user.is_active = True
        user.is_superuser = True
        user.needs_password_change = False
        user.mfa_enabled = False
        user.must_setup_mfa = False
        user.auth_provider = 'local'
        db.flush()

    service.ensure_default_api_key(db, user)
PY

# Validate/repair Grafana admin auth and clear rogue dashboards.
kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-observantio-grafana "${GRAFANA_DIRECT_CHECK_PORT}:3000" >/tmp/observantio-grafana-direct-check.log 2>&1 &
TEMP_GRAFANA_DIRECT_PF_PID=$!
sleep 2

GRAFANA_DATASOURCES_CODE="$(curl -sS -o /tmp/observantio-grafana-datasources.json -w '%{http_code}' -u "${GRAFANA_USERNAME}:${GRAFANA_PASSWORD}" "http://127.0.0.1:${GRAFANA_DIRECT_CHECK_PORT}/api/datasources" || true)"
if [[ "$GRAFANA_DATASOURCES_CODE" != "200" ]]; then
  GRAFANA_USER_LOOKUP_JSON="$(curl -sS -H "X-WEBAUTH-USER: ${GRAFANA_USERNAME}" -H "X-WEBAUTH-EMAIL: ${GRAFANA_USERNAME}@example.com" -H "X-WEBAUTH-NAME: ${GRAFANA_USERNAME}" -H 'X-WEBAUTH-ROLE: Admin' "http://127.0.0.1:${GRAFANA_DIRECT_CHECK_PORT}/api/users/lookup?loginOrEmail=${GRAFANA_USERNAME}" || true)"
  GRAFANA_USER_ID="$(printf '%s' "$GRAFANA_USER_LOOKUP_JSON" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')"
  [[ -n "$GRAFANA_USER_ID" ]] || { echo "Unable to resolve Grafana admin user" >&2; exit 1; }
  curl -sS -X PUT -H 'Content-Type: application/json' -H "X-WEBAUTH-USER: ${GRAFANA_USERNAME}" -H "X-WEBAUTH-EMAIL: ${GRAFANA_USERNAME}@example.com" -H "X-WEBAUTH-NAME: ${GRAFANA_USERNAME}" -H 'X-WEBAUTH-ROLE: Admin' -d "{\"password\":\"${GRAFANA_PASSWORD}\"}" "http://127.0.0.1:${GRAFANA_DIRECT_CHECK_PORT}/api/admin/users/${GRAFANA_USER_ID}/password" >/dev/null
fi

DASH_UIDS="$(curl -sS -u "${GRAFANA_USERNAME}:${GRAFANA_PASSWORD}" "http://127.0.0.1:${GRAFANA_DIRECT_CHECK_PORT}/api/search?type=dash-db" | grep -o '"uid":"[^"]*"' | cut -d'"' -f4 | sort -u || true)"
if [[ -n "$DASH_UIDS" ]]; then
  while read -r uid; do
    [[ -n "$uid" ]] || continue
    curl -sS -X DELETE -u "${GRAFANA_USERNAME}:${GRAFANA_PASSWORD}" "http://127.0.0.1:${GRAFANA_DIRECT_CHECK_PORT}/api/dashboards/uid/${uid}" >/dev/null || true
  done <<< "$DASH_UIDS"
fi

kill "$TEMP_GRAFANA_DIRECT_PF_PID" >/dev/null 2>&1 || true
unset TEMP_GRAFANA_DIRECT_PF_PID

mkdir -p "$PORT_FORWARD_LOG_DIR"
kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-observantio-observantio "$LOCAL_API_PORT":4319 >"${PORT_FORWARD_LOG_DIR}/tmp-api.log" 2>&1 &
TEMP_API_PF_PID=$!
kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-observantio-grafana-auth-gateway 18080:8080 >"${PORT_FORWARD_LOG_DIR}/tmp-grafana-gateway.log" 2>&1 &
TEMP_GW_PF_PID=$!
sleep 2

curl -fsS "http://127.0.0.1:${LOCAL_API_PORT}/health" >/dev/null

curl -sS -o /dev/null -D /tmp/observantio-api-cors.headers -X OPTIONS "http://127.0.0.1:${LOCAL_API_PORT}/api/auth/login" -H 'Origin: http://127.0.0.1:5173' -H 'Access-Control-Request-Method: POST'
grep -iq '^access-control-allow-origin: http://127.0.0.1:5173$' < <(tr -d '\r' </tmp/observantio-api-cors.headers) || { echo "API CORS check failed" >&2; exit 1; }

curl -sS -o /dev/null -D /tmp/observantio-grafana-gateway-cors.headers -X OPTIONS "http://127.0.0.1:18080/grafana/bootstrap" -H 'Origin: http://127.0.0.1:5173' -H 'Access-Control-Request-Method: GET'
grep -iq '^access-control-allow-origin: http://127.0.0.1:5173$' < <(tr -d '\r' </tmp/observantio-grafana-gateway-cors.headers) || { echo "Grafana gateway CORS check failed" >&2; exit 1; }

LOGIN_PAYLOAD="$(build_login_payload "$OBSERVANTIO_USERNAME" "$OBSERVANTIO_PASSWORD")"
LOGIN_HTTP_CODE="$(curl -sS -o /tmp/observantio-installer-login.json -w '%{http_code}' -X POST "http://127.0.0.1:${LOCAL_API_PORT}/api/auth/login" -H 'Content-Type: application/json' -d "$LOGIN_PAYLOAD")"
ACCESS_TOKEN="$(sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' /tmp/observantio-installer-login.json)"

if [[ "$LOGIN_HTTP_CODE" != "200" ]] && grep -q '"mfa_setup_required"[[:space:]]*:[[:space:]]*true' /tmp/observantio-installer-login.json; then
  kubectl -n "$NAMESPACE" exec -i "$WATCHDOG_POD" -- \
    env OBS_USER="$OBSERVANTIO_USERNAME" \
    python - <<'PY'
import os
from sqlalchemy import func

from database import get_db_session
from db_models import User

username = os.environ["OBS_USER"]
with get_db_session() as db:
    user = db.query(User).filter(func.lower(User.username) == username.lower()).first()
    if user:
        user.mfa_enabled = False
        user.must_setup_mfa = False
        user.totp_secret = None
        user.mfa_recovery_hashes = None
        db.flush()
PY
  LOGIN_HTTP_CODE="$(curl -sS -o /tmp/observantio-installer-login.json -w '%{http_code}' -X POST "http://127.0.0.1:${LOCAL_API_PORT}/api/auth/login" -H 'Content-Type: application/json' -d "$LOGIN_PAYLOAD")"
  ACCESS_TOKEN="$(sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' /tmp/observantio-installer-login.json)"
fi

if [[ "$LOGIN_HTTP_CODE" != "200" || -z "$ACCESS_TOKEN" ]]; then
  echo "Login smoke check failed (HTTP ${LOGIN_HTTP_CODE})" >&2
  exit 1
fi

API_KEYS_JSON="$(curl -sS "http://127.0.0.1:${LOCAL_API_PORT}/api/auth/api-keys" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
[[ "$API_KEYS_JSON" == *'"is_default":true'* && "$API_KEYS_JSON" == *'"is_enabled":true'* ]] || { echo "Default enabled API key missing" >&2; exit 1; }

ALERTMANAGER_MUTATION_BODY="$(curl -sS -X POST "http://127.0.0.1:${LOCAL_API_PORT}/api/alertmanager/silences" -H "Authorization: Bearer ${ACCESS_TOKEN}" -H 'Content-Type: application/json' -d '{}')"
[[ "$ALERTMANAGER_MUTATION_BODY" != *"No active API key available for this operation"* ]] || { echo "Notifier API key path still failing" >&2; exit 1; }

DATASOURCES_BODY="$(curl -sS "http://127.0.0.1:${LOCAL_API_PORT}/api/grafana/datasources" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
[[ "$DATASOURCES_BODY" != "[]" ]] || { echo "No Grafana datasources visible" >&2; exit 1; }

AGENTS_ACTIVE_BODY="$(curl -sS "http://127.0.0.1:${LOCAL_API_PORT}/api/agents/active" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
[[ "$AGENTS_ACTIVE_BODY" != "[]" ]] || { echo "No active OTEL agent activity" >&2; exit 1; }

if [[ -n "${TEMP_API_PF_PID:-}" ]]; then kill "$TEMP_API_PF_PID" >/dev/null 2>&1 || true; unset TEMP_API_PF_PID; fi
if [[ -n "${TEMP_GW_PF_PID:-}" ]]; then kill "$TEMP_GW_PF_PID" >/dev/null 2>&1 || true; unset TEMP_GW_PF_PID; fi

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
  if [[ "$PORT_FORWARD_MODE" == "detached" ]]; then
    nohup kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-observantio-observantio "${API_FORWARD_PORT}:4319" >"${PORT_FORWARD_LOG_DIR}/api.log" 2>&1 &
    API_PF_PID=$!
    nohup kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-observantio-grafana-auth-gateway "${GRAFANA_PROXY_FORWARD_PORT}:8080" >"${PORT_FORWARD_LOG_DIR}/grafana-gateway.log" 2>&1 &
    GRAFANA_PF_PID=$!
    nohup kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-observantio-ui "${UI_FORWARD_PORT}:80" >"${PORT_FORWARD_LOG_DIR}/ui.log" 2>&1 &
    UI_PF_PID=$!
  else
    kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-observantio-observantio "${API_FORWARD_PORT}:4319" >"${PORT_FORWARD_LOG_DIR}/api.log" 2>&1 &
    API_PF_PID=$!
    kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-observantio-grafana-auth-gateway "${GRAFANA_PROXY_FORWARD_PORT}:8080" >"${PORT_FORWARD_LOG_DIR}/grafana-gateway.log" 2>&1 &
    GRAFANA_PF_PID=$!
    kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-observantio-ui "${UI_FORWARD_PORT}:80" >"${PORT_FORWARD_LOG_DIR}/ui.log" 2>&1 &
    UI_PF_PID=$!
  fi

  sleep 2
  curl -fsS "http://127.0.0.1:${API_FORWARD_PORT}/health" >/dev/null
  curl -fsS "http://127.0.0.1:${UI_FORWARD_PORT}/" >/dev/null
fi

echo
echo "Smoke install complete"
echo "  Namespace:            ${NAMESPACE}"
echo "  Release:              ${RELEASE_NAME}"
echo "  Observantio API:      http://127.0.0.1:${LOCAL_API_PORT}"
echo "  Observantio Username: ${OBSERVANTIO_USERNAME}"
echo "  Observantio Password: ${OBSERVANTIO_PASSWORD}"
echo "  Internal TLS certs:   generated in secret ${TLS_SECRET_NAME}"
echo

echo "This is a smoke setup for Kubernetes (single-node/dev-friendly, not production hardening)."

echo
if [[ "$START_PORT_FORWARDS" == "true" ]]; then
  echo "Port-forwards:"
  echo "  API:           http://127.0.0.1:${API_FORWARD_PORT}"
  echo "  Grafana proxy: http://127.0.0.1:${GRAFANA_PROXY_FORWARD_PORT}/grafana/"
  echo "  UI:            http://127.0.0.1:${UI_FORWARD_PORT}/"
  echo "  Logs:          ${PORT_FORWARD_LOG_DIR}"
  if [[ "$PORT_FORWARD_MODE" == "foreground" ]]; then
    echo
    echo "Foreground mode. Press Ctrl+C to stop forwards."
    wait "$API_PF_PID" "$GRAFANA_PF_PID" "$UI_PF_PID"
  fi
else
  echo "Port-forwards disabled."
  echo "  kubectl -n ${NAMESPACE} port-forward svc/${RELEASE_NAME}-observantio-observantio ${API_FORWARD_PORT}:4319"
  echo "  kubectl -n ${NAMESPACE} port-forward svc/${RELEASE_NAME}-observantio-grafana-auth-gateway ${GRAFANA_PROXY_FORWARD_PORT}:8080"
  echo "  kubectl -n ${NAMESPACE} port-forward svc/${RELEASE_NAME}-observantio-ui ${UI_FORWARD_PORT}:80"
fi
