#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTEST="${ROOT_DIR}/.venv/bin/pytest"
VENV_COVERAGE="${ROOT_DIR}/.venv/bin/coverage"
REPORT_DIR="${ROOT_DIR}/test-reports"
COVERAGE_DIR="${REPORT_DIR}/coverage"
JUNIT_DIR="${REPORT_DIR}/junit"
COVERAGE_THRESHOLD="${COVERAGE_THRESHOLD:-100}"

ALL_SERVICES=(resolver gatekeeper notifier watchdog)

usage() {
  cat <<EOF
Usage: $(basename "$0") [SERVICE]

Run pytest with coverage and JUnit output per service.

  SERVICE   Optional. One of: ${ALL_SERVICES[*]}
            If omitted, all services are run and coverage is combined.

Environment:
  COVERAGE_THRESHOLD   Fail under threshold (default: 100)

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
    PYTHONWARNINGS="${PYTHONWARNINGS:-ignore::ResourceWarning}" \
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
      --durations=10 \
      tests
  )
}

for service in "${services_to_run[@]}"; do
  run_suite "${service}"
done

echo
echo "==> Combining coverage reports"

(
  cd "${ROOT_DIR}"
  combine_paths=()
  for service in "${services_to_run[@]}"; do
    f="${COVERAGE_DIR}/.coverage.${service}"
    if [[ -f "${f}" ]]; then
      combine_paths+=("${f}")
    fi
  done
  if [[ ${#combine_paths[@]} -eq 0 ]]; then
    echo "error: no per-service coverage data for: ${services_to_run[*]}" >&2
    exit 1
  fi
  COVERAGE_FILE="${COVERAGE_DIR}/.coverage" "${VENV_COVERAGE}" combine "${combine_paths[@]}"
  COVERAGE_FILE="${COVERAGE_DIR}/.coverage" "${VENV_COVERAGE}" report -m
  COVERAGE_FILE="${COVERAGE_DIR}/.coverage" "${VENV_COVERAGE}" xml -o "${COVERAGE_DIR}/coverage.xml"
  COVERAGE_FILE="${COVERAGE_DIR}/.coverage" "${VENV_COVERAGE}" html -d "${COVERAGE_DIR}/html"
)

echo
if [[ ${#services_to_run[@]} -eq 4 ]]; then
  echo "All service pytest suites completed."
else
  echo "pytest suites completed for: ${services_to_run[*]}"
fi
echo "JUnit reports:    ${JUNIT_DIR}"
echo "Coverage reports: ${COVERAGE_DIR}"
echo "Combined HTML:    ${COVERAGE_DIR}/html/index.html"
