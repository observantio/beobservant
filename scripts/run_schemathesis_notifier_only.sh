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
    echo ".schemathesis_watchdog_bearer exists but is empty. Put the raw JWT on a single line." >&2
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
wait_for_http_ready "notifier" "http://127.0.0.1:4323/health" 180

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
    watchdog_token = os.getenv('SCHEMATHESIS_WATCHDOG_BEARER', '')
    if not watchdog_token:
        raise SystemExit(
            'Password login is disabled and SCHEMATHESIS_WATCHDOG_BEARER is not set. '
            'Provide a valid bearer token to run authenticated Schemathesis requests.'
        )
else:
    code = resp.status_code if resp is not None else 'n/a'
    body = (resp.text[:300] if resp is not None else 'no response')
    raise SystemExit(f"Failed to obtain watchdog token: {code} {body}")

claims = decode_payload(watchdog_token)
now = int(time.time())
exp = now + 7200

notifier_key = env.get('NOTIFIER_CONTEXT_SIGNING_KEY') or env.get('NOTIFIER_CONTEXT_VERIFY_KEY')
if not notifier_key:
    raise SystemExit('Missing notifier context signing key in .env')

notifier_claims = {
    'sub': str(claims.get('sub', 'schemathesis-user')),
    'user_id': str(claims.get('sub', 'schemathesis-user')),
    'username': str(claims.get('username', username)),
    'tenant_id': str(claims.get('tenant_id', 'default')),
    'org_id': str(claims.get('org_id', claims.get('tenant_id', 'default'))),
    'role': str(claims.get('role', 'admin')),
    'is_superuser': bool(claims.get('is_superuser', True)),
    'permissions': claims.get('permissions') if isinstance(claims.get('permissions'), list) else [],
    'group_ids': claims.get('group_ids') if isinstance(claims.get('group_ids'), list) else [],
    'iss': env.get('NOTIFIER_CONTEXT_ISSUER', 'watchdog-main'),
    'aud': env.get('NOTIFIER_CONTEXT_AUDIENCE', 'notifier'),
    'iat': now,
    'exp': exp,
    'jti': str(uuid.uuid4()),
}

notifier_token = jwt.encode(notifier_claims, notifier_key, algorithm='HS256')

values = {
    'NOTIFIER_SERVICE_TOKEN': env.get('NOTIFIER_EXPECTED_SERVICE_TOKEN') or env.get('GATEWAY_INTERNAL_SERVICE_TOKEN', ''),
    'NOTIFIER_CONTEXT_TOKEN': notifier_token,
}

for key, value in values.items():
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
curl -fsS http://127.0.0.1:4323/openapi.json -o test-reports/openapi-notifier.json
cp -f test-reports/openapi-notifier.json notifier/openapi.json

echo "Using raw OpenAPI snapshot (no mutations)"

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

if ! .venv/bin/schemathesis run test-reports/openapi-notifier.json \
  --url=http://127.0.0.1:4323 \
  -H "X-Service-Token: ${NOTIFIER_SERVICE_TOKEN}" \
  -H "Authorization: Bearer ${NOTIFIER_CONTEXT_TOKEN}" \
  --exclude-checks=unsupported_method,positive_data_acceptance \
    --report-dir test-reports/schemathesis/notifier \
  "${COMMON_ARGS[@]}" \
  --report-junit-path test-reports/schemathesis-notifier.xml; then
  echo "Schemathesis notifier run completed with failures" >&2
  exit 1
fi

echo "Schemathesis notifier run completed"
