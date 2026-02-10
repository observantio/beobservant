#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="${1:-localhost:4318}"
COUNT="${2:-500}"
DELAY="${3:-0.03}"
RETRIES=3
INSECURE=true

_required=(docker sleep head od tr awk)
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

FRONTENDS=(
  "web-frontend" "mobile-ios" "mobile-android" "admin-portal" 
  "partner-portal" "merchant-dashboard" "customer-app"
)

GATEWAYS=(
  "api-gateway" "graphql-gateway" "grpc-gateway" "websocket-gateway"
)

CORE_SERVICES=(
  "user-service" "auth-service" "session-service" "profile-service"
  "permissions-service" "tenant-service" "feature-flags-service"
)

BUSINESS_SERVICES=(
  "order-service" "payment-service" "inventory-service" "shipping-service"
  "pricing-service" "catalog-service" "cart-service" "recommendation-service"
  "search-service" "notification-service" "email-service" "sms-service"
  "analytics-service" "reporting-service" "fraud-detection" "loyalty-service"
  "review-service" "wishlist-service" "promotion-service" "tax-service"
  "warehouse-service" "fulfillment-service" "returns-service"
)

DATA_STORES=(
  "postgres-primary" "postgres-replica-1" "postgres-replica-2"
  "mysql-primary" "mysql-replica"
  "redis-cache" "redis-session" "redis-queue"
  "mongodb-primary" "mongodb-replica"
  "elasticsearch" "opensearch"
  "cassandra-node-1" "cassandra-node-2"
  "s3-storage" "gcs-storage"
)

MESSAGE_SYSTEMS=(
  "kafka-broker-1" "kafka-broker-2" "kafka-broker-3"
  "rabbitmq" "pulsar" "kinesis" "sqs" "sns"
)

EXTERNAL_SERVICES=(
  "stripe-api" "paypal-api" "sendgrid-api" "twilio-api"
  "aws-sqs" "aws-lambda" "cloudflare-cdn" "datadog-agent"
  "auth0-api" "okta-api" "segment-api" "amplitude-api"
  "google-maps-api" "openai-api" "algolia-api"
)

REGIONS=("us-east-1" "us-west-2" "eu-west-1" "eu-central-1" "ap-southeast-1" "ap-southeast-2" "ap-northeast-1")
ENVS=("prod" "prod" "prod" "prod" "staging" "staging" "dev")
CUSTOMERS=("acme-corp" "globex" "initech" "umbrella-corp" "wayne-enterprises" "stark-industries" "free-tier" "premium-tier" "enterprise-tier")
HTTP_METHODS=("GET" "POST" "PUT" "PATCH" "DELETE")

USER_AGENTS=(
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1"
  "okhttp/4.12.0" "axios/1.6.0" "curl/8.4.0"
  "iOS/17.0 (com.example.app)" "Android/14 (com.example.app)"
)

hex_id(){
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1" 2>/dev/null || head -c "$1" /dev/urandom | od -An -v -t x1 | tr -d ' \n'
  else
    head -c "$1" /dev/urandom | od -An -v -t x1 | tr -d ' \n'
  fi
}

rand() {
  local min=$1; local max=$2
  if command -v shuf >/dev/null 2>&1; then
    shuf -i "${min}-${max}" -n1
  else
    local range=$((max - min + 1))
    echo $(( (RANDOM << 15 | RANDOM) % range + min ))
  fi
}

pick() {
  local arr=("$@")
  echo "${arr[$((RANDOM % ${#arr[@]}))]}"
}

