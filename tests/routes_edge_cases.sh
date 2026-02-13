#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
AUTH_TOKEN="${AUTH_TOKEN:-}"
TEST_USERNAME="${TEST_USERNAME:-}"
TEST_PASSWORD="${TEST_PASSWORD:-}"
INBOUND_WEBHOOK_TOKEN="${INBOUND_WEBHOOK_TOKEN:-}"
AGENT_HEARTBEAT_TOKEN="${AGENT_HEARTBEAT_TOKEN:-}"
OTLP_TOKEN="${OTLP_TOKEN:-}"

_required=(curl awk sed mktemp)
_missing=()
for _c in "${_required[@]}"; do
  if ! command -v "$_c" >/dev/null 2>&1; then
    _missing+=("$_c")
  fi
done
if [ "${#_missing[@]}" -gt 0 ]; then
  echo "Missing required commands: ${_missing[*]}. Install them and re-run." >&2
  exit 1
fi

PASS=0
FAIL=0

print_result() {
  local status="$1"
  local name="$2"
  local code="$3"
  local expect="$4"
  if [ "$status" = "PASS" ]; then
    echo "✅ PASS | $name | code=$code | expected=$expect"
  else
    echo "❌ FAIL | $name | code=$code | expected=$expect"
  fi
}

extract_token() {
  local body="$1"
  printf '%s' "$body" | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1
}

login_if_needed() {
  if [ -n "$AUTH_TOKEN" ]; then
    return
  fi
  if [ -z "$TEST_USERNAME" ] || [ -z "$TEST_PASSWORD" ]; then
    echo "AUTH_TOKEN not provided. Set AUTH_TOKEN, or TEST_USERNAME + TEST_PASSWORD for auto-login."
    return
  fi

  local body code token
  body=$(mktemp)
  code=$(curl -sS -o "$body" -w "%{http_code}" \
    -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$TEST_USERNAME\",\"password\":\"$TEST_PASSWORD\"}" || true)

  if [ "$code" != "200" ]; then
    echo "Auto-login failed with HTTP $code"
    cat "$body"
    rm -f "$body"
    return
  fi

  token=$(extract_token "$(cat "$body")")
  rm -f "$body"

  if [ -z "$token" ]; then
    echo "Auto-login succeeded but access_token was not found in response"
    return
  fi

  AUTH_TOKEN="$token"
  echo "Auto-login succeeded"
}

run_case() {
  local name="$1"
  local method="$2"
  local path="$3"
  local expect="$4"
  local auth_mode="${5:-auth}"    # auth | none
  local payload="${6:-}"
  local content_type="${7:-application/json}"
  local extra_header="${8:-}"

  local body code auth_header=()
  body=$(mktemp)

  if [ "$auth_mode" = "auth" ] && [ -n "$AUTH_TOKEN" ]; then
    auth_header=(-H "Authorization: Bearer $AUTH_TOKEN")
  fi

  if [ -n "$payload" ]; then
    code=$(curl -sS -o "$body" -w "%{http_code}" \
      -X "$method" "$BASE_URL$path" \
      "${auth_header[@]}" \
      -H "Content-Type: $content_type" \
      ${extra_header:+-H "$extra_header"} \
      -d "$payload" || true)
  else
    code=$(curl -sS -o "$body" -w "%{http_code}" \
      -X "$method" "$BASE_URL$path" \
      "${auth_header[@]}" \
      ${extra_header:+-H "$extra_header"} || true)
  fi

  local ok=0
  if [ "$expect" = "NON_5XX" ]; then
    if [ "$code" -ge 200 ] && [ "$code" -lt 500 ]; then
      ok=1
    fi
  elif [[ "$code" =~ ^($expect)$ ]]; then
    ok=1
  fi

  if [ "$ok" -eq 1 ]; then
    PASS=$((PASS + 1))
    print_result "PASS" "$name" "$code" "$expect"
  else
    FAIL=$((FAIL + 1))
    print_result "FAIL" "$name" "$code" "$expect"
    echo "--- response body (first 400 chars) ---"
    head -c 400 "$body"; echo
    echo "---------------------------------------"
  fi

  rm -f "$body"
}

