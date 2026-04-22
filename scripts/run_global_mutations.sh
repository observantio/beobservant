#!/usr/bin/env bash

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_MUTMUT="${ROOT_DIR}/.venv/bin/mutmut"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
ROOT_PYPROJECT="${ROOT_DIR}/pyproject.toml"

ALL_SERVICES=(resolver gatekeeper notifier watchdog)
MAX_CHILDREN="${MUTMUT_MAX_CHILDREN:-4}"
CONTINUE_ON_ERROR=1
STRICT_MODE=1
OUTPUT_DIR="${ROOT_DIR}/test-reports/mutations"

# Known equivalent survivors that are semantically identical in runtime behavior.
KNOWN_EQUIVALENT_MUTANTS=(
  "gatekeeper:routers.gateway_router.x__validate_otlp_token_request__mutmut_6"
  "gatekeeper:routers.gateway_router.x__validate_otlp_token_request__mutmut_54"
  "gatekeeper:routers.gateway_router.x__validate_otlp_token_request__mutmut_61"
  "gatekeeper:routers.gateway_router.x__validate_otlp_token_request__mutmut_62"
  "resolver:api.routes.exception.x_handle_exceptions__mutmut_3"
  "resolver:api.routes.exception.x_handle_exceptions__mutmut_7"
  "resolver:api.routes.exception.x_handle_exceptions__mutmut_12"
  "resolver:api.routes.exception.x_handle_exceptions__mutmut_16"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_2"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_7"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_10"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_13"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_17"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_18"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_25"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_26"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_27"
  "notifier:services.common.url_utils.x_is_safe_http_url__mutmut_32"
)

usage() {
  cat <<EOF
Usage: $(basename "$0") [SERVICE] [OPTIONS]

Run mutmut for backend services and generate a consolidated mutation report.

  SERVICE                     Optional. One of: ${ALL_SERVICES[*]}

Options:
  --max-children N            Number of mutmut workers (default: ${MAX_CHILDREN})
  --output-dir PATH           Report directory root (default: ${OUTPUT_DIR})
  --no-continue-on-error      Stop immediately on first service failure
  --continue-on-error         Continue and summarize all services (default)
  --strict                    Exit non-zero when unexpected survivors/failures exist (default)
  --no-strict                 Always exit zero after report generation
  -h, --help                  Show this help

Environment:
  MUTMUT_MAX_CHILDREN         Default for --max-children

Examples:
  $(basename "$0")
  $(basename "$0") watchdog
  $(basename "$0") --max-children 8 --no-continue-on-error
EOF
}

if [[ ! -x "${VENV_MUTMUT}" ]]; then
  echo "error: ${VENV_MUTMUT} not found or not executable. Create the virtualenv first." >&2
  exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "error: ${VENV_PYTHON} not found or not executable. Create the virtualenv first." >&2
  exit 1
fi

if [[ ! -f "${ROOT_PYPROJECT}" ]]; then
  echo "error: ${ROOT_PYPROJECT} not found." >&2
  exit 1
fi

services_to_run=()

is_service() {
  local candidate="$1"
  local service
  for service in "${ALL_SERVICES[@]}"; do
    if [[ "${candidate}" == "${service}" ]]; then
      return 0
    fi
  done
  return 1
}

restore_temp_setup_cfgs() {
  :
}

trap restore_temp_setup_cfgs EXIT

