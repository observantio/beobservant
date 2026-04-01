#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python || ! -x .venv/bin/schemathesis ]]; then
  echo "Missing .venv with schemathesis installed" >&2
  exit 1
fi

if [[ -z "${SCHEMATHESIS_WATCHDOG_BEARER:-}" && -f .schemathesis ]]; then
  if [[ ! -s .schemathesis ]]; then
    echo ".schemathesis exists but is empty. Put the raw JWT on a single line." >&2
    exit 1
  fi

  SCHEMATHESIS_WATCHDOG_BEARER="$(tr -d '\r\n' < .schemathesis)"
  if [[ -z "${SCHEMATHESIS_WATCHDOG_BEARER}" ]]; then
    echo ".schemathesis contained only whitespace/newlines. Put the raw JWT on a single line." >&2
    exit 1
  fi

  export SCHEMATHESIS_WATCHDOG_BEARER
fi

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

AUTH_EXPORT_FILE="$(mktemp)"
.venv/bin/python - <<'PY' > "$AUTH_EXPORT_FILE"
import base64
import binascii
import json
import os
import time

import requests
from dotenv import dotenv_values
from requests import RequestException


def b64url_decode(data: str) -> bytes:
    pad = '=' * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + pad)


def decode_payload(token: str) -> dict:
    parts = token.split('.')
    if len(parts) < 2:
        return {}
    return json.loads(b64url_decode(parts[1]).decode('utf-8'))


env = dotenv_values('.env')
base = os.getenv('WATCHDOG_BASE_URL', 'http://127.0.0.1:4319')
username = os.getenv('SCHEMATHESIS_ADMIN_USERNAME', env.get('DEFAULT_ADMIN_USERNAME', 'admin'))
password_candidates = [
    os.getenv('SCHEMATHESIS_ADMIN_PASSWORD', ''),
    'TempSchemathesisPass123!',
    env.get('DEFAULT_ADMIN_PASSWORD', ''),
]
password_candidates = [p for p in password_candidates if p]

resp = None
for password in password_candidates:
  for _ in range(10):
    try:
      resp = requests.post(
        f"{base}/api/auth/login",
        json={"username": username, "password": password},
        timeout=20,
      )
      if resp.status_code == 200:
        break
      if resp.status_code >= 500:
        time.sleep(1)
        continue
      break
    except RequestException:
      time.sleep(1)
  if resp is not None and resp.status_code == 200:
    break

watchdog_token = ''
if resp is not None and resp.status_code == 200:
  watchdog_token = resp.json().get('access_token', '')
  if not watchdog_token:
    raise SystemExit('Login succeeded but no access_token in response')
elif resp is not None and resp.status_code == 403 and 'Password login is disabled' in (resp.text or ''):
  watchdog_token = os.getenv('SCHEMATHESIS_WATCHDOG_BEARER', '') or (env.get('SCHEMATHESIS_WATCHDOG_BEARER') or '')
  if not watchdog_token:
    raise SystemExit(
      "Password login is disabled and SCHEMATHESIS_WATCHDOG_BEARER is not set. "
      "Provide a valid bearer token to run authenticated Schemathesis requests."
    )
else:
  code = resp.status_code if resp is not None else 'n/a'
  body = (resp.text[:300] if resp is not None else 'no response')
  raise SystemExit(f"Failed to obtain watchdog token: {code} {body}")

try:
  claims = decode_payload(watchdog_token)
except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
  claims = {}
if not isinstance(claims, dict):
  claims = {}

values = {
    'WATCHDOG_BEARER': watchdog_token,
    'INTERNAL_TOKEN': env.get('GATEWAY_INTERNAL_SERVICE_TOKEN', ''),
}
for key, value in values.items():
    if key == 'WATCHDOG_BEARER':
        print(f"export {key}={json.dumps(value)}")
        continue
    if not value:
        raise SystemExit(f'Missing required value for {key}')
    print(f"export {key}={json.dumps(value)}")
PY

if [[ ! -s "$AUTH_EXPORT_FILE" ]]; then
  echo "Authentication export generation failed" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$AUTH_EXPORT_FILE"