send_span(){
  local svc=$1
  local trace=$2
  local parent=$3
  local name=$4
  local dur=$5
  local status=$6
  local attrs=$7

  attrs_with_ids="$attrs,trace_id=\"$trace\""
  if [ -n "$parent" ]; then attrs_with_ids="$attrs_with_ids,parent_span_id=\"$parent\""; fi
  attrs_with_ids="$attrs_with_ids,span.name=\"$name\""

  local status_emoji="✓"
  local status_text="OK"
  if [[ $status -eq 1 ]]; then
    status_emoji="✗"
    status_text="ERROR"
  elif [[ $status -eq 2 ]]; then
    status_emoji="⚠"
    status_text="WARN"
  fi
  
  echo "  $status_emoji $svc | $name | ${dur}ms | $status_text"

  attempt=0
  CODE=1
  until [[ $attempt -ge $RETRIES ]]; do
    set +e
    $DOCKER_RUN $TELEMETRYGEN_IMG traces \
      --otlp-http \
      --otlp-endpoint "$ENDPOINT" \
      $( [ "$INSECURE" = true ] && echo --otlp-insecure ) \
      --service "$svc" \
      --traces 1 \
      --span-duration "${dur}ms" \
      --status-code "$status" \
      --telemetry-attributes "$attrs_with_ids" \
      >/dev/null 2>&1
    CODE=$?
    set -e
    [[ $CODE -eq 0 ]] && break
    attempt=$((attempt+1))
    [[ $attempt -lt $RETRIES ]] && safe_sleep 0.3
  done
  if [[ $CODE -ne 0 ]]; then
    echo "    ⚠ Send failed after $attempt attempts" >&2
  fi
}

generate_realistic_latency() {
  local base=$1
  local variance=$2
  local spike_chance=${3:-5}
  
  if [[ $((RANDOM % 100)) -lt spike_chance ]]; then
    echo $((base * $(rand 3 10)))
  else
    local var=$((RANDOM % variance))
    echo $((base + var - variance/2))
  fi
}

generate_http_status() {
  local error_type=$1
  
  if [[ $error_type -eq 0 ]]; then
    local success_codes=(200 200 200 200 201 201 202 204)
    echo "${success_codes[$((RANDOM % ${#success_codes[@]}))]}"
  else
    local error_codes=(400 401 403 404 409 422 429 500 502 503 504)
    echo "${error_codes[$((RANDOM % ${#error_codes[@]}))]}"
  fi
}

should_have_error() {
  local base_rate=${1:-3}
  local env=$2
  
  if [[ "$env" == "dev" ]]; then
    base_rate=15
  elif [[ "$env" == "staging" ]]; then
    base_rate=8
  fi
  
  [[ $((RANDOM % 100)) -lt $base_rate ]]
  return $?
}

should_timeout() {
  [[ $((RANDOM % 100)) -lt 2 ]]
  return $?
}

