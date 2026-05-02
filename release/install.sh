#!/usr/bin/env bash

# Observantio Release Installation Script
# This script sets up the environment for running Observantio from a release bundle.
# All Rights Reserved. (c) 2026 Stefan Kumarasinghe

set -euo pipefail

usage() {
  cat <<'USAGE'
$(colorize "${C_MAGENTA}${C_BOLD}" "Observantio release installer")

$(colorize "${C_CYAN}${C_BOLD}" "Usage:")
  ./release/install.sh [--help]

$(colorize "${C_CYAN}${C_BOLD}" "What it does:")
  - Verifies Docker and Docker Compose access for the current user.
  - Creates .env from .env.example when needed and keeps a backup copy.
  - Randomizes insecure defaults and updates host-facing URLs.
  - Runs the host-aware observability config generator.
  - Pulls images and optionally starts the compose stack.

$(colorize "${C_CYAN}${C_BOLD}" "Notes:")
  - This installer is interactive and must be run from a terminal.
  - Use the release bundle README and DEPLOYMENT guide for the full flow.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 0 ]]; then
  err "Unknown option: $1"
  usage >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/docker-compose.prod.yml" ]]; then
  ROOT_DIR="${SCRIPT_DIR}"
elif [[ -f "${SCRIPT_DIR}/../docker-compose.prod.yml" ]]; then
  ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
  err "docker-compose.prod.yml not found next to this script or in its parent directory."
  exit 1
fi

cd "${ROOT_DIR}"

USE_COLOR="0"
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  USE_COLOR="1"
fi
USE_EMOJI="0"
if [[ -t 1 && "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" == *"UTF-8"* ]]; then
  USE_EMOJI="1"
fi
if [[ "${OBSERVANTIO_EMOJI:-auto}" == "0" ]]; then
  USE_EMOJI="0"
elif [[ "${OBSERVANTIO_EMOJI:-auto}" == "1" ]]; then
  USE_EMOJI="1"
fi

C_RESET=$'\033[0m'
C_BOLD=$'\033[1m'
C_DIM=$'\033[2m'
C_CYAN=$'\033[36m'
C_GREEN=$'\033[32m'
C_YELLOW=$'\033[33m'
C_RED=$'\033[31m'
C_MAGENTA=$'\033[35m'

EM_INFO="i"
EM_OK="+"
EM_WARN="!"
EM_ERR="x"
if [[ "$USE_EMOJI" == "1" ]]; then
  EM_INFO="ⓘ"
  EM_OK="✔"
  EM_WARN="⚠"
  EM_ERR="✖"
fi

colorize() {
  local code="$1"
  shift
  if [[ "$USE_COLOR" == "1" ]]; then
    printf '%b%s%b' "$code" "$*" "$C_RESET"
  else
    printf '%s' "$*"
  fi
}

banner() {
  printf '\n%s\n%s\n%s\n\n' \
    "$(colorize "${C_MAGENTA}${C_BOLD}" "Observantio Release Installer")" \
    "$(colorize "${C_CYAN}" "Let's be observant together! Support us on GitHub")" \
    "$(colorize "${C_DIM}" "------------------------------------------------------------")"
}

section() {
  printf '%s\n' "$(colorize "${C_BOLD}${C_CYAN}" "$*")"
}

info() {
  printf '%s %s %s\n' "$(colorize "$C_CYAN" "[INFO]")" "$EM_INFO" "$(colorize "$C_CYAN" "$*")"
}

ok() {
  printf '%s %s %s\n' "$(colorize "$C_GREEN" "[OK]")" "$EM_OK" "$(colorize "$C_GREEN" "$*")"
}

warn() {
  printf '%s %s %s\n' "$(colorize "$C_YELLOW" "[WARN]")" "$EM_WARN" "$(colorize "$C_YELLOW" "$*")"
}

err() {
  printf '%s %s %s\n' "$(colorize "$C_RED" "[ERROR]")" "$EM_ERR" "$(colorize "$C_RED" "$*")" >&2
}

port_label() {
  case "$1" in
    4319) printf '%s' "API" ;;
    4320) printf '%s' "OTLP gateway" ;;
    4323) printf '%s' "Notifier" ;;
    5173) printf '%s' "UI" ;;
    8080) printf '%s' "Grafana proxy" ;;
    *)    printf '%s' "Port $1" ;;
  esac
}

