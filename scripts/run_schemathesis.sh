#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'USAGE'
Usage: scripts/run_schemathesis.sh <service>

Services:
  watchdog
  gatekeeper
  notifier
  resolver
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

SERVICE="${1:-}"
if [[ -z "$SERVICE" ]]; then
  echo "Missing required service argument" >&2
  usage >&2
  exit 1
fi

case "$SERVICE" in
  watchdog|gatekeeper|notifier|resolver) ;;
  *)
    echo "Invalid service: $SERVICE" >&2
    usage >&2
    exit 1
    ;;
esac

if [[ ! -x .venv/bin/python || ! -x .venv/bin/schemathesis ]]; then
  echo "Missing .venv with schemathesis installed" >&2
  exit 1
fi

if [[ "$SERVICE" != "gatekeeper" && -z "${SCHEMATHESIS_WATCHDOG_BEARER:-}" && -f .schemathesis ]]; then
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

PROXY_CONTAINER=""

cleanup() {
  if [[ -n "$PROXY_CONTAINER" ]]; then
    docker rm -f "$PROXY_CONTAINER" >/dev/null 2>&1 || true
  fi
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

setup_gatekeeper_proxy() {
  PROXY_CONTAINER="watchdog-gatekeeper-port-proxy"
  docker rm -f "$PROXY_CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$PROXY_CONTAINER" --network watchdog_obs -p 4321:4321 alpine/socat TCP-LISTEN:4321,fork,reuseaddr TCP:gateway-auth:4321 >/dev/null
}

setup_resolver_proxy() {
  PROXY_CONTAINER="watchdog-resolver-port-proxy"
  docker rm -f "$PROXY_CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$PROXY_CONTAINER" --network watchdog_obs -p 4322:4322 alpine/socat TCP-LISTEN:4322,fork,reuseaddr TCP:resolver:4322 >/dev/null
}

wait_for_http_ready "watchdog" "http://127.0.0.1:4319/health" 180

case "$SERVICE" in
  gatekeeper)
    setup_gatekeeper_proxy
    wait_for_http_ready "gatekeeper" "http://127.0.0.1:4321/api/gateway/health" 180
    ;;
  notifier)
    wait_for_http_ready "notifier" "http://127.0.0.1:4323/health" 180
    ;;
  resolver)
    setup_resolver_proxy
    wait_for_http_ready "resolver" "http://127.0.0.1:4322/api/v1/ready" 180
    ;;
  watchdog)
    ;;
esac

AUTH_EXPORT_FILE="$(mktemp)"
.venv/bin/python - "$SERVICE" <<'PY' > "$AUTH_EXPORT_FILE"
import base64
import binascii
import json
import os
import sys
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


def login_watchdog_token(env: dict[str, str], use_env_fallback: bool = False) -> tuple[str, dict]:
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
        if use_env_fallback:
            watchdog_token = watchdog_token or (env.get('SCHEMATHESIS_WATCHDOG_BEARER') or '')
        if not watchdog_token:
            raise SystemExit(
                'Password login is disabled and SCHEMATHESIS_WATCHDOG_BEARER is not set. '
                'Provide a valid bearer token to run authenticated Schemathesis requests.'
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

    return watchdog_token, claims


service = sys.argv[1]
env = dotenv_values('.env')

if service == 'watchdog':
    watchdog_token, _ = login_watchdog_token(env, use_env_fallback=True)
    internal_token = env.get('GATEWAY_INTERNAL_SERVICE_TOKEN', '')
    if not internal_token:
        raise SystemExit('Missing required value for GATEWAY_INTERNAL_SERVICE_TOKEN')
    print(f"export WATCHDOG_BEARER={json.dumps(watchdog_token)}")
    print(f"export INTERNAL_TOKEN={json.dumps(internal_token)}")
elif service == 'gatekeeper':
    token = env.get('DEFAULT_OTLP_TOKEN') or env.get('OTEL_OTLP_TOKEN', '')
    if not token:
        raise SystemExit('Missing required value for DEFAULT_OTLP_TOKEN/OTEL_OTLP_TOKEN')
    print(f"export GATEKEEPER_OTLP_TOKEN={json.dumps(token)}")
elif service == 'notifier':
    watchdog_token, claims = login_watchdog_token(env)

    now = int(time.time())
    exp = now + 7200
    username = os.getenv('SCHEMATHESIS_ADMIN_USERNAME', env.get('DEFAULT_ADMIN_USERNAME', 'admin'))

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
        'jti': f"schemathesis-{uuid.uuid4()}",
    }

    notifier_token = jwt.encode(notifier_claims, notifier_key, algorithm='HS256')

    notifier_service_token = env.get('NOTIFIER_EXPECTED_SERVICE_TOKEN') or env.get('GATEWAY_INTERNAL_SERVICE_TOKEN', '')
    if not notifier_service_token:
        raise SystemExit('Missing required value for NOTIFIER_EXPECTED_SERVICE_TOKEN/GATEWAY_INTERNAL_SERVICE_TOKEN')

    print(f"export NOTIFIER_SERVICE_TOKEN={json.dumps(notifier_service_token)}")
    print(f"export NOTIFIER_CONTEXT_TOKEN={json.dumps(notifier_token)}")
