#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python || ! -x .venv/bin/schemathesis ]]; then
  echo "Missing .venv with schemathesis installed" >&2
  exit 1
fi

# Ensure resolver is reachable from localhost via proxy container.
docker rm -f watchdog-resolver-port-proxy >/dev/null 2>&1 || true
docker run -d --name watchdog-resolver-port-proxy --network watchdog_obs -p 4322:4322 alpine/socat TCP-LISTEN:4322,fork,reuseaddr TCP:resolver:4322 >/dev/null

# Ensure gatekeeper is reachable from localhost via proxy container.
docker rm -f watchdog-gatekeeper-port-proxy >/dev/null 2>&1 || true
docker run -d --name watchdog-gatekeeper-port-proxy --network watchdog_obs -p 4321:4321 alpine/socat TCP-LISTEN:4321,fork,reuseaddr TCP:gateway-auth:4321 >/dev/null

cleanup() {
  docker rm -f watchdog-resolver-port-proxy >/dev/null 2>&1 || true
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
wait_for_http_ready "notifier" "http://127.0.0.1:4323/health" 180
wait_for_http_ready "resolver" "http://127.0.0.1:4322/api/v1/ready" 180
wait_for_http_ready "gatekeeper" "http://127.0.0.1:4321/api/gateway/health" 180

# Generate required auth material for all services.
AUTH_EXPORT_FILE="$(mktemp)"
.venv/bin/python - <<'PY' > "$AUTH_EXPORT_FILE"
import base64
import json
import os
import time
import uuid

import jwt
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
  # In OIDC-only mode, allow running with x-internal-token and optional pre-provided bearer.
  watchdog_token = os.getenv('SCHEMATHESIS_WATCHDOG_BEARER', '')
  if not watchdog_token:
    raise SystemExit(
      "Password login is disabled and SCHEMATHESIS_WATCHDOG_BEARER is not set. "
      "Provide a valid bearer token to run authenticated Schemathesis requests."
    )
else:
  code = resp.status_code if resp is not None else 'n/a'
  body = (resp.text[:300] if resp is not None else 'no response')
  raise SystemExit(f"Failed to obtain watchdog token: {code} {body}")

claims = decode_payload(watchdog_token)
now = int(time.time())
# The full run can exceed 15 minutes; issue context tokens with a wider TTL.
exp = now + 14400
base_context = {
    'user_id': str(claims.get('sub', 'schemathesis-user')),
    'username': str(claims.get('username', username)),
    'tenant_id': str(claims.get('tenant_id', 'default')),
    'org_id': str(claims.get('org_id', claims.get('tenant_id', 'default'))),
    'role': str(claims.get('role', 'admin')),
    'is_superuser': bool(claims.get('is_superuser', True)),
    'permissions': claims.get('permissions') if isinstance(claims.get('permissions'), list) else [],
    'group_ids': claims.get('group_ids') if isinstance(claims.get('group_ids'), list) else [],
    'iat': now,
    'exp': exp,
}

notifier_key = env.get('NOTIFIER_CONTEXT_SIGNING_KEY') or env.get('NOTIFIER_CONTEXT_VERIFY_KEY')
resolver_key = env.get('RESOLVER_CONTEXT_SIGNING_KEY') or env.get('RESOLVER_CONTEXT_VERIFY_KEY')
if not notifier_key or not resolver_key:
    raise SystemExit('Missing notifier/resolver context signing keys in .env')

notifier_claims = {
    **base_context,
    'iss': env.get('NOTIFIER_CONTEXT_ISSUER', 'watchdog-main'),
    'aud': env.get('NOTIFIER_CONTEXT_AUDIENCE', 'notifier'),
    'jti': str(uuid.uuid4()),
}
resolver_claims = {
    **base_context,
    'iss': env.get('RESOLVER_CONTEXT_ISSUER', 'watchdog-main'),
    'aud': env.get('RESOLVER_CONTEXT_AUDIENCE', 'resolver'),
    'jti': str(uuid.uuid4()),
}

notifier_token = jwt.encode(notifier_claims, notifier_key, algorithm='HS256')
resolver_token = jwt.encode(resolver_claims, resolver_key, algorithm='HS256')

values = {
    'WATCHDOG_BEARER': watchdog_token,
    'INTERNAL_TOKEN': env.get('GATEWAY_INTERNAL_SERVICE_TOKEN', ''),
    'NOTIFIER_SERVICE_TOKEN': env.get('NOTIFIER_EXPECTED_SERVICE_TOKEN') or env.get('GATEWAY_INTERNAL_SERVICE_TOKEN', ''),
    'NOTIFIER_CONTEXT_TOKEN': notifier_token,
    'RESOLVER_SERVICE_TOKEN': env.get('RESOLVER_EXPECTED_SERVICE_TOKEN', ''),
    'RESOLVER_CONTEXT_TOKEN': resolver_token,
  'GATEKEEPER_OTLP_TOKEN': os.getenv('SCHEMATHESIS_GATEKEEPER_OTLP_TOKEN') or env.get('DEFAULT_OTLP_TOKEN') or env.get('OTEL_OTLP_TOKEN', ''),
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

# Refresh local OpenAPI snapshots used for reproducible test artifacts.
curl -fsS http://127.0.0.1:4319/openapi.json -o test-reports/openapi-watchdog.json
curl -fsS http://127.0.0.1:4323/openapi.json -o test-reports/openapi-notifier.json
curl -fsS http://127.0.0.1:4322/openapi.json -o test-reports/openapi-resolver.json
curl -fsS http://127.0.0.1:4321/openapi.json -o test-reports/openapi-gatekeeper.json

# Also publish snapshots at each service root for easier discoverability.
cp -f test-reports/openapi-watchdog.json watchdog/openapi.json
cp -f test-reports/openapi-notifier.json notifier/openapi.json
cp -f test-reports/openapi-resolver.json resolver/openapi.json
cp -f test-reports/openapi-gatekeeper.json gatekeeper/openapi.json

if [[ "${SCHEMATHESIS_PATCH_SPEC:-0}" == "1" ]]; then
  echo "Applying compatibility patches to OpenAPI snapshots"
# Normalize generated OpenAPI docs for robust contract testing.
.venv/bin/python - <<'PY'
import json
from pathlib import Path

FILES = [
  Path('test-reports/openapi-watchdog.json'),
  Path('test-reports/openapi-notifier.json'),
  Path('test-reports/openapi-resolver.json'),
  Path('test-reports/openapi-gatekeeper.json'),
]

GENERIC_RESPONSES = {
  '400': {'description': 'Bad Request'},
  '401': {'description': 'Unauthorized'},
  '403': {'description': 'Forbidden'},
  '404': {'description': 'Not Found'},
  '409': {'description': 'Conflict'},
  '429': {'description': 'Too Many Requests'},
  '500': {'description': 'Internal Server Error'},
}


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
  for path_item in paths.values():
    if not isinstance(path_item, dict):
      continue
    for operation in path_item.values():
      if not isinstance(operation, dict):
        continue
      responses = operation.setdefault('responses', {})
      for status_code, response in GENERIC_RESPONSES.items():
        responses.setdefault(status_code, response)

  components = spec.get('components', {})
  schemas = components.get('schemas', {}) if isinstance(components, dict) else {}
  for schema in schemas.values():
    if isinstance(schema, dict):
      tighten_required_strings(schema)

  file_path.write_text(json.dumps(spec, separators=(',', ':')))
PY
else
  echo "Using raw OpenAPI snapshots (no mutations)"
fi

COMMON_ARGS=(
  --phases=examples,coverage,fuzzing,stateful
  --checks=not_a_server_error,status_code_conformance,content_type_conformance,response_headers_conformance,response_schema_conformance,negative_data_rejection,missing_required_header,ignored_auth,use_after_free,ensure_resource_availability
  --max-failures=100
  --continue-on-failure
  --workers=1
  --request-timeout=20
  --request-retries=2
  --max-response-time=5
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
  --exclude-checks=unsupported_method,positive_data_acceptance \
  --report-dir test-reports/schemathesis/watchdog \
  "${COMMON_ARGS[@]}" \
  --report-junit-path test-reports/schemathesis-watchdog.xml
WATCHDOG_EXIT=$?

.venv/bin/schemathesis run test-reports/openapi-notifier.json \
  --url=http://127.0.0.1:4323 \
  -H "X-Service-Token: ${NOTIFIER_SERVICE_TOKEN}" \
  -H "Authorization: Bearer ${NOTIFIER_CONTEXT_TOKEN}" \
  --exclude-checks=unsupported_method,positive_data_acceptance \
  --report-dir test-reports/schemathesis/notifier \
  "${COMMON_ARGS[@]}" \
  --report-junit-path test-reports/schemathesis-notifier.xml
NOTIFIER_EXIT=$?

.venv/bin/schemathesis run test-reports/openapi-resolver.json \
  --url=http://127.0.0.1:4322 \
  -H "X-Service-Token: ${RESOLVER_SERVICE_TOKEN}" \
  -H "Authorization: Bearer ${RESOLVER_CONTEXT_TOKEN}" \
  --exclude-checks=unsupported_method,positive_data_acceptance \
  --report-dir test-reports/schemathesis/resolver \
  "${COMMON_ARGS[@]}" \
  --report-junit-path test-reports/schemathesis-resolver.xml
RESOLVER_EXIT=$?

.venv/bin/schemathesis run test-reports/openapi-gatekeeper.json \
  --url=http://127.0.0.1:4321 \
  -H "x-otlp-token: ${GATEKEEPER_OTLP_TOKEN}" \
  --exclude-checks=unsupported_method,positive_data_acceptance \
  --report-dir test-reports/schemathesis/gatekeeper \
  "${COMMON_ARGS[@]}" \
  --report-junit-path test-reports/schemathesis-gatekeeper.xml
GATEKEEPER_EXIT=$?

set -e

if [[ $WATCHDOG_EXIT -ne 0 || $NOTIFIER_EXIT -ne 0 || $RESOLVER_EXIT -ne 0 || $GATEKEEPER_EXIT -ne 0 ]]; then
  echo "Schemathesis completed with failures: watchdog=${WATCHDOG_EXIT}, notifier=${NOTIFIER_EXIT}, resolver=${RESOLVER_EXIT}, gatekeeper=${GATEKEEPER_EXIT}" >&2
  exit 1
fi

echo "Schemathesis full-stack run completed"