generate_user_flow() {
  local trace_id=$1
  local region=$2
  local env=$3
  local customer=$4
  
  local frontend="$(pick "${FRONTENDS[@]}")"
  local gateway="$(pick "${GATEWAYS[@]}")"
  local user_agent="$(pick "${USER_AGENTS[@]}")"
  
  local root_span=$(hex_id 8)
  local gw_span=$(hex_id 8)
  
  local routes=(
    "/api/products:GET"
    "/api/products/{id}:GET"
    "/api/cart:GET"
    "/api/cart:POST"
    "/api/cart/items:DELETE"
    "/api/search:GET"
    "/api/user/profile:GET"
    "/api/user/profile:PUT"
    "/api/checkout:POST"
    "/api/orders:GET"
    "/api/orders/{id}:GET"
    "/api/reviews:POST"
    "/api/wishlist:GET"
    "/api/recommendations:GET"
    "/graphql:POST"
    "/api/notifications:GET"
    "/api/analytics/track:POST"
  )
  
  local route_info="$(pick "${routes[@]}")"
  local route="${route_info%:*}"
  local method="${route_info#*:}"
  
  local has_error=0
  should_have_error 3 "$env" && has_error=1
  
  local has_timeout=0
  should_timeout && has_timeout=1
  
  local status_code=$(generate_http_status $has_error)
  
  local trace_flags=""
  [[ $((RANDOM % 10)) -eq 0 ]] && trace_flags="sampled=true,debug=true"
  
  echo ""
  echo "[$method $route] $env/$region | $customer | trace=${trace_id:0:12}... | HTTP $status_code"
  
  local frontend_dur=$(generate_realistic_latency 50 60 8)
  if [[ $has_timeout -eq 1 ]]; then
    frontend_dur=$((frontend_dur * 20))
  fi
  
  send_span \
    "$frontend" \
    "$trace_id" \
    "" \
    "$method $route" \
    "$frontend_dur" \
    "$has_error" \
    "env=\"$env\",cloud.region=\"$region\",http.method=\"$method\",http.route=\"$route\",http.status_code=\"$status_code\",customer=\"$customer\",user_agent=\"$user_agent\",$trace_flags"
  
  local gw_dur=$(generate_realistic_latency 80 100 6)
  if [[ $has_timeout -eq 1 ]]; then
    gw_dur=$((gw_dur * 15))
    has_error=1
  fi
  
  send_span \
    "$gateway" \
    "$trace_id" \
    "$root_span" \
    "$method $route" \
    "$gw_dur" \
    "$has_error" \
    "env=\"$env\",cloud.region=\"$region\",http.method=\"$method\",http.route=\"$route\",http.status_code=\"$status_code\",gateway.type=\"${gateway}\""
  
  if [[ $has_error -eq 0 ]] || [[ $((RANDOM % 2)) -eq 0 ]]; then
    local auth_span=$(hex_id 8)
    local auth_dur=$(generate_realistic_latency 15 20 3)
    
    send_span \
      "auth-service" \
      "$trace_id" \
      "$gw_span" \
      "ValidateToken" \
      "$auth_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",rpc.method=\"ValidateToken\",rpc.system=\"grpc\""
    
    local cache_hit=$((RANDOM % 100 < 70))
    if [[ $cache_hit -eq 1 ]]; then
      send_span \
        "$(pick redis-cache redis-session)" \
        "$trace_id" \
        "$auth_span" \
        "GET session:${trace_id:0:8}" \
        "$(rand 1 5)" \
        0 \
        "db.system=\"redis\",db.operation=\"GET\",cache.hit=\"true\""
    else
      send_span \
        "$(pick redis-cache redis-session)" \
        "$trace_id" \
        "$auth_span" \
        "GET session:${trace_id:0:8}" \
        "$(rand 2 6)" \
        0 \
        "db.system=\"redis\",db.operation=\"GET\",cache.hit=\"false\""
      
      send_span \
        "$(pick postgres-primary postgres-replica-1)" \
        "$trace_id" \
        "$auth_span" \
        "SELECT users WHERE id=$1" \
        "$(rand 10 30)" \
        0 \
        "db.system=\"postgresql\",db.operation=\"SELECT\",db.sql.table=\"users\""
    fi
  fi
  
  if [[ $has_error -eq 0 ]]; then
    case "$route" in
      /api/products*|/api/search*)
        generate_product_flow "$trace_id" "$gw_span" "$region" "$env"
        ;;
      /api/cart*)
        generate_cart_flow "$trace_id" "$gw_span" "$region" "$env"
        ;;
      /api/checkout*)
        generate_checkout_flow "$trace_id" "$gw_span" "$region" "$env" "$customer"
        ;;
      /api/user/profile*)
        generate_profile_flow "$trace_id" "$gw_span" "$region" "$env"
        ;;
      /api/orders*)
        generate_orders_flow "$trace_id" "$gw_span" "$region" "$env"
        ;;
      /api/reviews*)
        generate_reviews_flow "$trace_id" "$gw_span" "$region" "$env"
        ;;
      /api/wishlist*)
        generate_wishlist_flow "$trace_id" "$gw_span" "$region" "$env"
        ;;
      /api/recommendations*)
        generate_recommendation_flow "$trace_id" "$gw_span" "$region" "$env"
        ;;
      /graphql*)
        generate_graphql_flow "$trace_id" "$gw_span" "$region" "$env"
        ;;
      *)
        generate_generic_flow "$trace_id" "$gw_span" "$region" "$env"
        ;;
    esac
  fi
}