port_is_listening() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn "( sport = :${port} )" 2>/dev/null | grep -q .
    return $?
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  return 1
}

preflight_host_ports() {
  local ports=(4319 4320 4323 5173 8080)
  local busy=()
  local port

  if ! command -v ss >/dev/null 2>&1 && ! command -v lsof >/dev/null 2>&1; then
    warn "Port preflight skipped because ss/lsof is unavailable."
    return 0
  fi

  for port in "${ports[@]}"; do
    if port_is_listening "$port"; then
      busy+=("$port")
    fi
  done

  [[ "${#busy[@]}" -eq 0 ]] && return 0

  echo ""
  err "Cannot start because one or more required host ports are already in use."
  for port in "${busy[@]}"; do
    warn "Port ${port} ($(port_label "$port")) is busy."
  done
  echo ""
  echo "Helpful checks:"
  echo "  ss -ltnp 'sport = :4323'"
  echo "  docker ps --format 'table {{.Names}}\t{{.Ports}}'"
  echo "If this is another Observantio stack, stop it first and rerun the installer."
  echo ""
  return 1
}

ENV_BACKUP=""
INSTALL_COMPLETE="0"

backup_env_file() {
  if [[ ! -f .env ]]; then
    return
  fi

  local stamp
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  ENV_BACKUP=".env.backup-${stamp}"
  cp .env "${ENV_BACKUP}"
  ok "Backed up existing .env to ${ENV_BACKUP}"
}

restore_env_on_failure() {
  local exit_code="$?"
  trap - ERR INT TERM
  if [[ "${INSTALL_COMPLETE}" != "1" && -n "${ENV_BACKUP}" && -f "${ENV_BACKUP}" ]]; then
    cp "${ENV_BACKUP}" .env
    warn "Restored .env from ${ENV_BACKUP}"
  fi
  exit "${exit_code}"
}

trap restore_env_on_failure ERR INT TERM

require_docker_access() {
  if docker info >/dev/null 2>&1; then
    return
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
      err "Docker is only accessible via sudo on this host. Add your user to the docker group before continuing."
    exit 1
  fi

    err "Docker is installed but not usable by the current user. Add your user to the docker group or configure non-interactive access first."
  exit 1
}

require_compose_access() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
    return
  fi

  if command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
    return
  fi

  if command -v sudo >/dev/null 2>&1; then
    if sudo -n docker compose version >/dev/null 2>&1 || { command -v docker-compose >/dev/null 2>&1 && sudo -n docker-compose version >/dev/null 2>&1; }; then
        err "Docker Compose is only accessible via sudo on this host. Add your user to the docker group before continuing."
      exit 1
    fi
  fi

    err "Docker compose (plugin) or docker-compose is required. Please install Docker Compose and try again."
  exit 1
}

if ! command -v docker >/dev/null 2>&1; then
   err "Docker is required but not installed. Please install Docker and try again. Go to the observantio folder and the extracted folder and rerun the install.sh script"
  exit 1
fi

require_docker_access
require_compose_access

if [[ ! -f ".env" ]]; then
  if [[ ! -f ".env.example" ]]; then
    err "Missing required file: .env.example"
    exit 1
  fi
  cp .env.example .env
fi

backup_env_file

RUN_OPTIMAL_SCRIPT="${ROOT_DIR}/scripts/run_optimal_config.sh"
if [[ ! -f "${RUN_OPTIMAL_SCRIPT}" ]]; then
  err "Missing required script: ${RUN_OPTIMAL_SCRIPT}"
  err "This release bundle is incomplete. Re-download the release tarball."
  exit 1
fi
chmod +x "${RUN_OPTIMAL_SCRIPT}"

randomized_keys=()
bundle_version_keys=()

set_env_key() {
  local key="$1"
  local value="$2"
  local tmp_file
  tmp_file="$(mktemp)"
  awk -v k="$key" -v v="$value" 'BEGIN { FS="="; OFS="="; replaced=0 }
    $1 == k { print k "=" v; replaced=1; next }
    { print $0 }
    END { if (!replaced) print k "=" v }
  ' .env > "$tmp_file"
  mv "$tmp_file" .env
}