elif service == 'resolver':
    watchdog_token, claims = login_watchdog_token(env)

    now = int(time.time())
    exp = now + 7200
    username = os.getenv('SCHEMATHESIS_ADMIN_USERNAME', env.get('DEFAULT_ADMIN_USERNAME', 'admin'))

    resolver_key = env.get('RESOLVER_CONTEXT_SIGNING_KEY') or env.get('RESOLVER_CONTEXT_VERIFY_KEY')
    if not resolver_key:
        raise SystemExit('Missing resolver context signing key in .env')

    resolver_claims = {
        'sub': str(claims.get('sub', 'schemathesis-user')),
        'user_id': str(claims.get('sub', 'schemathesis-user')),
        'username': str(claims.get('username', username)),
        'tenant_id': str(claims.get('tenant_id', 'default')),
        'org_id': str(claims.get('org_id', claims.get('tenant_id', 'default'))),
        'role': str(claims.get('role', 'admin')),
        'is_superuser': bool(claims.get('is_superuser', True)),
        'permissions': claims.get('permissions') if isinstance(claims.get('permissions'), list) else [],
        'group_ids': claims.get('group_ids') if isinstance(claims.get('group_ids'), list) else [],
        'iss': env.get('RESOLVER_CONTEXT_ISSUER', 'watchdog-main'),
        'aud': env.get('RESOLVER_CONTEXT_AUDIENCE', 'resolver'),
        'iat': now,
        'exp': exp,
        'jti': str(uuid.uuid4()),
    }

    resolver_token = jwt.encode(resolver_claims, resolver_key, algorithm='HS256')

    resolver_service_token = env.get('RESOLVER_EXPECTED_SERVICE_TOKEN', '')
    if not resolver_service_token:
        raise SystemExit('Missing required value for RESOLVER_EXPECTED_SERVICE_TOKEN')

    print(f"export RESOLVER_SERVICE_TOKEN={json.dumps(resolver_service_token)}")
    print(f"export RESOLVER_CONTEXT_TOKEN={json.dumps(resolver_token)}")
else:
    raise SystemExit(f'Unsupported service: {service}')
PY

if [[ ! -s "$AUTH_EXPORT_FILE" ]]; then
  echo "Authentication export generation failed" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$AUTH_EXPORT_FILE"
rm -f "$AUTH_EXPORT_FILE"

mkdir -p test-reports

SPEC_PATH=""
TARGET_URL=""
SERVICE_OPENAPI_PATH=""
REPORT_DIR=""
JUNIT_PATH=""

declare -a EXTRA_HEADERS=()
declare -a COMMON_ARGS=()

after_snapshot_mutation() {
  local target_file="$1"

  if [[ "$SERVICE" == "watchdog" ]]; then
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
    return
  fi

  if [[ "$SERVICE" == "gatekeeper" ]]; then
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
    return
  fi

  echo "Using raw OpenAPI snapshot (no mutations)"
}

