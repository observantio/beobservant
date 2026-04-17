#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_MYPY="${ROOT_DIR}/.venv/bin/mypy"

ALL_SERVICES=(resolver gatekeeper notifier watchdog)

usage() {
  cat <<EOF
Usage: $(basename "$0") [SERVICE]

Run mypy for backend services using the repo pyproject defaults.

  SERVICE   Optional. One of: ${ALL_SERVICES[*]}
            If omitted, all services are checked.

Examples:
  $(basename "$0")
  $(basename "$0") watchdog
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi

if [[ ! -x "${VENV_MYPY}" ]]; then
  echo "error: ${VENV_MYPY} not found or not executable. Create the virtualenv first." >&2
  exit 1
fi

services_to_run=("${ALL_SERVICES[@]}")
if [[ $# -eq 1 ]]; then
  want="$1"
  ok=0
  for s in "${ALL_SERVICES[@]}"; do
    if [[ "$s" == "$want" ]]; then
      ok=1
      break
    fi
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "error: unknown service '${want}'. Expected one of: ${ALL_SERVICES[*]}" >&2
    usage >&2
    exit 2
  fi
  services_to_run=("$want")
fi

run_suite() {
  local service_dir="$1"
  local config_file="$2"
  local cache_dir="/tmp/watchdog_mypy_cache/${service_dir}"
  mkdir -p "${cache_dir}"

  echo
  echo "==> Running mypy in ${service_dir}"
  (
    cd "${ROOT_DIR}/${service_dir}"
    # Running per-service can make shared override sections appear "unused".
    "${VENV_MYPY}" --cache-dir "${cache_dir}" --config-file "${config_file}" --no-warn-unused-configs .
  )
}

for svc in "${services_to_run[@]}"; do
  run_suite "${svc}" "../pyproject.toml"
done

echo
if [[ ${#services_to_run[@]} -eq 4 ]]; then
  echo "All service mypy checks completed."
else
  echo "mypy checks completed for: ${services_to_run[*]}"
fi
