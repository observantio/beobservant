#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "docker compose (plugin) or docker-compose is required." >&2
  exit 1
fi

if [[ ! -f ".env" ]]; then
  cp .env.example .env
fi

set_env_key() {
  local key="$1"
  local value="$2"
  local tmp_file
  tmp_file="$(mktemp)"
  awk -F= -v k="$key" -v v="$value" '
    BEGIN { replaced=0 }
    $1 == k { print k "=" v; replaced=1; next }
    { print $0 }
    END { if (!replaced) print k "=" v }
  ' .env > "$tmp_file"
  mv "$tmp_file" .env
}

get_env_key() {
  local key="$1"
  awk -F= -v k="$key" '$1 == k { print substr($0, index($0, "=") + 1); exit }' .env
}

default_admin_username="$(get_env_key DEFAULT_ADMIN_USERNAME)"
default_admin_password="$(get_env_key DEFAULT_ADMIN_PASSWORD)"
default_admin_email="$(get_env_key DEFAULT_ADMIN_EMAIL)"

read -r -p "Admin username [${default_admin_username:-admin}]: " input_admin_username
read -r -s -p "Admin password [hidden, press Enter to keep default]: " input_admin_password
echo
read -r -p "Admin email [${default_admin_email:-admin@observantio.local}]: " input_admin_email

admin_username="${input_admin_username:-${default_admin_username:-admin}}"
admin_password="${input_admin_password:-${default_admin_password:-Obsrv!Admin#R4nD0m}}"
admin_email="${input_admin_email:-${default_admin_email:-admin@observantio.local}}"

set_env_key "DEFAULT_ADMIN_USERNAME" "$admin_username"
set_env_key "DEFAULT_ADMIN_PASSWORD" "$admin_password"
set_env_key "DEFAULT_ADMIN_EMAIL" "$admin_email"

release_arch="$(get_env_key RELEASE_ARCH)"
if [[ -n "${release_arch}" && "${release_arch}" != "multi" ]]; then
  host_arch="$(uname -m)"
  host_arch="${host_arch/x86_64/amd64}"
  host_arch="${host_arch/aarch64/arm64}"
  if [[ "${host_arch}" != "${release_arch}" ]]; then
    echo "Warning: bundle architecture is ${release_arch} but host appears to be ${host_arch}." >&2
  fi
fi

echo "Pulling images for OBSERVANTIO_BUNDLE_VERSION=$(get_env_key OBSERVANTIO_BUNDLE_VERSION)..."
"${COMPOSE_CMD[@]}" -f docker-compose.prod.yml pull

read -r -p "Start services now? [Y/n]: " start_now
if [[ -z "${start_now}" || "${start_now}" =~ ^[Yy]$ ]]; then
  "${COMPOSE_CMD[@]}" -f docker-compose.prod.yml up -d
  echo "Observantio is up."
else
  echo "Skipped start. Run: ${COMPOSE_CMD[*]} -f docker-compose.prod.yml up -d"
fi