echo "========================================"
echo "BeObservant Route + Edge Case Runner"
echo "BASE_URL: $BASE_URL"
echo "========================================"

login_if_needed

echo
echo "[Public endpoint edge cases]"
run_case "root" GET "/" "200" none
run_case "health" GET "/health" "200" none
run_case "gateway validate missing token" GET "/api/gateway/validate" "401" none
run_case "gateway validate invalid token" GET "/api/gateway/validate" "401" none "" "application/json" "x-otlp-token: invalid"
run_case "agents heartbeat missing token" POST "/api/agents/heartbeat" "401" none '{"api_key":"k1","host_name":"h1","ip_address":"127.0.0.1","version":"1.0.0"}'

if [ -n "$OTLP_TOKEN" ]; then
  run_case "gateway validate valid token" GET "/api/gateway/validate" "200" none "" "application/json" "x-otlp-token: $OTLP_TOKEN"
fi

if [ -n "$AGENT_HEARTBEAT_TOKEN" ]; then
  run_case "agents heartbeat valid token" POST "/api/agents/heartbeat" "200" none '{"api_key":"k1","host_name":"h1","ip_address":"127.0.0.1","version":"1.0.0"}' "application/json" "x-agent-heartbeat-token: $AGENT_HEARTBEAT_TOKEN"
fi

if [ -n "$INBOUND_WEBHOOK_TOKEN" ]; then
  run_case "alerts webhook valid token" POST "/alerts/webhook" "200" none '{"alerts":[]}' "application/json" "x-beobservant-webhook-token: $INBOUND_WEBHOOK_TOKEN"
  run_case "alerts critical valid token" POST "/alerts/critical" "200" none '{"alerts":[]}' "application/json" "x-beobservant-webhook-token: $INBOUND_WEBHOOK_TOKEN"
  run_case "alerts warning valid token" POST "/alerts/warning" "200" none '{"alerts":[]}' "application/json" "x-beobservant-webhook-token: $INBOUND_WEBHOOK_TOKEN"
else
  run_case "alerts webhook missing token" POST "/alerts/webhook" "401" none '{"alerts":[]}'
fi

echo
echo "[Auth endpoint edge cases]"
run_case "auth login invalid password" POST "/api/auth/login" "401|422" none '{"username":"invalid","password":"bad"}'
run_case "auth register invalid payload" POST "/api/auth/register" "422" none '{"username":"x"}'

if [ -z "$AUTH_TOKEN" ]; then
  echo
  echo "Skipping authenticated suite because no AUTH_TOKEN is available."
  echo "Provide AUTH_TOKEN or TEST_USERNAME + TEST_PASSWORD to run full route coverage."
