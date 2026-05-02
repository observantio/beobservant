#!/usr/bin/env bash

# Observantio Release Uninstall Script
# Stops and removes the Observantio production stack from a release bundle.
# All Rights Reserved. (c) 2026 Stefan Kumarasinghe

set -euo pipefail

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

section() {
  printf '\n%s\n' "$(colorize "${C_BOLD}${C_MAGENTA}" "$*")"
  printf '%s\n' "$(colorize "${C_DIM}" "------------------------------------------------------------")"
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

usage() {
  cat <<USAGE
$(colorize "${C_MAGENTA}${C_BOLD}" "Observantio Release Uninstall")

$(colorize "${C_CYAN}${C_BOLD}" "Usage:")
  ./release/uninstall.sh [--purge] [--yes] [--help]

$(colorize "${C_CYAN}${C_BOLD}" "Options:")
  --purge   Remove named volumes in addition to containers and networks.
  --yes     Skip confirmation prompt for --purge.
  --help    Show this help message.
USAGE
}

PURGE_VOLUMES=false
AUTO_YES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge)
      PURGE_VOLUMES=true
      ;;
    --yes)
      AUTO_YES=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown option: $1"
      usage >&2
      exit 1
      ;;
  esac
  shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/docker-compose.prod.yml" ]]; then
  ROOT_DIR="${SCRIPT_DIR}"
elif [[ -f "${SCRIPT_DIR}/../docker-compose.prod.yml" ]]; then
  ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
  err "docker-compose.prod.yml not found next to this script or in its parent directory."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  err "Docker is required but not installed."
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  err "Docker Compose (plugin) or docker-compose is required."
  exit 1
fi

cd "${ROOT_DIR}"

section "Observantio Uninstall"
info "Using compose command: ${COMPOSE_CMD[*]}"
info "Project root: ${ROOT_DIR}"

if [[ "$PURGE_VOLUMES" == true ]]; then
  warn "--purge will permanently remove named volumes and persisted data."
  if [[ "$AUTO_YES" != true ]]; then
    read -r -p "Type 'purge' to continue: " confirm
    if [[ "$confirm" != "purge" ]]; then
      warn "Uninstall cancelled. No changes were made."
      exit 0
    fi
  fi

  info "Stopping stack and removing containers, networks, and volumes..."
  "${COMPOSE_CMD[@]}" -f docker-compose.prod.yml down --volumes --remove-orphans
  ok "Observantio production stack uninstalled with volumes removed."
else
  info "Stopping stack and removing containers/networks..."
  "${COMPOSE_CMD[@]}" -f docker-compose.prod.yml down --remove-orphans
  ok "Observantio production stack uninstalled."
  info "Tip: rerun with --purge to also remove named volumes."
fi