generate_product_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  
  local catalog_span=$(hex_id 8)
  local catalog_dur=$(generate_realistic_latency 60 80 5)
  
  send_span \
    "catalog-service" \
    "$trace_id" \
    "$parent" \
    "GetProducts" \
    "$catalog_dur" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"GetProducts\",rpc.system=\"grpc\",product.category=\"electronics\""
  
  local cache_strategy=$((RANDOM % 3))
  if [[ $cache_strategy -eq 0 ]]; then
    send_span \
      "redis-cache" \
      "$trace_id" \
      "$catalog_span" \
      "MGET products:*" \
      "$(rand 2 8)" \
      0 \
      "db.system=\"redis\",db.operation=\"MGET\",cache.hit=\"true\""
  else
    send_span \
      "$(pick postgres-replica-1 postgres-replica-2)" \
      "$trace_id" \
      "$catalog_span" \
      "SELECT * FROM products WHERE category=$1 LIMIT 50" \
      "$(generate_realistic_latency 30 40 8)" \
      0 \
      "db.system=\"postgresql\",db.operation=\"SELECT\",db.sql.table=\"products\",db.rows_returned=\"$(rand 10 50)\""
  fi
  
  if [[ $((RANDOM % 3)) -eq 0 ]]; then
    local search_span=$(hex_id 8)
    send_span \
      "search-service" \
      "$trace_id" \
      "$parent" \
      "Search" \
      "$(generate_realistic_latency 100 150 10)" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",rpc.method=\"Search\",search.query=\"laptop\""
    
    send_span \
      "$(pick elasticsearch opensearch)" \
      "$trace_id" \
      "$search_span" \
      "POST /_search" \
      "$(generate_realistic_latency 80 120 12)" \
      0 \
      "db.system=\"elasticsearch\",db.operation=\"SEARCH\",search.hits=\"$(rand 5 200)\""
  fi
  
  if [[ $((RANDOM % 2)) -eq 0 ]]; then
    local rec_span=$(hex_id 8)
    send_span \
      "recommendation-service" \
      "$trace_id" \
      "$parent" \
      "GetRecommendations" \
      "$(generate_realistic_latency 120 200 15)" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",rpc.method=\"GetRecommendations\",ml.model=\"collaborative-filtering-v2\""
    
    if [[ $((RANDOM % 2)) -eq 0 ]]; then
      send_span \
        "openai-api" \
        "$trace_id" \
        "$rec_span" \
        "POST /v1/embeddings" \
        "$(generate_realistic_latency 200 400 20)" \
        0 \
        "http.method=\"POST\",net.peer.name=\"api.openai.com\",ai.model=\"text-embedding-ada-002\""
    fi
  fi
}

generate_cart_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  
  local cart_span=$(hex_id 8)
  send_span \
    "cart-service" \
    "$trace_id" \
    "$parent" \
    "UpdateCart" \
    "$(generate_realistic_latency 40 60 6)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"UpdateCart\",cart.items=\"$(rand 1 10)\""
  
  send_span \
    "redis-cache" \
    "$trace_id" \
    "$cart_span" \
    "SETEX cart:${trace_id:0:8} 3600" \
    "$(rand 2 10)" \
    0 \
    "db.system=\"redis\",db.operation=\"SETEX\""
  
  local inv_span=$(hex_id 8)
  send_span \
    "inventory-service" \
    "$trace_id" \
    "$cart_span" \
    "CheckAvailability" \
    "$(generate_realistic_latency 35 50 8)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"CheckAvailability\""
  
  local db_choice=$((RANDOM % 3))
  if [[ $db_choice -eq 0 ]]; then
    send_span \
      "$(pick postgres-replica-1 postgres-replica-2)" \
      "$trace_id" \
      "$inv_span" \
      "SELECT stock FROM inventory WHERE sku IN ($1,$2,$3)" \
      "$(rand 15 45)" \
      0 \
      "db.system=\"postgresql\",db.operation=\"SELECT\",db.sql.table=\"inventory\""
  else
    send_span \
      "$(pick cassandra-node-1 cassandra-node-2)" \
      "$trace_id" \
      "$inv_span" \
      "SELECT * FROM inventory.stock WHERE sku=?" \
      "$(rand 20 60)" \
      0 \
      "db.system=\"cassandra\",db.operation=\"SELECT\""
  fi
  
  local price_span=$(hex_id 8)
  send_span \
    "pricing-service" \
    "$trace_id" \
    "$cart_span" \
    "CalculatePrice" \
    "$(generate_realistic_latency 25 40 5)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"CalculatePrice\",pricing.strategy=\"dynamic\""
  
  if [[ $((RANDOM % 4)) -eq 0 ]]; then
    local promo_span=$(hex_id 8)
    send_span \
      "promotion-service" \
      "$trace_id" \
      "$price_span" \
      "ApplyPromotions" \
      "$(rand 15 40)" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",promo.code=\"SAVE20\""
  fi
}