get_env_key() {
  local key="$1"
  awk -v k="$key" 'BEGIN { FS="=" }
    $1 == k { print substr($0, index($0, "=") + 1); exit }
  ' .env
}

random_hex() {
  local length="$1"
  local bytes=$(( (length + 1) / 2 ))
  local result
  if command -v openssl >/dev/null 2>&1; then
    result="$(openssl rand -hex "${bytes}")"
  elif [[ -r /dev/urandom ]]; then
    result="$(od -An -N"${bytes}" -tx1 /dev/urandom | tr -d ' \n')"
  else
      err "random_hex: no entropy source available (openssl or /dev/urandom required)"
    exit 1
  fi
  printf '%s' "${result:0:${length}}"
}

random_fernet_key() {
  local raw
  if command -v python3 >/dev/null 2>&1; then
    raw="$(python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
  elif command -v openssl >/dev/null 2>&1; then
    raw="$(openssl rand -base64 32 | tr -d '\n' | tr '+/' '-_')"
  elif [[ -r /dev/urandom ]]; then
    raw="$(head -c 32 /dev/urandom | base64 | tr -d '\n' | tr '+/' '-_')"
  else
      err "random_fernet_key: no entropy source available"
    exit 1
  fi
  printf '%s' "$raw"
}

is_insecure_value() {
  local current="$1"
  local known_default="${2:-}"
  [[ -z "${current}" || "${current}" == replace_with_* || "${current}" == changeme* || "${current}" == "${known_default}" ]]
}

looks_like_pem_private_key() {
  local value="$1"
  [[ "${value}" == *"-----BEGIN PRIVATE KEY-----"* || "${value}" == *"-----BEGIN RSA PRIVATE KEY-----"* || "${value}" == *"-----BEGIN EC PRIVATE KEY-----"* ]]
}

looks_like_pem_public_key() {
  local value="$1"
  [[ "${value}" == *"-----BEGIN PUBLIC KEY-----"* || "${value}" == *"-----BEGIN RSA PUBLIC KEY-----"* ]]
}

set_secret_if_insecure() {
  local key="$1"
  local known_default="$2"
  local new_value="$3"
  if [[ -z "${new_value}" ]]; then
     err "set_secret_if_insecure: generated empty value for ${key}"
    exit 1
  fi
  local current
  current="$(get_env_key "${key}")"
  if is_insecure_value "${current}" "${known_default}"; then
    set_env_key "${key}" "${new_value}"
    randomized_keys+=("${key}")
  fi
}

read_version_json_field() {
  local key="$1"
  local manifest_path

  for manifest_path in "${ROOT_DIR}/versions.json" "${SCRIPT_DIR}/versions.json" "${ROOT_DIR}/release/versions.json"; do
    if [[ -f "${manifest_path}" ]]; then
      sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "${manifest_path}" | head -n1
      return 0
    fi
  done
}

normalize_bundle_image_tag() {
  local key="$1"
  local value="$2"
  local current

  current="$(get_env_key "${key}")"
  if [[ -z "${current}" || "${current}" == "v0.0.0" || "${current}" == replace_with_* || "${current}" == changeme* || "${current}" != "${value}" ]]; then
    set_env_key "${key}" "${value}"
    bundle_version_keys+=("${key}")
  fi
}

bundle_version="$(read_version_json_field bundle_version)"
if [[ -z "${bundle_version}" ]]; then
  bundle_version="$(get_env_key OBSERVANTIO_BUNDLE_VERSION)"
fi
if [[ -z "${bundle_version}" ]]; then
  bundle_version="v0.0.6"
fi

if [[ -z "$(get_env_key OBSERVANTIO_BUNDLE_VERSION)" || "$(get_env_key OBSERVANTIO_BUNDLE_VERSION)" == "v0.0.0" || "$(get_env_key OBSERVANTIO_BUNDLE_VERSION)" != "${bundle_version}" ]]; then
  set_env_key "OBSERVANTIO_BUNDLE_VERSION" "${bundle_version}"
  bundle_version_keys+=("OBSERVANTIO_BUNDLE_VERSION")