case "$SERVICE" in
  watchdog)
    SPEC_PATH="test-reports/openapi-watchdog.json"
    TARGET_URL="http://127.0.0.1:4319"
    SERVICE_OPENAPI_PATH="watchdog/openapi.json"
    REPORT_DIR="test-reports/schemathesis/watchdog"
    JUNIT_PATH="test-reports/schemathesis-watchdog.xml"

    curl -fsS "${TARGET_URL}/openapi.json" -o "$SPEC_PATH"
    cp -f "$SPEC_PATH" "$SERVICE_OPENAPI_PATH"
    after_snapshot_mutation "$SPEC_PATH"

    EXTRA_HEADERS+=("-H" "x-internal-token: ${INTERNAL_TOKEN}")
    EXTRA_HEADERS+=("-H" "Cookie:")
    if [[ -n "${WATCHDOG_BEARER:-}" ]]; then
      EXTRA_HEADERS+=("-H" "Authorization: Bearer ${WATCHDOG_BEARER}")
    fi

    COMMON_ARGS=(
      --phases=examples,coverage,fuzzing,stateful
      --checks=not_a_server_error,status_code_conformance,content_type_conformance,response_headers_conformance,response_schema_conformance,negative_data_rejection,missing_required_header,ignored_auth,use_after_free,ensure_resource_availability
      --max-failures=20
      --continue-on-failure
      --workers=4
      --request-timeout=5
      --request-retries=1
      --rate-limit="${SCHEMATHESIS_RATE_LIMIT:-8/s}"
      --max-response-time=4
      --generation-deterministic
      --generation-unique-inputs
      --generation-maximize=response_time
      --suppress-health-check=filter_too_much
      --warnings=off
      --report=junit,har,ndjson
    )
    ;;
  gatekeeper)
    SPEC_PATH="test-reports/openapi-gatekeeper.json"
    TARGET_URL="http://127.0.0.1:4321"
    SERVICE_OPENAPI_PATH="gatekeeper/openapi.json"
    REPORT_DIR="test-reports/schemathesis/gatekeeper"
    JUNIT_PATH="test-reports/schemathesis-gatekeeper.xml"

    curl -fsS "${TARGET_URL}/openapi.json" -o "$SPEC_PATH"
    cp -f "$SPEC_PATH" "$SERVICE_OPENAPI_PATH"
    after_snapshot_mutation "$SPEC_PATH"

    EXTRA_HEADERS+=("-H" "x-otlp-token: ${GATEKEEPER_OTLP_TOKEN}")

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
    ;;
  notifier)
    SPEC_PATH="test-reports/openapi-notifier.json"
    TARGET_URL="http://127.0.0.1:4323"
    SERVICE_OPENAPI_PATH="notifier/openapi.json"
    REPORT_DIR="test-reports/schemathesis/notifier"
    JUNIT_PATH="test-reports/schemathesis-notifier.xml"

    curl -fsS "${TARGET_URL}/openapi.json" -o "$SPEC_PATH"
    cp -f "$SPEC_PATH" "$SERVICE_OPENAPI_PATH"
    after_snapshot_mutation "$SPEC_PATH"

    EXTRA_HEADERS+=("-H" "X-Service-Token: ${NOTIFIER_SERVICE_TOKEN}")
    EXTRA_HEADERS+=("-H" "Authorization: Bearer ${NOTIFIER_CONTEXT_TOKEN}")

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
    ;;
  resolver)
    SPEC_PATH="test-reports/openapi-resolver.json"
    TARGET_URL="http://127.0.0.1:4322"
    SERVICE_OPENAPI_PATH="resolver/openapi.json"
    REPORT_DIR="test-reports/schemathesis/resolver"
    JUNIT_PATH="test-reports/schemathesis-resolver.xml"

    curl -fsS "${TARGET_URL}/openapi.json" -o "$SPEC_PATH"
    cp -f "$SPEC_PATH" "$SERVICE_OPENAPI_PATH"
    after_snapshot_mutation "$SPEC_PATH"

    EXTRA_HEADERS+=("-H" "X-Service-Token: ${RESOLVER_SERVICE_TOKEN}")
    EXTRA_HEADERS+=("-H" "Authorization: Bearer ${RESOLVER_CONTEXT_TOKEN}")

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
    ;;
esac

set +e
.venv/bin/schemathesis run "$SPEC_PATH" \
  --url="$TARGET_URL" \
  "${EXTRA_HEADERS[@]}" \
  --exclude-checks=unsupported_method,positive_data_acceptance \
  --report-dir "$REPORT_DIR" \
  "${COMMON_ARGS[@]}" \
  --report-junit-path "$JUNIT_PATH"
SCHEMATHESIS_EXIT=$?
set -e

if [[ $SCHEMATHESIS_EXIT -ne 0 ]]; then
  echo "Schemathesis ${SERVICE} run completed with failures: ${SERVICE}=${SCHEMATHESIS_EXIT}" >&2
  exit 1
fi

echo "Schemathesis ${SERVICE} run completed"