generate_checkout_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local customer=$5
  
  local order_span=$(hex_id 8)
  local order_dur=$(generate_realistic_latency 150 200 10)
  
  local order_error=0
  should_have_error 5 "$env" && order_error=1
  
  send_span \
    "order-service" \
    "$trace_id" \
    "$parent" \
    "CreateOrder" \
    "$order_dur" \
    "$order_error" \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"CreateOrder\",order.total=\"$(rand 50 5000)\",order.currency=\"USD\""
  
  if [[ $order_error -eq 0 ]]; then
    send_span \
      "postgres-primary" \
      "$trace_id" \
      "$order_span" \
      "INSERT INTO orders VALUES ($1,$2,$3)" \
      "$(rand 25 70)" \
      0 \
      "db.system=\"postgresql\",db.operation=\"INSERT\",db.sql.table=\"orders\""
    
    local fraud_span=$(hex_id 8)
    send_span \
      "fraud-detection" \
      "$trace_id" \
      "$order_span" \
      "AnalyzeTransaction" \
      "$(generate_realistic_latency 80 150 15)" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",fraud.score=\"$(rand 1 100)\",ml.model=\"fraud-detection-v3\""
    
    local payment_span=$(hex_id 8)
    local payment_error=0
    should_have_error 4 "$env" && payment_error=1
    
    local payment_provider="$(pick stripe-api paypal-api)"
    local payment_dur=$(generate_realistic_latency 300 500 25)
    
    send_span \
      "payment-service" \
      "$trace_id" \
      "$order_span" \
      "ProcessPayment" \
      "$payment_dur" \
      "$payment_error" \
      "env=\"$env\",cloud.region=\"$region\",rpc.method=\"ProcessPayment\",payment.provider=\"${payment_provider}\""
    
    send_span \
      "$payment_provider" \
      "$trace_id" \
      "$payment_span" \
      "POST /v1/charges" \
      "$(generate_realistic_latency 250 450 30)" \
      "$payment_error" \
      "http.method=\"POST\",net.peer.name=\"api.${payment_provider//-api/}.com\",http.status_code=\"$(generate_http_status $payment_error)\""
    
    if [[ $payment_error -eq 0 ]]; then
      local inv_span=$(hex_id 8)
      send_span \
        "inventory-service" \
        "$trace_id" \
        "$order_span" \
        "ReserveStock" \
        "$(generate_realistic_latency 50 90 8)" \
        0 \
        "env=\"$env\",cloud.region=\"$region\",rpc.method=\"ReserveStock\""
      
      send_span \
        "postgres-primary" \
        "$trace_id" \
        "$inv_span" \
        "UPDATE inventory SET reserved=reserved+$1 WHERE sku=$2" \
        "$(rand 20 60)" \
        0 \
        "db.system=\"postgresql\",db.operation=\"UPDATE\",db.sql.table=\"inventory\""
      
      if [[ $((RANDOM % 2)) -eq 0 ]]; then
        send_span \
          "$(pick kafka-broker-1 kafka-broker-2 kafka-broker-3)" \
          "$trace_id" \
          "$inv_span" \
          "PUBLISH inventory.reserved" \
          "$(rand 5 25)" \
          0 \
          "messaging.system=\"kafka\",messaging.destination=\"inventory.reserved\",messaging.partition=\"$(rand 0 5)\""
      fi
      
      local shipping_span=$(hex_id 8)
      send_span \
        "shipping-service" \
        "$trace_id" \
        "$order_span" \
        "CreateShipment" \
        "$(generate_realistic_latency 70 120 10)" \
        0 \
        "env=\"$env\",cloud.region=\"$region\",rpc.method=\"CreateShipment\",shipping.carrier=\"$(pick UPS FedEx DHL USPS)\""
      
      send_span \
        "postgres-primary" \
        "$trace_id" \
        "$shipping_span" \
        "INSERT INTO shipments (order_id,carrier,tracking) VALUES ($1,$2,$3)" \
        "$(rand 18 55)" \
        0 \
        "db.system=\"postgresql\",db.operation=\"INSERT\",db.sql.table=\"shipments\""
      
      local notif_method=$((RANDOM % 3))
      local notif_span=$(hex_id 8)
      
      if [[ $notif_method -eq 0 ]]; then
        send_span \
          "email-service" \
          "$trace_id" \
          "$order_span" \
          "SendOrderConfirmation" \
          "$(generate_realistic_latency 60 150 12)" \
          0 \
          "env=\"$env\",cloud.region=\"$region\",email.template=\"order-confirmation\""
        
        send_span \
          "sendgrid-api" \
          "$trace_id" \
          "$notif_span" \
          "POST /v3/mail/send" \
          "$(generate_realistic_latency 100 350 20)" \
          0 \
          "http.method=\"POST\",net.peer.name=\"api.sendgrid.com\""
      elif [[ $notif_method -eq 1 ]]; then
        send_span \
          "sms-service" \
          "$trace_id" \
          "$order_span" \
          "SendSMS" \
          "$(generate_realistic_latency 80 200 15)" \
          0 \
          "env=\"$env\",cloud.region=\"$region\",sms.destination=\"+1555***$(rand 1000 9999)\""
        
        send_span \
          "twilio-api" \
          "$trace_id" \
          "$notif_span" \
          "POST /2010-04-01/Accounts/{sid}/Messages" \
          "$(generate_realistic_latency 120 400 25)" \
          0 \
          "http.method=\"POST\",net.peer.name=\"api.twilio.com\""
      else
        send_span \
          "notification-service" \
          "$trace_id" \
          "$order_span" \
          "SendPushNotification" \
          "$(rand 40 100)" \
          0 \
          "env=\"$env\",cloud.region=\"$region\",push.platform=\"$(pick ios android web)\""
      fi
      
      send_span \
        "$(pick kafka-broker-1 kafka-broker-2)" \
        "$trace_id" \
        "$order_span" \
        "PUBLISH order.created" \
        "$(rand 8 35)" \
        0 \
        "messaging.system=\"kafka\",messaging.destination=\"order.created\",messaging.partition=\"$(rand 0 9)\""
      
      if [[ $((RANDOM % 3)) -eq 0 ]]; then
        local analytics_span=$(hex_id 8)
        send_span \
          "analytics-service" \
          "$trace_id" \
          "$order_span" \
          "TrackEvent" \
          "$(rand 15 50)" \
          0 \
          "env=\"$env\",cloud.region=\"$region\",event.type=\"purchase\",event.value=\"$(rand 50 5000)\""
        
        local analytics_dest="$(pick segment-api amplitude-api aws-lambda)"
        send_span \
          "$analytics_dest" \
          "$trace_id" \
          "$analytics_span" \
          "POST /track" \
          "$(rand 25 90)" \
          0 \
          "http.method=\"POST\",net.peer.name=\"${analytics_dest}\""
      fi
      
      if [[ "$customer" == *"enterprise"* ]] && [[ $((RANDOM % 2)) -eq 0 ]]; then
        local tax_span=$(hex_id 8)
        send_span \
          "tax-service" \
          "$trace_id" \
          "$order_span" \
          "CalculateTax" \
          "$(rand 30 80)" \
          0 \
          "env=\"$env\",tax.jurisdiction=\"$(pick CA NY TX FL)\""
      fi
    fi
  fi
}