fi

watchdog_version="$(read_version_json_field watchdog)"
gatekeeper_version="$(read_version_json_field gatekeeper)"
ui_version="$(read_version_json_field ui)"
otel_agent_version="$(read_version_json_field otel_agent)"
notifier_version="$(read_version_json_field notifier)"
resolver_version="$(read_version_json_field resolver)"

normalize_bundle_image_tag "IMAGE_TAG_WATCHDOG" "${watchdog_version:-$bundle_version}"
normalize_bundle_image_tag "IMAGE_TAG_GATEKEEPER" "${gatekeeper_version:-$bundle_version}"
normalize_bundle_image_tag "IMAGE_TAG_UI" "${ui_version:-$bundle_version}"
normalize_bundle_image_tag "IMAGE_TAG_OTEL_AGENT" "${otel_agent_version:-$bundle_version}"
normalize_bundle_image_tag "IMAGE_TAG_NOTIFIER" "${notifier_version:-$bundle_version}"
normalize_bundle_image_tag "IMAGE_TAG_RESOLVER" "${resolver_version:-$bundle_version}"

old_postgres_password="$(get_env_key POSTGRES_PASSWORD)"
new_postgres_password="${old_postgres_password}"
if is_insecure_value "${old_postgres_password}" "Y7vK2mP9sQ4tN8wX3zR6cD1fH5jL0bG"; then
  new_postgres_password="$(random_hex 48)"
  set_env_key "POSTGRES_PASSWORD" "${new_postgres_password}"
  randomized_keys+=("POSTGRES_PASSWORD")
fi

if [[ "${new_postgres_password}" != "${old_postgres_password}" && -n "${old_postgres_password}" ]]; then
  for db_key in DATABASE_URL NOTIFIER_DATABASE_URL RESOLVER_DATABASE_URL; do
    current_db_url="$(get_env_key "${db_key}")"
    if [[ -n "${current_db_url}" && "${current_db_url}" == *"${old_postgres_password}"* ]]; then
      updated_url="$(printf '%s' "${current_db_url}" | sed "s|${old_postgres_password}|${new_postgres_password}|g")"
      set_env_key "${db_key}" "${updated_url}"
      randomized_keys+=("${db_key}")
    fi
  done
fi

set_secret_if_insecure "JWT_SECRET_KEY" "S3cr3tK3yF0rJWTs&s3cur3R4nd0mStr1ngG3n3r4t0r" "$(random_hex 64)"

jwt_algorithm="$(get_env_key JWT_ALGORITHM)"
jwt_auto_generate_keys="$(get_env_key JWT_AUTO_GENERATE_KEYS)"
jwt_private_key="$(get_env_key JWT_PRIVATE_KEY)"
jwt_public_key="$(get_env_key JWT_PUBLIC_KEY)"

if [[ "${jwt_algorithm}" == "RS256" || "${jwt_algorithm}" == "ES256" ]]; then
  jwt_auto_generate_keys_lower="$(printf '%s' "${jwt_auto_generate_keys}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${jwt_auto_generate_keys_lower}" == "true" ]]; then
    if [[ -n "${jwt_private_key}" ]] && ! looks_like_pem_private_key "${jwt_private_key}"; then
      set_env_key "JWT_PRIVATE_KEY" ""
      randomized_keys+=("JWT_PRIVATE_KEY")
    fi
    if [[ -n "${jwt_public_key}" ]] && ! looks_like_pem_public_key "${jwt_public_key}"; then
      set_env_key "JWT_PUBLIC_KEY" ""
      randomized_keys+=("JWT_PUBLIC_KEY")
    fi
  fi
fi

old_default_otlp_token="$(get_env_key DEFAULT_OTLP_TOKEN)"
set_secret_if_insecure "DEFAULT_OTLP_TOKEN" "otlp_4fK9qL2mP8rS3tV6wX1yZ7" "otlp_$(random_hex 28)"
default_otlp_token="$(get_env_key DEFAULT_OTLP_TOKEN)"

