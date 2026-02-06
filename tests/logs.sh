#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="localhost:4318"
DURATION_MINUTES=60
LOGS_PER_BATCH=3
DELAY=0.02
RETRIES=2
INSECURE=true

_required=(docker sleep head od tr awk openssl)
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

safe_sleep() {
  local t="$1"
  if command -v sleep >/dev/null 2>&1; then
    sleep "$t"; return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import time; time.sleep($t)"
    return
  fi
  if command -v perl >/dev/null 2>&1; then
    perl -e "select(undef,undef,undef,$t)"
    return
  fi
  local sec=${t%%.*}
  if [ -z "$sec" ]; then sec=0; fi
  local end=$((SECONDS + sec))
  while [ "$SECONDS" -lt "$end" ]; do :; done
}

TELEMETRYGEN_IMG="ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest"
DOCKER_RUN="docker run --rm --network host"

SERVICES=(
  "api-gateway"
  "auth-service"
  "payment-service"
  "inventory-service"
  "order-service"
  "notification-service"
  "email-service"
  "shipping-service"
  "catalog-service"
  "search-service"
  "cart-service"
  "recommendation-service"
  "analytics-service"
  "frontend-web"
  "mobile-api"
  "admin-portal"
)

ENVIRONMENTS=("prod" "prod" "prod" "prod" "staging")
REGIONS=("us-east-1" "us-west-2" "eu-west-1" "ap-southeast-2")
NAMESPACES=("default" "backend" "payments" "analytics")
CLUSTERS=("eks-prod-01" "eks-prod-02" "eks-staging-01")

HTTP_METHODS=("GET" "POST" "PUT" "DELETE" "PATCH")
HTTP_PATHS=(
  "/api/v1/login"
  "/api/v1/orders"
  "/api/v1/orders/{id}"
  "/api/v1/payments"
  "/api/v1/products"
  "/api/v1/cart"
  "/api/v1/checkout"
  "/api/v1/search"
  "/api/v1/recommendations"
  "/api/v1/user/profile"
  "/health"
  "/metrics"
  "/ready"
)

LEVELS=("DEBUG" "DEBUG" "INFO" "INFO" "INFO" "INFO" "INFO" "WARN" "ERROR")
INFO_MESSAGES=(
  "request completed successfully"
  "cache hit"
  "database query executed"
  "message published to queue"
  "external API call completed"
  "authentication successful"
  "user session created"
  "order processed"
  "payment authorized"
)
WARN_MESSAGES=(
  "slow database query detected"
  "cache miss - fetching from database"
  "retry attempt for external service"
  "high memory usage detected"
  "connection pool approaching limit"
  "request queue growing"
)
ERROR_MESSAGES=(
  "timeout while calling upstream service"
  "database connection pool exhausted"
  "failed to publish message to kafka"
  "payment provider returned 502"
  "unauthorized request - invalid token"
  "rate limit exceeded"
  "service dependency unavailable"
  "failed to write to cache"
)

random_pick() {
  if [ "$#" -eq 1 ]; then
    IFS=' ' read -r -a _arr <<< "$1"
    arr=("${_arr[@]}")
  else
    arr=("$@")
  fi
  echo "${arr[RANDOM % ${#arr[@]}]}"
}

rand() {
  local min=$1; local max=$2
  if command -v shuf >/dev/null 2>&1; then
    shuf -i "${min}-${max}" -n1
  else
    local range=$((max - min + 1))
    local r=$(( (RANDOM << 15 | RANDOM) % range + min ))
    echo "$r"
  fi
}

hex_id(){
  local n="$1"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$n" 2>/dev/null
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<PY
import secrets,sys
n=int(sys.argv[1])
print(secrets.token_hex(n))
PY
    return
  fi
  local out=""
  for ((i=0;i<n;i++)); do
    out+=$(printf "%02x" $((RANDOM % 256)))
  done
  printf "%s" "$out"
}

END_TIME=$((SECONDS + DURATION_MINUTES * 60))
COUNT=0

