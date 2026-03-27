#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYLINT="${ROOT_DIR}/.venv/bin/pylint"

if [[ ! -x "${VENV_PYLINT}" ]]; then
  echo "error: ${VENV_PYLINT} not found or not executable. Create the virtualenv first." >&2
  exit 1
fi

echo
(
  cd "${ROOT_DIR}/resolver"
  "${VENV_PYLINT}" --rcfile pyproject.toml .
)

echo
(
  cd "${ROOT_DIR}"
  "${VENV_PYLINT}" --rcfile pyproject.toml gatekeeper
)

echo
(
  cd "${ROOT_DIR}/notifier"
  "${VENV_PYLINT}" --rcfile pyproject.toml .
)

echo
(
  cd "${ROOT_DIR}"
  "${VENV_PYLINT}" --rcfile pyproject.toml watchdog
)

echo
echo "All service pylint checks completed."