default_org_id="$(get_env_key DEFAULT_ORG_ID)"
mimir_tenant_id="$(get_env_key MIMIR_TENANT_ID)"
if is_insecure_value "${mimir_tenant_id}" "observantio" || [[ -z "${mimir_tenant_id}" ]]; then
  set_env_key "MIMIR_TENANT_ID" "${default_org_id:-default}"
fi

otel_otlp_token="$(get_env_key OTEL_OTLP_TOKEN)"
if is_insecure_value "${otel_otlp_token}" "otel_5qW1mN7rT3xY9pK2vL6" || [[ "${otel_otlp_token}" == "${old_default_otlp_token}" ]]; then
  set_env_key "OTEL_OTLP_TOKEN" "${default_otlp_token}"
  randomized_keys+=("OTEL_OTLP_TOKEN")
fi

set_secret_if_insecure "INBOUND_WEBHOOK_TOKEN"          "whk_2nR8tV4pQ1xY6mK3zL7"           "whk_$(random_hex 28)"
set_secret_if_insecure "OTLP_INGEST_TOKEN"              "otlp_ingest_9xR3mT7qP2vN6kY1zL5"   "otlp_ingest_$(random_hex 28)"
set_secret_if_insecure "AGENT_HEARTBEAT_TOKEN"          "heartbeat_7mQ2rP9xT4vN1kY6zL3"     "heartbeat_$(random_hex 28)"
set_secret_if_insecure "GATEWAY_STATUS_OTLP_TOKEN"      "status_7vN2qP8mR4tX1yZ6kL3"        "status_$(random_hex 28)"
set_secret_if_insecure "GATEWAY_INTERNAL_SERVICE_TOKEN" "svc_gateway_8mQ3tP7rN2vW6xY1kL4"   "svc_gateway_$(random_hex 28)"
set_secret_if_insecure "DATA_ENCRYPTION_KEY"            "YXV0b19nZW5lcmF0ZV9pbl9pbnN0YWxsZXJfMzJfYnl0ZXM=" "$(random_fernet_key)"

notifier_service_token="$(get_env_key NOTIFIER_SERVICE_TOKEN)"
notifier_expected_service_token="$(get_env_key NOTIFIER_EXPECTED_SERVICE_TOKEN)"
if is_insecure_value "${notifier_service_token}" "svc_notifier_9kLm2pQ7rS4tV8xY1zC5" || is_insecure_value "${notifier_expected_service_token}" "svc_notifier_9kLm2pQ7rS4tV8xY1zC5"; then
  new_notifier_service_token="svc_notifier_$(random_hex 28)"
  set_env_key "NOTIFIER_SERVICE_TOKEN" "${new_notifier_service_token}"
  set_env_key "NOTIFIER_EXPECTED_SERVICE_TOKEN" "${new_notifier_service_token}"
  randomized_keys+=("NOTIFIER_SERVICE_TOKEN" "NOTIFIER_EXPECTED_SERVICE_TOKEN")
fi

notifier_ctx_signing="$(get_env_key NOTIFIER_CONTEXT_SIGNING_KEY)"
notifier_ctx_verify="$(get_env_key NOTIFIER_CONTEXT_VERIFY_KEY)"
if is_insecure_value "${notifier_ctx_signing}" "ctx_notifier_Z4pN8wR2yV6mQ1tX7kL9" || is_insecure_value "${notifier_ctx_verify}" "ctx_notifier_Z4pN8wR2yV6mQ1tX7kL9"; then
  new_notifier_ctx="ctx_notifier_$(random_hex 32)"
  set_env_key "NOTIFIER_CONTEXT_SIGNING_KEY" "${new_notifier_ctx}"
  set_env_key "NOTIFIER_CONTEXT_VERIFY_KEY" "${new_notifier_ctx}"
  randomized_keys+=("NOTIFIER_CONTEXT_SIGNING_KEY" "NOTIFIER_CONTEXT_VERIFY_KEY")
fi

