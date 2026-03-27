#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_MYPY="${ROOT_DIR}/.venv/bin/mypy"

if [[ ! -x "${VENV_MYPY}" ]]; then
  echo "error: ${VENV_MYPY} not found or not executable. Create the virtualenv first." >&2
  exit 1
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
    "${VENV_MYPY}" --cache-dir "${cache_dir}" --config-file "${config_file}" .
  )
}

run_suite "resolver" "../pyproject.toml"
run_suite "gatekeeper" "../pyproject.toml"
run_suite "notifier" "../pyproject.toml"
run_suite "watchdog" "../pyproject.toml"

echo
echo "All service mypy checks completed."
