#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYLINT="${ROOT_DIR}/.venv/bin/pylint"

ALL_SERVICES=(resolver gatekeeper notifier watchdog)

usage() {
  cat <<EOF
Usage: $(basename "$0") [SERVICE]

Run pylint for backend services with shared pyproject config.

  SERVICE   Optional. One of: ${ALL_SERVICES[*]}
            If omitted, all services are checked.

Examples:
  $(basename "$0")
  $(basename "$0") gatekeeper
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

if [[ ! -x "${VENV_PYLINT}" ]]; then
  echo "error: ${VENV_PYLINT} not found or not executable. Create the virtualenv first." >&2
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

fail=0
run_pkg() {
  local name="$1"
  shift
  echo
  echo "== pylint: ${name} =="
  if ! "$@"; then
    fail=1
  fi
}

run_pylint_for() {
  local name="$1"
  case "$name" in
    resolver)
      run_pkg "resolver" bash -c "cd \"${ROOT_DIR}/resolver\" && \"${VENV_PYLINT}\" --rcfile pyproject.toml ."
      ;;
    gatekeeper)
      run_pkg "gatekeeper" bash -c "cd \"${ROOT_DIR}\" && PYLINT_PATH_FIRST=gatekeeper \"${VENV_PYLINT}\" --rcfile pyproject.toml gatekeeper"
      ;;
    notifier)
      run_pkg "notifier" bash -c "cd \"${ROOT_DIR}/notifier\" && \"${VENV_PYLINT}\" --rcfile pyproject.toml ."
      ;;
    watchdog)
      run_pkg "watchdog" bash -c "cd \"${ROOT_DIR}\" && PYLINT_PATH_FIRST=watchdog \"${VENV_PYLINT}\" --rcfile pyproject.toml watchdog"
      ;;
    *)
      echo "error: internal: unknown service ${name}" >&2
      exit 3
      ;;
  esac
}

for svc in "${services_to_run[@]}"; do
  run_pylint_for "$svc"
done

echo
if [[ "${fail}" -ne 0 ]]; then
  echo "One or more pylint runs reported issues." >&2
  exit 1
fi
if [[ ${#services_to_run[@]} -eq 4 ]]; then
  echo "All service pylint checks completed."
else
  echo "pylint checks completed for: ${services_to_run[*]}"
fi