resolver_service_token="$(get_env_key RESOLVER_SERVICE_TOKEN)"
resolver_expected_service_token="$(get_env_key RESOLVER_EXPECTED_SERVICE_TOKEN)"
if is_insecure_value "${resolver_service_token}" "svc_resolver_3xT7mQ2pL9rV4wY8kN1" || is_insecure_value "${resolver_expected_service_token}" "svc_resolver_3xT7mQ2pL9rV4wY8kN1"; then
  new_resolver_service_token="svc_resolver_$(random_hex 28)"
  set_env_key "RESOLVER_SERVICE_TOKEN" "${new_resolver_service_token}"
  set_env_key "RESOLVER_EXPECTED_SERVICE_TOKEN" "${new_resolver_service_token}"
  randomized_keys+=("RESOLVER_SERVICE_TOKEN" "RESOLVER_EXPECTED_SERVICE_TOKEN")
fi

resolver_ctx_signing="$(get_env_key RESOLVER_CONTEXT_SIGNING_KEY)"
resolver_ctx_verify="$(get_env_key RESOLVER_CONTEXT_VERIFY_KEY)"
if is_insecure_value "${resolver_ctx_signing}" "ctx_resolver_M2vR8tQ4yK7nP1wX6zL3" || is_insecure_value "${resolver_ctx_verify}" "ctx_resolver_M2vR8tQ4yK7nP1wX6zL3"; then
  new_resolver_ctx="ctx_resolver_$(random_hex 32)"
  set_env_key "RESOLVER_CONTEXT_SIGNING_KEY" "${new_resolver_ctx}"
  set_env_key "RESOLVER_CONTEXT_VERIFY_KEY" "${new_resolver_ctx}"
  randomized_keys+=("RESOLVER_CONTEXT_SIGNING_KEY" "RESOLVER_CONTEXT_VERIFY_KEY")
fi

grafana_password="$(get_env_key GRAFANA_PASSWORD)"
gf_security_admin_password="$(get_env_key GF_SECURITY_ADMIN_PASSWORD)"
if is_insecure_value "${grafana_password}" "GrafanaR4nD0m21" || is_insecure_value "${gf_security_admin_password}" "GrafanaR4nD0m21" \
  || [[ "${grafana_password}" == "Grafana!R4nD0m#21" ]] || [[ "${gf_security_admin_password}" == "Grafana!R4nD0m#21" ]]; then
  new_grafana_password="Grafana!$(random_hex 16)"
  set_env_key "GRAFANA_PASSWORD" "${new_grafana_password}"
  set_env_key "GF_SECURITY_ADMIN_PASSWORD" "${new_grafana_password}"
  randomized_keys+=("GRAFANA_PASSWORD" "GF_SECURITY_ADMIN_PASSWORD")
fi

grafana_username="$(get_env_key GRAFANA_USERNAME)"
if is_insecure_value "${grafana_username}" ""; then
  grafana_username="admin"
  set_env_key "GRAFANA_USERNAME" "${grafana_username}"
  randomized_keys+=("GRAFANA_USERNAME")
fi
set_env_key "GF_SECURITY_ADMIN_USER" "${grafana_username}"

app_env="$(get_env_key APP_ENV)"
if [[ -z "${app_env}" ]]; then
  app_env="$(get_env_key ENVIRONMENT)"
fi
app_env="$(printf '%s' "${app_env}" | tr '[:upper:]' '[:lower:]')"
is_production_env=false
if [[ "${app_env}" == "production" || "${app_env}" == "prod" ]]; then
  is_production_env=true
fi

auth_public_ip_allowlist="$(get_env_key AUTH_PUBLIC_IP_ALLOWLIST)"
if [[ "${is_production_env}" == "false" && -z "${auth_public_ip_allowlist}" ]]; then
  set_env_key "ALLOWLIST_FAIL_OPEN" "true"
fi

gateway_ip_allowlist="$(get_env_key GATEWAY_IP_ALLOWLIST)"
if [[ "${is_production_env}" == "false" && -z "${gateway_ip_allowlist}" ]]; then
  set_env_key "GATEWAY_ALLOWLIST_FAIL_OPEN" "true"
fi

grafana_proxy_ip_allowlist="$(get_env_key GRAFANA_PROXY_IP_ALLOWLIST)"
if [[ -z "${grafana_proxy_ip_allowlist}" ]]; then
  set_env_key "GRAFANA_PROXY_IP_ALLOWLIST" "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
fi