generate_orders_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  
  local orders_span=$(hex_id 8)
  send_span \
    "order-service" \
    "$trace_id" \
    "$parent" \
    "GetOrders" \
    "$(generate_realistic_latency 45 70 7)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"GetOrders\""
  
  send_span \
    "$(pick postgres-replica-1 postgres-replica-2)" \
    "$trace_id" \
    "$orders_span" \
    "SELECT * FROM orders WHERE user_id=$1 ORDER BY created_at DESC LIMIT 20" \
    "$(rand 25 80)" \
    0 \
    "db.system=\"postgresql\",db.operation=\"SELECT\",db.sql.table=\"orders\",db.rows_returned=\"$(rand 1 20)\""
}

generate_reviews_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  
  local review_span=$(hex_id 8)
  send_span \
    "review-service" \
    "$trace_id" \
    "$parent" \
    "CreateReview" \
    "$(generate_realistic_latency 60 100 8)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"CreateReview\",review.rating=\"$(rand 1 5)\""
  
  send_span \
    "$(pick mongodb-primary postgres-primary)" \
    "$trace_id" \
    "$review_span" \
    "INSERT review" \
    "$(rand 20 60)" \
    0 \
    "db.operation=\"INSERT\",db.sql.table=\"reviews\""
  
  if [[ $((RANDOM % 3)) -eq 0 ]]; then
    local sentiment_span=$(hex_id 8)
    send_span \
      "analytics-service" \
      "$trace_id" \
      "$review_span" \
      "AnalyzeSentiment" \
      "$(generate_realistic_latency 100 250 20)" \
      0 \
      "env=\"$env\",ml.model=\"sentiment-analysis-v1\",sentiment.score=\"$(rand -100 100)\""
  fi
}