render_service_pyproject() {
  local service="$1"
  local pyproject_path="$2"

  "${VENV_PYTHON}" - "${ROOT_PYPROJECT}" "${service}" "${pyproject_path}" <<'PY'
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
  import tomllib
else:
  import tomli as tomllib

root_pyproject, service_name, output_path = sys.argv[1:]
data = tomllib.loads(Path(root_pyproject).read_text(encoding="utf-8"))
profiles = data.get("tool", {}).get("observantio", {}).get("mutmut_profiles", {})
defaults = profiles.get("defaults", {})
service_profile = profiles.get(service_name)
if not isinstance(service_profile, dict):
  raise SystemExit(
    f"missing [tool.observantio.mutmut_profiles.{service_name}] in {root_pyproject}"
  )

merged: dict[str, object] = {}
if isinstance(defaults, dict):
  merged.update(defaults)
merged.update(service_profile)

list_keys = [
  "paths_to_mutate",
  "tests_dir",
  "also_copy",
  "pytest_add_cli_args_test_selection",
  "pytest_add_cli_args",
  "do_not_mutate",
  "type_check_command",
]
scalar_keys = [
  "mutate_only_covered_lines",
  "debug",
  "max_stack_depth",
]
ordered_keys = list_keys + scalar_keys


def toml_quote(value: object) -> str:
  escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
  return f'"{escaped}"'


def render_scalar(value: object) -> str:
  if isinstance(value, bool):
    return "true" if value else "false"
  if isinstance(value, (int, float)):
    return str(value)
  return toml_quote(value)


lines = ["[tool.mutmut]"]
for key in ordered_keys:
  if key not in merged:
    continue
  value = merged[key]
  if key in list_keys:
    if not isinstance(value, list) or len(value) == 0:
      continue
    lines.append(f"{key} = [")
    for item in value:
      lines.append(f"  {toml_quote(item)},")
    lines.append("]")
  else:
    lines.append(f"{key} = {render_scalar(value)}")

Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --max-children)
      if [[ $# -lt 2 ]]; then
        echo "error: --max-children requires a value" >&2
        exit 2
      fi
      MAX_CHILDREN="$2"
      shift 2
      ;;
    --output-dir)
      if [[ $# -lt 2 ]]; then
        echo "error: --output-dir requires a value" >&2
        exit 2
      fi
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --no-continue-on-error)
      CONTINUE_ON_ERROR=0
      shift
      ;;
    --continue-on-error)
      CONTINUE_ON_ERROR=1
      shift
      ;;
    --strict)
      STRICT_MODE=1
      shift
      ;;
    --no-strict)
      STRICT_MODE=0
      shift
      ;;
    -* )
      echo "error: unknown option $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if is_service "$1"; then
        if [[ ${#services_to_run[@]} -gt 0 ]]; then
          echo "error: only one SERVICE can be provided" >&2
          usage >&2
          exit 2
        fi
        services_to_run=("$1")
        shift
      else
        echo "error: unknown service '$1'. Expected one of: ${ALL_SERVICES[*]}" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

if [[ ${#services_to_run[@]} -eq 0 ]]; then
  services_to_run=("${ALL_SERVICES[@]}")
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="${OUTPUT_DIR}/${timestamp}"
LATEST_DIR="${OUTPUT_DIR}/latest"
mkdir -p "${RUN_DIR}"

is_known_equivalent_mutant() {
  local key="$1:$2"
  local known
  for known in "${KNOWN_EQUIVALENT_MUTANTS[@]}"; do
    if [[ "${known}" == "${key}" ]]; then
      return 0
    fi
  done
  return 1
}

declare -a summary_rows=()
declare -a unexpected_survivors=()
total_mutants=0
total_killed=0
total_survived=0
total_equivalent=0
service_failures=0
services_no_coverage=0

echo "Mutation run directory: ${RUN_DIR}"
echo "Services: ${services_to_run[*]}"
echo "max-children: ${MAX_CHILDREN}"

for service in "${services_to_run[@]}"; do
  service_dir="${ROOT_DIR}/${service}"
  service_pyproject="${service_dir}/pyproject.toml"
  run_log="${RUN_DIR}/${service}.mutmut-run.log"
  results_file="${RUN_DIR}/${service}.mutmut-results.txt"
  export_log="${RUN_DIR}/${service}.mutmut-export.log"
  stats_file="${RUN_DIR}/${service}.mutmut-cicd-stats.json"
  created_temp_pyproject=0

  echo
  echo "==> ${service}: mutmut run"
  rm -rf "${service_dir}/mutants"
  rm -rf "${service_dir}/.mutmut-cache"

  if [[ ! -f "${service_pyproject}" ]]; then
    if ! render_service_pyproject "${service}" "${service_pyproject}"; then
      echo "  status=error total=0 killed=0 survived=0 equivalent=0 unexpected=0"
      summary_rows+=("${service}|error|0|0|0|0|0|1")
      ((service_failures += 1))
      if [[ ${CONTINUE_ON_ERROR} -eq 0 ]]; then
        echo "Stopping early due to --no-continue-on-error"
        break
      fi
      continue
    fi
    created_temp_pyproject=1
  fi

  run_rc=0
  (
    cd "${service_dir}" || exit 1
    MUTANT_UNDER_TEST="" "${VENV_MUTMUT}" run --max-children "${MAX_CHILDREN}"
  ) >"${run_log}" 2>&1 || run_rc=$?

  results_rc=0
  (
    cd "${service_dir}" || exit 1
    "${VENV_MUTMUT}" results
  ) >"${results_file}" 2>&1 || results_rc=$?

  export_rc=0
  (
    cd "${service_dir}" || exit 1
    "${VENV_MUTMUT}" export-cicd-stats
  ) >"${export_log}" 2>&1 || export_rc=$?

  if [[ ${created_temp_pyproject} -eq 1 ]]; then
    rm -f "${service_pyproject}"
  fi

  if [[ -f "${service_dir}/mutants/mutmut-cicd-stats.json" ]]; then
    cp "${service_dir}/mutants/mutmut-cicd-stats.json" "${stats_file}"
  fi

  service_total=0
  service_killed=0
  service_survived=0

  if [[ -f "${stats_file}" ]]; then
    read -r service_total service_killed service_survived < <(
      "${VENV_PYTHON}" - "${stats_file}" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
print(data.get("total", 0), data.get("killed", 0), data.get("survived", 0))
PY
    )
  fi

  service_equivalent=0
  service_unexpected=0
  no_coverage_for_mutants=0

  if [[ ${run_rc} -ne 0 && -f "${run_log}" ]]; then
    if grep -q "could not find any test case for any mutant" "${run_log}"; then
      no_coverage_for_mutants=1
    fi
  fi

  if [[ -f "${results_file}" ]]; then
    while IFS= read -r line; do
      mutant="$(echo "${line}" | sed -E 's/^[[:space:]]*([^:]+):[[:space:]]+survived[[:space:]]*$/\1/')"
      if [[ -z "${mutant}" || "${mutant}" == "${line}" ]]; then
        continue
      fi
      if is_known_equivalent_mutant "${service}" "${mutant}"; then
        ((service_equivalent += 1))
      else
        ((service_unexpected += 1))
        unexpected_survivors+=("${service}:${mutant}")
      fi
    done < <(grep -E ':[[:space:]]+survived[[:space:]]*$' "${results_file}" || true)
  fi

  status="ok"
  if [[ ${no_coverage_for_mutants} -eq 1 ]]; then
    status="no-coverage"
    ((services_no_coverage += 1))
  elif [[ ${run_rc} -ne 0 || ${results_rc} -ne 0 || ${export_rc} -ne 0 ]]; then
    status="error"
    ((service_failures += 1))
  elif [[ ${service_unexpected} -gt 0 ]]; then
    status="survivors"
  fi

  ((total_mutants += service_total))
  ((total_killed += service_killed))
  ((total_survived += service_survived))
  ((total_equivalent += service_equivalent))

  summary_rows+=("${service}|${status}|${service_total}|${service_killed}|${service_survived}|${service_equivalent}|${service_unexpected}|${run_rc}")

  printf '  status=%s total=%s killed=%s survived=%s equivalent=%s unexpected=%s\n' \
    "${status}" "${service_total}" "${service_killed}" "${service_survived}" "${service_equivalent}" "${service_unexpected}"

  if [[ ${status} == "error" && ${CONTINUE_ON_ERROR} -eq 0 ]]; then
    echo "Stopping early due to --no-continue-on-error"
    break
  fi
done

summary_file="${RUN_DIR}/summary.md"

{
  echo "# Global Mutation Summary"
  echo
  echo "Run timestamp: ${timestamp}"
  echo
  echo "| Service | Status | Total | Killed | Survived | Known Equivalent | Unexpected Survived | mutmut run rc |"
  echo "|---|---:|---:|---:|---:|---:|---:|---:|"
  for row in "${summary_rows[@]}"; do
    IFS='|' read -r service status total killed survived equivalent unexpected run_rc <<<"${row}"
    echo "| ${service} | ${status} | ${total} | ${killed} | ${survived} | ${equivalent} | ${unexpected} | ${run_rc} |"
  done
  echo

  effective_survived=$((total_survived - total_equivalent))
  if (( total_mutants > 0 )); then
    effective_score="$(${VENV_PYTHON} - <<PY
total = ${total_mutants}
equiv = ${total_equivalent}
surv = ${total_survived}
effective_surv = max(0, surv - equiv)
print(f"{((total - effective_surv) / total) * 100:.2f}")
PY
)"
  else
    effective_score="0.00"
  fi

  echo "## Totals"
  echo
  echo "- Total mutants: ${total_mutants}"
  echo "- Killed: ${total_killed}"
  echo "- Reported survived: ${total_survived}"
  echo "- Known equivalent survived: ${total_equivalent}"
  echo "- Effective unexpected survived: ${effective_survived}"
  echo "- Effective mutation score: ${effective_score}%"
  echo "- Service execution failures: ${service_failures}"
  echo "- Services with no mutant coverage: ${services_no_coverage}"
  echo

  if [[ ${#unexpected_survivors[@]} -gt 0 ]]; then
    echo "## Unexpected Survivors"
    echo
    for item in "${unexpected_survivors[@]}"; do
      echo "- ${item}"
    done
    echo
  fi

  echo "## Artifacts"
  echo
  echo "- Run directory: ${RUN_DIR}"
  echo "- Latest symlink: ${LATEST_DIR}"
} >"${summary_file}"

ln -sfn "${RUN_DIR}" "${LATEST_DIR}"

cat "${summary_file}"

effective_unexpected_survivors=$((total_survived - total_equivalent))
if (( effective_unexpected_survivors < 0 )); then
  effective_unexpected_survivors=0
fi

if [[ ${STRICT_MODE} -eq 1 ]]; then
  if (( service_failures > 0 || services_no_coverage > 0 || effective_unexpected_survivors > 0 )); then
    exit 1
  fi
fi

exit 0