grafana_auth_proxy_whitelist="$(get_env_key GF_AUTH_PROXY_WHITELIST)"
if [[ -z "${grafana_auth_proxy_whitelist}" || "${grafana_auth_proxy_whitelist}" == "127.0.0.1,::1" ]]; then
  set_env_key "GF_AUTH_PROXY_WHITELIST" "127.0.0.1,::1,172.16.0.0/12"
fi

default_admin_username="$(get_env_key DEFAULT_ADMIN_USERNAME)"
default_admin_password="$(get_env_key DEFAULT_ADMIN_PASSWORD)"
default_admin_email="$(get_env_key DEFAULT_ADMIN_EMAIL)"
default_cors_origins="$(get_env_key CORS_ORIGINS)"

if is_insecure_value "${default_admin_password}" "Obsrv!AdminR4nD0m"; then
  default_admin_password=""
fi

default_ui_host="localhost"
if [[ -n "${default_cors_origins}" ]]; then
  first_origin="${default_cors_origins%%,*}"
  first_origin="${first_origin#http://}"
  first_origin="${first_origin#https://}"
  first_origin="${first_origin%%/*}"
  first_origin="${first_origin%%:*}"
  if [[ -n "${first_origin}" ]]; then
    default_ui_host="${first_origin}"
  fi
fi

if [[ ! -t 0 ]]; then
  err "This installer is interactive and must be run from a terminal session."
  exit 1
fi

banner

read -r -p "$(colorize "${C_BOLD}" "What is the UI host IP or DNS (CORS + access host) [${default_ui_host}]: ")" input_ui_host
ui_host="${input_ui_host:-${default_ui_host}}"
ui_origin="http://${ui_host}:5173"
api_base_url="http://${ui_host}:4319"
otlp_gateway_url="http://${ui_host}:4320"
grafana_root_url="http://${ui_host}:8080/grafana/"
app_login_url="${ui_origin}/login"

read -r -p "$(colorize "${C_BOLD}" "Admin username [${default_admin_username:-admin}]: ")" input_admin_username
read -r -p "$(colorize "${C_BOLD}" "Admin email (valid email for future SSO use) [${default_admin_email:-admin@observantio.local}]: ")" input_admin_email

if [[ -n "${default_admin_password}" ]]; then
  read -r -s -p "$(colorize "${C_BOLD}" "Admin password (min 16 chars) [hidden, Enter keeps default]: ")" input_admin_password
else
  read -r -s -p "$(colorize "${C_BOLD}" "Admin password (min 16 chars) [required]: ")" input_admin_password
fi
echo

admin_username="${input_admin_username:-${default_admin_username:-admin}}"
admin_email="${input_admin_email:-${default_admin_email:-admin@observantio.local}}"

if [[ -n "${default_admin_password}" ]]; then
  admin_password="${input_admin_password:-${default_admin_password}}"
else
  admin_password="${input_admin_password:-}"
fi

if [[ -z "${admin_password}" ]]; then
  err "Admin password is required."
  exit 1
fi