rm -f "$AUTH_EXPORT_FILE"

mkdir -p test-reports
curl -fsS http://127.0.0.1:4319/openapi.json -o test-reports/openapi-watchdog.json
cp -f test-reports/openapi-watchdog.json watchdog/openapi.json

if [[ "${SCHEMATHESIS_PATCH_SPEC:-0}" == "1" ]]; then
  echo "Applying compatibility patches to OpenAPI snapshot"
.venv/bin/python - <<'PY'
import json
from pathlib import Path

FILES = [Path('test-reports/openapi-watchdog.json')]

def tighten_required_strings(schema: dict) -> None:
  if not isinstance(schema, dict):
    return

  required = schema.get('required')
  props = schema.get('properties')
  if isinstance(required, list) and isinstance(props, dict):
    for prop_name in required:
      prop = props.get(prop_name)
      if not isinstance(prop, dict):
        continue
      if prop.get('type') == 'string' and 'minLength' not in prop and 'enum' not in prop:
        prop['minLength'] = 1

  for value in schema.values():
    if isinstance(value, dict):
      tighten_required_strings(value)
    elif isinstance(value, list):
      for item in value:
        if isinstance(item, dict):
          tighten_required_strings(item)


for file_path in FILES:
  spec = json.loads(file_path.read_text())
  paths = spec.get('paths', {})
  internal_validate = paths.get('/api/internal/otlp/validate', {})
  if isinstance(internal_validate, dict):
    legacy_get = internal_validate.get('get')
    if isinstance(legacy_get, dict):
      responses = legacy_get.setdefault('responses', {})
      responses.setdefault('410', {'description': 'Gone'})

  ready_path = paths.get('/ready', {})
  if isinstance(ready_path, dict):
    ready_get = ready_path.get('get')
    if isinstance(ready_get, dict):
      responses = ready_get.setdefault('responses', {})
      responses.setdefault('503', {'description': 'Service Unavailable'})

  components = spec.get('components', {})
  schemas = components.get('schemas', {}) if isinstance(components, dict) else {}
  for schema in schemas.values():
    if isinstance(schema, dict):
      tighten_required_strings(schema)

  file_path.write_text(json.dumps(spec, separators=(',', ':')))
PY
else
  echo "Using raw OpenAPI snapshot (no mutations)"
fi

COMMON_ARGS=(
  --phases=examples,coverage,fuzzing,stateful
  --checks=not_a_server_error,status_code_conformance,content_type_conformance,response_headers_conformance,response_schema_conformance,negative_data_rejection,missing_required_header,ignored_auth,use_after_free,ensure_resource_availability
  --max-failures=20
  --continue-on-failure
  --workers=4
  --request-timeout=5
  --request-retries=1
  --max-response-time=4
  --generation-deterministic
  --generation-unique-inputs
  --generation-maximize=response_time
  --suppress-health-check=filter_too_much
  --warnings=off
  --report=junit,har,ndjson
)

WATCHDOG_AUTH_ARGS=()
if [[ -n "${WATCHDOG_BEARER}" ]]; then
  WATCHDOG_AUTH_ARGS=(-H "Authorization: Bearer ${WATCHDOG_BEARER}")
fi

set +e
.venv/bin/schemathesis run test-reports/openapi-watchdog.json \
  --url=http://127.0.0.1:4319 \
  "${WATCHDOG_AUTH_ARGS[@]}" \
  -H "x-internal-token: ${INTERNAL_TOKEN}" \
  -H "Cookie:" \
  --exclude-checks=unsupported_method,positive_data_acceptance \
  --report-dir test-reports/schemathesis/watchdog \
  "${COMMON_ARGS[@]}" \
  --report-junit-path test-reports/schemathesis-watchdog.xml
WATCHDOG_EXIT=$?
set -e

if [[ $WATCHDOG_EXIT -ne 0 ]]; then
  echo "Schemathesis watchdog run completed with failures: watchdog=${WATCHDOG_EXIT}" >&2
  exit 1
fi

echo "Schemathesis watchdog run completed"
