#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python || ! -x .venv/bin/schemathesis ]]; then
  echo "Missing .venv with schemathesis installed" >&2
  exit 1
fi

docker rm -f watchdog-gatekeeper-port-proxy >/dev/null 2>&1 || true
docker run -d --name watchdog-gatekeeper-port-proxy --network watchdog_obs -p 4321:4321 alpine/socat TCP-LISTEN:4321,fork,reuseaddr TCP:gateway-auth:4321 >/dev/null

cleanup() {
  docker rm -f watchdog-gatekeeper-port-proxy >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_http_ready() {
  local name="$1"
  local url="$2"
  local timeout_secs="${3:-120}"
  local start_ts
  start_ts="$(date +%s)"

  while true; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    if (( $(date +%s) - start_ts >= timeout_secs )); then
      echo "Timed out waiting for ${name} readiness at ${url}" >&2
      return 1
    fi
    sleep 2
  done
}

wait_for_http_ready "watchdog" "http://127.0.0.1:4319/health" 180
wait_for_http_ready "gatekeeper" "http://127.0.0.1:4321/api/gateway/health" 180

AUTH_EXPORT_FILE="$(mktemp)"
.venv/bin/python - <<'PY' > "$AUTH_EXPORT_FILE"
import json
from dotenv import dotenv_values

env = dotenv_values('.env')

token = env.get('DEFAULT_OTLP_TOKEN') or env.get('OTEL_OTLP_TOKEN', '')
if not token:
    raise SystemExit('Missing required value for DEFAULT_OTLP_TOKEN/OTEL_OTLP_TOKEN')

print(f"export GATEKEEPER_OTLP_TOKEN={json.dumps(token)}")
PY

if [[ ! -s "$AUTH_EXPORT_FILE" ]]; then
  echo "Authentication export generation failed" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$AUTH_EXPORT_FILE"
rm -f "$AUTH_EXPORT_FILE"

mkdir -p test-reports
curl -fsS http://127.0.0.1:4321/openapi.json -o test-reports/openapi-gatekeeper.json
cp -f test-reports/openapi-gatekeeper.json gatekeeper/openapi.json

if [[ "${SCHEMATHESIS_PATCH_SPEC:-0}" == "1" ]]; then
  echo "Applying compatibility patches to OpenAPI snapshot"
.venv/bin/python - <<'PY'
import json
from pathlib import Path

file_path = Path('test-reports/openapi-gatekeeper.json')
spec = json.loads(file_path.read_text())

GENERIC_RESPONSES = {
    '400': {'description': 'Bad Request'},
    '401': {'description': 'Unauthorized'},
    '403': {'description': 'Forbidden'},
    '404': {'description': 'Not Found'},
    '409': {'description': 'Conflict'},
    '429': {'description': 'Too Many Requests'},
    '500': {'description': 'Internal Server Error'},
    '503': {'description': 'Service Unavailable'},
}

for path_item in (spec.get('paths') or {}).values():
    if not isinstance(path_item, dict):
        continue
    for operation in path_item.values():
        if not isinstance(operation, dict):
            continue
        responses = operation.setdefault('responses', {})
        for status_code, response in GENERIC_RESPONSES.items():
            responses.setdefault(status_code, response)

file_path.write_text(json.dumps(spec, separators=(',', ':')))
PY
else
  echo "Using raw OpenAPI snapshot (no mutations)"
fi

COMMON_ARGS=(
  --phases=examples,coverage,fuzzing,stateful
  --checks=not_a_server_error,status_code_conformance,content_type_conformance,response_headers_conformance,response_schema_conformance,negative_data_rejection,missing_required_header,ignored_auth,use_after_free,ensure_resource_availability
  --max-failures=100
  --continue-on-failure
  --workers=4
  --request-timeout=5
  --request-retries=1
  --max-response-time=2
  --generation-deterministic
  --generation-unique-inputs
  --generation-maximize=response_time
  --suppress-health-check=filter_too_much
  --warnings=off
  --report=junit,har,ndjson
)

set +e
.venv/bin/schemathesis run test-reports/openapi-gatekeeper.json \
  --url=http://127.0.0.1:4321 \
  -H "x-otlp-token: ${GATEKEEPER_OTLP_TOKEN}" \
  --exclude-checks=unsupported_method,positive_data_acceptance \
  --report-dir test-reports/schemathesis/gatekeeper \
  "${COMMON_ARGS[@]}" \
  --report-junit-path test-reports/schemathesis-gatekeeper.xml
GATEKEEPER_EXIT=$?
set -e

if [[ $GATEKEEPER_EXIT -ne 0 ]]; then
  echo "Schemathesis gatekeeper run completed with failures: gatekeeper=${GATEKEEPER_EXIT}" >&2
  exit 1
fi

echo "Schemathesis gatekeeper run completed"