else
  echo
  echo "[Authenticated route coverage + edge cases]"

  run_case "auth me" GET "/api/auth/me" "200|401|403" auth
  run_case "auth me update empty" PUT "/api/auth/me" "200|400|401|403|422" auth '{}'
  run_case "auth api keys list" GET "/api/auth/api-keys" "200|401|403" auth
  run_case "auth api key create invalid" POST "/api/auth/api-keys" "400|401|403|422" auth '{"name":""}'
  run_case "auth users" GET "/api/auth/users" "200|401|403" auth
  run_case "auth groups" GET "/api/auth/groups" "200|401|403" auth
  run_case "auth permissions" GET "/api/auth/permissions" "200|401|403" auth
  run_case "auth role defaults" GET "/api/auth/role-defaults" "200|401|403" auth

  run_case "system metrics" GET "/api/system/metrics" "200|401|403" auth

  run_case "agents list" GET "/api/agents/" "200|401|403" auth
  run_case "agents active" GET "/api/agents/active" "200|401|403" auth

  run_case "tempo services" GET "/api/tempo/services" "200|401|403" auth
  run_case "tempo operations" GET "/api/tempo/services/nonexistent/operations" "200|401|403|404" auth
  run_case "tempo search default" GET "/api/tempo/traces/search" "200|401|403|422" auth
  run_case "tempo search invalid limit" GET "/api/tempo/traces/search?limit=0" "422|401|403" auth
  run_case "tempo get trace invalid" GET "/api/tempo/traces/does-not-exist" "404|401|403" auth
  run_case "tempo metrics" GET "/api/tempo/metrics" "200|401|403" auth

  run_case "loki query missing query param" GET "/api/loki/query" "422|401|403" auth
  run_case "loki query instant missing query" GET "/api/loki/query_instant" "422|401|403" auth
  run_case "loki labels" GET "/api/loki/labels" "200|401|403" auth
  run_case "loki label values" GET "/api/loki/label/app/values" "200|401|403|404" auth
  run_case "loki search invalid body" POST "/api/loki/search" "400|401|403|422" auth '{"pattern":""}'
  run_case "loki filter invalid body" POST "/api/loki/filter" "400|401|403|422" auth '{"labels":{}}'
  run_case "loki aggregate missing query" GET "/api/loki/aggregate" "422|401|403" auth
  run_case "loki volume missing query" GET "/api/loki/volume" "422|401|403" auth

  run_case "alertmanager alerts" GET "/api/alertmanager/alerts" "NON_5XX" auth
  run_case "alertmanager alert groups" GET "/api/alertmanager/alerts/groups" "NON_5XX" auth
  run_case "alertmanager delete alerts empty filter" DELETE "/api/alertmanager/alerts?filter_labels={}" "400|401|403|422" auth
  run_case "alertmanager silences" GET "/api/alertmanager/silences" "NON_5XX" auth
  run_case "alertmanager silence not found" GET "/api/alertmanager/silences/not-found" "404|401|403" auth
  run_case "alertmanager status" GET "/api/alertmanager/status" "NON_5XX" auth
  run_case "alertmanager receivers" GET "/api/alertmanager/receivers" "NON_5XX" auth
  run_case "alertmanager rules" GET "/api/alertmanager/rules" "NON_5XX" auth
  run_case "alertmanager metrics names" GET "/api/alertmanager/metrics/names" "NON_5XX" auth
  run_case "alertmanager rule not found" GET "/api/alertmanager/rules/not-found" "404|401|403" auth
  run_case "alertmanager channels" GET "/api/alertmanager/channels" "NON_5XX" auth
  run_case "alertmanager channel not found" GET "/api/alertmanager/channels/not-found" "404|401|403" auth

  run_case "grafana auth hook" GET "/api/grafana/auth" "200|204|401|403" auth
  run_case "grafana dashboard search" GET "/api/grafana/dashboards/search" "NON_5XX" auth
  run_case "grafana dashboard by uid missing" GET "/api/grafana/dashboards/missing" "404|401|403" auth
  run_case "grafana dashboard create invalid visibility" POST "/api/grafana/dashboards?visibility=bad" "400|401|403|422" auth '{"dashboard":{"title":"x"}}'
  run_case "grafana datasources" GET "/api/grafana/datasources" "NON_5XX" auth
  run_case "grafana datasource missing" GET "/api/grafana/datasources/missing" "404|401|403" auth
  run_case "grafana dashboard filters meta" GET "/api/grafana/dashboards/meta/filters" "NON_5XX" auth
  run_case "grafana datasource filters meta" GET "/api/grafana/datasources/meta/filters" "NON_5XX" auth
  run_case "grafana folders" GET "/api/grafana/folders" "NON_5XX" auth
fi

echo
echo "========================================"
echo "Summary: PASS=$PASS FAIL=$FAIL"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