generate_wishlist_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  
  local wishlist_span=$(hex_id 8)
  send_span \
    "wishlist-service" \
    "$trace_id" \
    "$parent" \
    "AddToWishlist" \
    "$(rand 20 50)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"AddToWishlist\""
  
  send_span \
    "redis-cache" \
    "$trace_id" \
    "$wishlist_span" \
    "SADD wishlist:user:${trace_id:0:6} product:${trace_id:6:6}" \
    "$(rand 2 8)" \
    0 \
    "db.system=\"redis\",db.operation=\"SADD\""
}

generate_recommendation_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  
  local rec_span=$(hex_id 8)
  send_span \
    "recommendation-service" \
    "$trace_id" \
    "$parent" \
    "GetPersonalizedRecommendations" \
    "$(generate_realistic_latency 150 300 20)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"GetPersonalizedRecommendations\",ml.model=\"transformer-v4\""
  
  send_span \
    "redis-cache" \
    "$trace_id" \
    "$rec_span" \
    "GET user:embeddings:${trace_id:0:8}" \
    "$(rand 3 12)" \
    0 \
    "db.system=\"redis\",db.operation=\"GET\",cache.hit=\"$(pick true false)\""
}

generate_graphql_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  
  local resolvers=("User" "Product" "Order" "Cart" "Review")
  local num_resolvers=$((RANDOM % 4 + 2))
  
  for ((i=0; i<num_resolvers; i++)); do
    local resolver="${resolvers[$((RANDOM % ${#resolvers[@]}))]}"
    local resolver_span=$(hex_id 8)
    
    send_span \
      "graphql-gateway" \
      "$trace_id" \
      "$parent" \
      "resolve:${resolver}" \
      "$(rand 20 80)" \
      0 \
      "env=\"$env\",graphql.field=\"${resolver}\",graphql.operation=\"query\""
  done
}