echo "=== Starting continuous log generation for ${DURATION_MINUTES} minutes ==="
echo "Press Ctrl+C to stop"
echo ""

while [ "$SECONDS" -lt "$END_TIME" ]; do
  COUNT=$((COUNT + 1))
  
  TRACE_ID=$(hex_id 16)
  SPAN_ID=$(hex_id 8)

  ENV=$(random_pick "${ENVIRONMENTS[*]}")
  REGION=$(random_pick "${REGIONS[*]}")
  CLUSTER=$(random_pick "${CLUSTERS[*]}")
  NAMESPACE=$(random_pick "${NAMESPACES[*]}")
  
  SVC=$(random_pick "${SERVICES[*]}")
  LEVEL=$(random_pick "${LEVELS[*]}")
  METHOD=$(random_pick "${HTTP_METHODS[*]}")
  PATH=$(random_pick "${HTTP_PATHS[*]}")
  
  STATUS=$(rand 200 299)
  LATENCY=$(rand 10 500)
  BODY=$(random_pick "${INFO_MESSAGES[*]}")

  if [[ "$LEVEL" == "ERROR" ]]; then
    BODY=$(random_pick "${ERROR_MESSAGES[*]}")
    STATUS=$(rand 500 504)
    LATENCY=$(rand 1200 5000)
  elif [[ "$LEVEL" == "WARN" ]]; then
    BODY=$(random_pick "${WARN_MESSAGES[*]}")
    STATUS=$(rand 200 504)
    LATENCY=$(rand 800 1800)
  fi
  
  LEVEL_EMOJI="ℹ"
  case "$LEVEL" in
    DEBUG) LEVEL_EMOJI="🔍" ;;
    INFO) LEVEL_EMOJI="✓" ;;
    WARN) LEVEL_EMOJI="⚠" ;;
    ERROR) LEVEL_EMOJI="✗" ;;
  esac

  echo "[$COUNT] $LEVEL_EMOJI $LEVEL | $SVC | $METHOD $PATH | $STATUS | ${LATENCY}ms | $BODY"

  ATTRS="env=\"$ENV\",cloud.region=\"$REGION\",k8s.cluster.name=\"$CLUSTER\",k8s.namespace.name=\"$NAMESPACE\",k8s.pod.name=\"$SVC-$(rand 1000 9999)\",service.version=\"1.$(rand 0 9).$(rand 0 20)\",http.method=\"$METHOD\",http.route=\"$PATH\",http.status_code=$STATUS,http.response_time_ms=$LATENCY,trace_id=\"$TRACE_ID\",span_id=\"$SPAN_ID\",log.level=\"$LEVEL\""

  attempt=0
  until [[ $attempt -ge $RETRIES ]]; do
    set +e
    $DOCKER_RUN $TELEMETRYGEN_IMG logs \
      --otlp-http \
      --otlp-endpoint "$ENDPOINT" \
      $( [ "$INSECURE" = true ] && echo --otlp-insecure ) \
      --service "$SVC" \
      --logs $LOGS_PER_BATCH \
      --body "$BODY" \
      --telemetry-attributes "$ATTRS" \
      >/dev/null 2>&1
    CODE=$?
    set -e

    [[ $CODE -eq 0 ]] && break
    attempt=$((attempt+1))
    safe_sleep 0.5
  done
  
  if [[ $CODE -ne 0 ]]; then
    echo "  FAILED to send logs after $RETRIES attempts"
  fi

  safe_sleep "$DELAY"
  
  if (( COUNT % 100 == 0 )); then
    ELAPSED=$((SECONDS))
    REMAINING=$((END_TIME - SECONDS))
    echo ""
    echo "--- Stats: $COUNT logs sent | ${ELAPSED}s elapsed | ${REMAINING}s remaining ---"
    echo ""
  fi
done

echo ""
echo "=== Complete: $COUNT logs generated over ${DURATION_MINUTES} minutes ==="