if [[ ${#admin_password} -lt 16 ]]; then
  err "Admin password must be at least 16 characters long."
  exit 1
fi

set_env_key "DEFAULT_ADMIN_USERNAME" "$admin_username"
set_env_key "DEFAULT_ADMIN_PASSWORD" "$admin_password"
set_env_key "DEFAULT_ADMIN_EMAIL" "$admin_email"
set_env_key "CORS_ORIGINS" "${ui_origin}"
set_env_key "VITE_API_URL" "${api_base_url}"
set_env_key "GF_SERVER_ROOT_URL" "${grafana_root_url}"
set_env_key "APP_LOGIN_URL" "${app_login_url}"

echo " "
section "Configured UI host settings"
printf '  %s %s\n' "$(colorize "$C_CYAN" "CORS_ORIGINS:")" "$(colorize "$C_CYAN" "${ui_origin}")"
printf '  %s %s\n' "$(colorize "$C_CYAN" "GF_SERVER_ROOT_URL:")" "$(colorize "$C_CYAN" "${grafana_root_url}")"
printf '  %s %s\n' "$(colorize "$C_CYAN" "APP_LOGIN_URL:")" "$(colorize "$C_CYAN" "${app_login_url}")"

if [[ "${#randomized_keys[@]}" -gt 0 ]]; then
  echo " "
  section "Randomized secure defaults for"
  printf '%s\n' "${randomized_keys[@]}" | awk '!seen[$0]++ { print "  - " $0 }'
fi

if [[ "${#bundle_version_keys[@]}" -gt 0 ]]; then
  echo " "
  section "Normalized bundle image tags for"
  printf '%s\n' "${bundle_version_keys[@]}" | awk '!seen[$0]++ { print "  - " $0 }'
fi

release_arch="$(get_env_key RELEASE_ARCH)"
if [[ -n "${release_arch}" && "${release_arch}" != "multi" ]]; then
  host_arch="$(uname -m)"
  host_arch="${host_arch/x86_64/amd64}"
  host_arch="${host_arch/aarch64/arm64}"
  if [[ "${host_arch}" != "${release_arch}" ]]; then
    warn "Bundle architecture is ${release_arch} but host appears to be ${host_arch}."
  fi
fi

echo ""
info "Running optimal config generator"
"${RUN_OPTIMAL_SCRIPT}"
echo ""
info "Pulling images for OBSERVANTIO_BUNDLE_VERSION=$(get_env_key OBSERVANTIO_BUNDLE_VERSION)..."
"${COMPOSE_CMD[@]}" -f docker-compose.prod.yml pull
echo ""
read -r -p "$(colorize "${C_BOLD}" "Start services now? [Y/n]: ")" start_now
echo " "
if [[ -z "${start_now}" || "${start_now}" =~ ^[Yy]$ ]]; then
  ok "Starting services now"
  if ! preflight_host_ports; then
    exit 1
  fi
  "${COMPOSE_CMD[@]}" -f docker-compose.prod.yml up -d
  echo " "
  section "You are all set"
  echo "  Next: harden the .env using the documentation and keep the backup copy nearby."
  echo "  Guide: https://github.com/observantio/watchdog/blob/main/USER%20GUIDE.md"
  echo "  Project: https://github.com/observantio/watchdog"
  printf '  %s %s (Username: %s)\n' "$(colorize "$C_GREEN" "UI:")" "$(colorize "$C_GREEN" "${ui_origin}")" "${admin_username}"
  echo " "
  if command -v curl >/dev/null 2>&1; then
    if ! curl -sf "http://localhost:4319/health" >/dev/null; then
      warn "Health probe failed at http://localhost:4319/health"
      warn "Check status: ${COMPOSE_CMD[*]} -f docker-compose.prod.yml ps"
      warn "Inspect logs: ${COMPOSE_CMD[*]} -f docker-compose.prod.yml logs watchdog"
    fi
  elif command -v wget >/dev/null 2>&1; then
    if ! wget -qO- "http://localhost:4319/health" >/dev/null; then
      warn "Health probe failed at http://localhost:4319/health"
      warn "Check status: ${COMPOSE_CMD[*]} -f docker-compose.prod.yml ps"
      warn "Inspect logs: ${COMPOSE_CMD[*]} -f docker-compose.prod.yml logs watchdog"
    fi
  fi
else
  warn "Skipped start. Run: ${COMPOSE_CMD[*]} -f docker-compose.prod.yml up -d"
fi

INSTALL_COMPLETE="1"

echo ""
section "You're all set"
printf '  %s %s\n' "$(colorize "$C_CYAN" "UI:")" "$(colorize "$C_CYAN" "${ui_origin}")"
printf '  %s %s\n' "$(colorize "$C_CYAN" "API:")" "$(colorize "$C_CYAN" "${api_base_url}")"
printf '  %s %s\n' "$(colorize "$C_CYAN" "Grafana:")" "$(colorize "$C_CYAN" "${grafana_root_url}")"
printf '  %s %s\n' "$(colorize "$C_CYAN" "Login URL:")" "$(colorize "$C_CYAN" "${app_login_url}")"
if [[ -n "${ENV_BACKUP}" && -f "${ENV_BACKUP}" ]]; then
  printf '  %s %s\n' "$(colorize "$C_YELLOW" "Backup:")" "$(colorize "$C_YELLOW" "${ENV_BACKUP}")"
fi
echo "  Re-run this installer later to refresh generated defaults while keeping your backup."
echo ""
