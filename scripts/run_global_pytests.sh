#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTEST="${ROOT_DIR}/.venv/bin/pytest"
VENV_COVERAGE="${ROOT_DIR}/.venv/bin/coverage"
REPORT_DIR="${ROOT_DIR}/test-reports"
COVERAGE_DIR="${REPORT_DIR}/coverage"
JUNIT_DIR="${REPORT_DIR}/junit"
COVERAGE_THRESHOLD="${COVERAGE_THRESHOLD:-0}"

SERVICES=(
  resolver
  gatekeeper
  notifier
  watchdog
)

if [[ ! -x "${VENV_PYTEST}" ]]; then
  echo "error: ${VENV_PYTEST} not found or not executable. Create the virtualenv first." >&2
  exit 1
fi

if [[ ! -x "${VENV_COVERAGE}" ]]; then
  echo "error: ${VENV_COVERAGE} not found or not executable." >&2
  exit 1
fi

if ! help_output="$("${VENV_PYTEST}" --help)"; then
  echo "error: failed to run ${VENV_PYTEST} --help" >&2
  exit 1
fi

if [[ "${help_output}" != *"--cov"* ]]; then
  echo "error: pytest-cov is not installed in ${ROOT_DIR}/.venv" >&2
  echo "install it with: ${ROOT_DIR}/.venv/bin/pip install pytest-cov" >&2
  exit 1
fi

mkdir -p "${COVERAGE_DIR}" "${JUNIT_DIR}"

run_suite() {
  local service_dir="$1"
  local cache_dir="/tmp/watchdog_pytest_cache/${service_dir}"
  local junit_file="${JUNIT_DIR}/${service_dir}.xml"
  local cov_file="${COVERAGE_DIR}/.coverage.${service_dir}"

  mkdir -p "${cache_dir}"

  echo
  echo "==> Running pytest in ${service_dir}"

  (
    cd "${ROOT_DIR}/${service_dir}"
    COVERAGE_FILE="${cov_file}" "${VENV_PYTEST}" \
      -o "cache_dir=${cache_dir}" \
      --junitxml="${junit_file}" \
      --cov=. \
      --cov-branch \
      --cov-report=term-missing:skip-covered \
      --cov-report=xml:"${COVERAGE_DIR}/${service_dir}-coverage.xml" \
      --cov-report=html:"${COVERAGE_DIR}/${service_dir}-html" \
      --cov-fail-under="${COVERAGE_THRESHOLD}" \
      -ra \
      --show-capture=no \
      --durations=10
  )
}

for service in "${SERVICES[@]}"; do
  run_suite "${service}"
done

echo
echo "==> Combining coverage reports"

(
  cd "${ROOT_DIR}"
  COVERAGE_FILE="${COVERAGE_DIR}/.coverage" "${VENV_COVERAGE}" combine "${COVERAGE_DIR}"/.coverage.*
  COVERAGE_FILE="${COVERAGE_DIR}/.coverage" "${VENV_COVERAGE}" report -m
  COVERAGE_FILE="${COVERAGE_DIR}/.coverage" "${VENV_COVERAGE}" xml -o "${COVERAGE_DIR}/coverage.xml"
  COVERAGE_FILE="${COVERAGE_DIR}/.coverage" "${VENV_COVERAGE}" html -d "${COVERAGE_DIR}/html"
)

echo
echo "All service pytest suites completed."
echo "JUnit reports:    ${JUNIT_DIR}"
echo "Coverage reports: ${COVERAGE_DIR}"
echo "Combined HTML:    ${COVERAGE_DIR}/html/index.html"