generate_profile_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  
  local profile_span=$(hex_id 8)
  send_span \
    "profile-service" \
    "$trace_id" \
    "$parent" \
    "GetProfile" \
    "$(generate_realistic_latency 40 70 6)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"GetProfile\""
  
  send_span \
    "$(pick postgres-replica-1 postgres-replica-2)" \
    "$trace_id" \
    "$profile_span" \
    "SELECT * FROM user_profiles WHERE id=$1" \
    "$(rand 18 50)" \
    0 \
    "db.system=\"postgresql\",db.operation=\"SELECT\",db.sql.table=\"user_profiles\""
  
  if [[ $((RANDOM % 3)) -eq 0 ]]; then
    send_span \
      "$(pick s3-storage gcs-storage)" \
      "$trace_id" \
      "$profile_span" \
      "GET /avatars/${trace_id:0:8}.jpg" \
      "$(generate_realistic_latency 50 150 15)" \
      0 \
      "aws.service=\"s3\",aws.operation=\"GetObject\",object.size=\"$(rand 10 500)kb\""
  fi
  
  if [[ $((RANDOM % 2)) -eq 0 ]]; then
    send_span \
      "cloudflare-cdn" \
      "$trace_id" \
      "$profile_span" \
      "GET /static/profile-assets" \
      "$(rand 8 35)" \
      0 \
      "http.url=\"cdn.example.com\",cdn.cache=\"$(pick HIT MISS)\""
  fi
}

generate_generic_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  
  local service="$(pick "${BUSINESS_SERVICES[@]}")"
  local method="$(pick GetData UpdateData ProcessRequest HandleEvent)"
  
  local span_id=$(hex_id 8)
  send_span \
    "$service" \
    "$trace_id" \
    "$parent" \
    "$method" \
    "$(generate_realistic_latency 40 100 10)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"$method\""
  
  if [[ $((RANDOM % 2)) -eq 0 ]]; then
    local db="$(pick "${DATA_STORES[@]}")"
    send_span \
      "$db" \
      "$trace_id" \
      "$span_id" \
      "$(pick SELECT INSERT UPDATE DELETE)" \
      "$(rand 15 70)" \
      0 \
      "db.operation=\"query\""
  fi
}

echo "========================================"
echo "Trace Generator for OpenTelemetry"
echo "========================================"
echo "Endpoint: $ENDPOINT"
echo "Count: $COUNT traces"
echo "Delay: ${DELAY}s between traces"
echo "========================================"
echo ""

TRAFFIC_PATTERN=$((RANDOM % 5))

for ((i=1;i<=COUNT;i++)); do
  
  if [[ $TRAFFIC_PATTERN -eq 0 ]] && [[ $((i % 50)) -eq 0 ]]; then
    echo ""
    echo "🔥 TRAFFIC SPIKE - Burst mode activated!"
    for ((burst=0;burst<10;burst++)); do
      TRACE_ID=$(hex_id 16)
      REGION="$(pick "${REGIONS[@]}")"
      ENV="$(pick "${ENVS[@]}")"
      CUSTOMER="$(pick "${CUSTOMERS[@]}")"
      generate_user_flow "$TRACE_ID" "$REGION" "$ENV" "$CUSTOMER" &
    done
    wait
    echo "🔥 Spike complete"
  fi
  
  echo ""
  echo "=== Trace $i/$COUNT ==="
  
  TRACE_ID=$(hex_id 16)
  REGION="$(pick "${REGIONS[@]}")"
  ENV="$(pick "${ENVS[@]}")"
  CUSTOMER="$(pick "${CUSTOMERS[@]}")"
  
  generate_user_flow "$TRACE_ID" "$REGION" "$ENV" "$CUSTOMER"
  
  if [[ $((RANDOM % 100)) -lt 5 ]]; then
    micro_delay=$(echo "scale=3; $DELAY * $(rand 5 20) / 10" | bc -l 2>/dev/null || echo "$DELAY")
    safe_sleep "$micro_delay"
  else
    safe_sleep "$DELAY"
  fi
  
  if [[ $((i % 100)) -eq 0 ]]; then
    echo ""
    echo "📊 Progress: $i/$COUNT traces completed ($(( i * 100 / COUNT ))%)"
  fi
done

echo ""
echo "========================================"
echo "✅ Complete: $COUNT traces generated"
echo "========================================"