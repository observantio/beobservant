#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="${1:-localhost:4318}"
DURATION_MINUTES="${2:-60}"
DELAY="${3:-0.05}"
RETRIES=3
INSECURE=true

if [ "$INSECURE" = true ]; then
  INSECURE_FLAG=(--otlp-insecure)
else
  INSECURE_FLAG=()
fi

_required=(docker sleep date awk)
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

TELEMETRYGEN_IMG="ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest"
DOCKER_RUN="docker run --rm --network host"

SERVICES=(
  "api-gateway" "graphql-gateway" "grpc-gateway" "websocket-gateway"
  "auth-service" "user-service" "session-service" "profile-service" "permissions-service"
  "payment-service" "order-service" "cart-service" "checkout-service"
  "inventory-service" "warehouse-service" "fulfillment-service" "shipping-service"
  "catalog-service" "search-service" "recommendation-service" "pricing-service"
  "notification-service" "email-service" "sms-service" "push-service"
  "analytics-service" "reporting-service" "fraud-detection" "tax-service"
  "review-service" "wishlist-service" "loyalty-service" "promotion-service"
  "postgres-primary" "postgres-replica" "redis-cache" "redis-session"
  "mongodb-primary" "elasticsearch" "kafka-broker" "rabbitmq"
)

REGIONS=("us-east-1" "us-west-2" "us-central-1" "eu-west-1" "eu-central-1" "ap-southeast-1" "ap-southeast-2" "ap-northeast-1")
ENVS=("prod" "prod" "prod" "prod" "staging" "staging" "dev")
CUSTOMERS=("acme-corp" "globex" "initech" "umbrella-corp" "wayne-enterprises" "free-tier" "premium-tier" "enterprise-tier")
USERS=("usr_a7f2" "usr_b3k9" "usr_c1m4" "usr_d8n2" "usr_e5p7" "usr_f9q1" "usr_g2r6" "usr_h4s3" "usr_i7t8" "usr_j1u5" "usr_k3w9" "usr_l8x2" "usr_m5y4" "usr_n1z7")

declare -A SERVICE_MESSAGES=(
  [api-gateway]="Request routed to upstream service|Rate limit applied to client|Circuit breaker opened for downstream|Request validation completed|Gateway timeout detected|Health check passed|SSL/TLS handshake successful|WebSocket connection upgraded|Load balancer target healthy|Request queue processing|Authentication middleware passed|CORS preflight handled|API version negotiation completed|Request ID generated|Compression applied to response|Cache lookup performed|Reverse proxy forwarding request|Service mesh sidecar injected|Request retried with backoff|Load shedding activated"
  [graphql-gateway]="GraphQL query parsed successfully|Resolver execution completed|Query complexity analyzed|Schema introspection requested|Subscription established|Batched query processed|DataLoader cache hit|Field resolver invoked|Mutation validation passed|Query cost calculated|Persisted query executed|Apollo federation resolved|N+1 query detected|Fragment spread processed|Directive applied|Type validation successful|Schema stitching completed"
  [auth-service]="User authentication successful|JWT token issued and signed|Refresh token rotated|Login attempt from new device detected|MFA challenge sent via SMS|Session created with TTL|Password reset email dispatched|Account locked after failed attempts|OAuth2 authorization code issued|SAML assertion validated|API key authenticated|Token introspection completed|SSO session established|Biometric verification passed|Device fingerprint recorded|Login anomaly detected|Password hash verified|OAuth callback processed|Token revocation requested|Identity federation completed"
  [user-service]="User profile retrieved from cache|Account created with email verification|Profile photo uploaded to S3|Preferences updated successfully|Email verification link sent|Account deletion queued|Password strength validated|Two-factor authentication enabled|Session invalidated across devices|GDPR data export initiated|Privacy settings synchronized|Subscription tier upgraded|Profile merge operation completed|Account suspension applied|Username availability confirmed|User search query executed|Batch user import processed|Profile audit logged|Contact info updated|Account reactivation approved"
  [payment-service]="Payment transaction authorized|Credit card tokenized securely|3DS authentication challenge initiated|Payment captured successfully|Refund processed to original method|Chargeback notification received|Fraud score calculated|Payment method saved to vault|Webhook retry scheduled for merchant|Settlement batch submitted|Payout initiated to bank account|Payment declined by issuer|Card verification value validated|Currency conversion applied|Transaction risk assessment passed|Recurring billing executed|Payment reconciliation completed|Merchant fee calculated|Partial payment authorized|ACH transfer initiated"
  [order-service]="Order created and assigned ID|Order status transitioned to processing|Payment verification completed|Shipping label generated via carrier API|Order cancelled per customer request|Partial order fulfillment initiated|Order priority escalated to express|Delivery confirmation webhook received|Return authorization created|Order split across multiple warehouses|Tax calculation service invoked|Address validation via geocoding|Bundle discount rules applied|Order export to ERP queued|Backorder notification sent|Order audit trail logged|Fulfillment SLA deadline calculated|Custom order notes saved|Gift wrapping option applied|Order tracking link generated"
  [inventory-service]="Stock level synchronized with warehouse|Item reserved for pending order|Low stock alert threshold triggered|SKU replenishment order created|Inventory audit reconciliation passed|Dead stock identified for clearance|Stock discrepancy investigated|Reorder point calculation updated|Backorder queue processed|SKU lifecycle status updated|Location transfer between warehouses|Batch expiration date tracked|Physical count scheduled|Cross-dock shipment recorded|Safety stock threshold maintained|Inventory turnover ratio calculated|Lot tracking enabled|Serial number registered|Stock allocation optimized|Cycle count variance recorded"
  [catalog-service]="Product catalog refreshed from upstream|SKU metadata indexed in search|Product image CDN URL generated|Category hierarchy updated|Product variant created|Price point effective date set|Product description enriched with AI|Inventory availability synced|Product bundle configured|Related products algorithm executed|Seasonal catalog activated|Product attribute validation passed|Bulk product import completed|Product feed generated for partners|Catalog export scheduled|Product rating aggregated|Product taxonomy updated|Cross-sell rules applied|Product deprecation marked|Catalog cache invalidated"
  [search-service]="Search query executed on index|Search results ranked by relevance|Faceted search filters applied|Autocomplete suggestions generated|Search index rebuilt incrementally|Typo tolerance correction applied|Synonym expansion activated|Search analytics event tracked|Popular searches aggregated|Zero-results query logged|Search personalization applied|Geographic search radius calculated|Product availability filtered|Boost rules applied to results|Search click-through tracked|A/B test variant assigned|Search cache warmed|Spell check suggestion offered|Multi-language search processed|Search performance optimized"
  [recommendation-service]="Collaborative filtering model executed|User preferences vector computed|Product similarity score calculated|Real-time personalization applied|Click stream data processed|Recommendation cache refreshed|A/B test cohort assigned|Conversion attribution tracked|Cold start problem handled|Trending items surfaced|Cross-sell opportunity identified|Recommendation explanation generated|Diversity algorithm applied|Contextual bandits updated|Session-based recommendations served|Hybrid recommendation strategy used|Fallback recommendations provided|Recommendation feedback collected|Model retrained with new data|Recommendation performance measured"
  [notification-service]="Email notification queued for delivery|SMS delivery confirmation received|Push notification sent to device|Webhook POST request succeeded|Email bounce handled gracefully|Notification throttling applied|Template rendered with user data|Batch notification processing started|Unsubscribe preference honored|Delivery retry attempt exhausted|Provider failover triggered|Channel preference respected|Notification deduplication applied|Delivery status webhook processed|Multi-channel notification orchestrated|Notification priority queue managed|Transactional email bypass spam filter|Notification analytics tracked|Quiet hours respected|Notification A/B test variant sent"
  [email-service]="Email composed from template|Recipient address validated|Email queued in send buffer|SMTP connection established|SPF/DKIM/DMARC validated|Email delivered successfully|Bounce notification processed|Email open tracking pixel loaded|Link click tracked in email|Attachment size validated|Email suppression list checked|Email personalization applied|HTML sanitization completed|Plain text fallback generated|Email preview rendered|Unsubscribe link appended|Email relay accepted message|Spam score calculated|Email rate limit enforced|Email archive policy applied"
  [analytics-service]="Event ingested into pipeline|Session tracking cookie set|Funnel conversion step recorded|Custom dimension captured|Real-time dashboard metric updated|Aggregation job completed on schedule|User cohort membership computed|A/B test conversion tracked|Data retention policy enforced|Attribution model applied|User journey path analyzed|Anomaly detection algorithm triggered|Report generation queued|Data export to warehouse scheduled|Query result cached|Sampling rate dynamically adjusted|Event schema validated|Metric threshold alert evaluated|Cross-domain tracking reconciled|Revenue attribution calculated"
  [fraud-detection]="Transaction risk score calculated|Behavioral biometric analyzed|Device fingerprint matched|Velocity check rule triggered|Geolocation anomaly detected|Machine learning model inference completed|Fraud pattern match identified|Whitelist verification passed|Blacklist screening performed|Manual review queue item created|Chargeback prediction scored|Account takeover signal detected|Synthetic identity suspected|Rules engine evaluation finished|Fraud case investigation opened|Risk threshold exceeded|Transaction hold applied|3D Secure challenge recommended|Trusted device recognized|Fraud alert notification sent"
  [shipping-service]="Carrier rate shopping completed|Shipping label created successfully|Tracking number generated|Package weight verified|Delivery estimate calculated|Carrier pickup scheduled|International customs form generated|Package dimensioning completed|Shipping zone classification applied|Signature requirement configured|Shipment insured for declared value|Package consolidated for efficiency|Return label preemptively generated|Carrier integration webhook received|Delivery exception notification sent|Proof of delivery captured|Multi-package shipment grouped|Freight quote obtained|Drop-ship order routed|Last-mile delivery optimized"
  [postgres-primary]="Connection established from pool|Transaction committed successfully|Write-ahead log synchronized|Query execution plan cached|Checkpoint operation completed|Index scan performed efficiently|Foreign key constraint validated|Trigger function executed|Row-level lock acquired|Dead tuple cleanup scheduled|Vacuum operation started|Replication slot lag monitored|Prepared statement executed|Bulk insert batch processed|Materialized view refreshed|Extension loaded into database|Table statistics updated|Connection returned to pool|Slow query logged for analysis|Database backup initiated"
  [redis-cache]="Cache key retrieved successfully|Cache hit on user session|Cache miss triggered upstream query|Key expiration TTL set|Cache invalidation pattern matched|Eviction policy LRU applied|Pub/sub message published|Sorted set member added|Hash field updated|Cache warming job completed|Pipeline batch executed|Lua script evaluated|Keyspace notification triggered|Replica synchronization completed|Memory usage threshold monitored|Persistence snapshot saved|Cache cluster resharding started|Scan cursor iteration continued|Bloom filter membership checked|Cache penetration detected"
  [kafka-broker]="Message produced to topic partition|Consumer group offset committed|Topic partition leader elected|Message batch compressed|Replication acknowledgment received|Consumer lag within threshold|Topic retention policy applied|Message timestamp indexed|Producer idempotence ensured|Consumer rebalance triggered|Log segment rolled over|Topic compaction completed|Offset reset to earliest|Message key serialized|Schema registry validation passed|Exactly-once semantics guaranteed|Dead letter queue message routed|Consumer group metadata updated|Topic partition expanded|Throughput quota enforced"
  [loyalty-service]="Loyalty points accrued|Reward tier threshold reached|Points redemption processed|Bonus points promotion applied|Points expiration reminder sent|Loyalty program enrollment completed|Referral bonus awarded|Points balance inquiry served|Tier upgrade notification sent|Points transfer between accounts|Loyalty analytics aggregated|Points reversal for return|Anniversary bonus credited|Partner points sync completed|Gamification badge unlocked|Points earning rate calculated|Loyalty status downgrade prevented|VIP early access granted|Points earning history audited|Loyalty program rules updated"
  [tax-service]="Sales tax calculated for jurisdiction|Tax nexus determination completed|VAT validation performed|Tax exemption certificate verified|Tax rate lookup from database|Tax engine API integration succeeded|Multi-jurisdiction tax apportioned|Product tax category classified|Tax reporting data aggregated|Tax calculation cached|Reverse charge mechanism applied|Tax holiday rules respected|Withholding tax computed|Tax filing report generated|Tax audit trail preserved|Use tax liability calculated|Tax jurisdiction override applied|Customs duty estimated|Tax compliance check passed|Tax rate change effective date applied"
)

declare -A ERROR_MESSAGES=(
  [api-gateway]="Upstream service connection refused|Request timeout exceeded 30 seconds|Invalid API key format rejected|CORS preflight check failed|Maximum request payload size exceeded|SSL certificate validation error|Service mesh routing conflict detected|Circuit breaker open - rejecting requests|WebSocket upgrade failed|Rate limiter Redis unavailable|Authentication token malformed|Request header too large|Downstream returned 503 Service Unavailable|API quota exceeded for client|Load balancer health check failing|Gateway configuration reload failed|TLS handshake timeout|Proxy buffer overflow|Invalid content-type header|Connection pool exhausted"
  [auth-service]="Database connection pool completely exhausted|Redis session store unreachable|LDAP directory server timeout|JWT token signature verification failed|Session state corrupted in store|Encryption key rotation failure|OAuth provider endpoint unreachable|TLS certificate expired for SAML|Password hash verification timeout|MFA token validation service down|Biometric service API unavailable|SSO federation trust broken|Token blacklist lookup failed|Device fingerprint service crashed|Identity provider SAML parse error|OAuth refresh token invalid|Session cookie decryption failed|Password policy validation crashed|Account recovery email send failed|Rate limiting cache unreachable"
  [payment-service]="Payment gateway connection timeout|Duplicate transaction ID detected|PCI compliance validation failed|Tokenization service unavailable|Merchant account suspended by provider|Card number validation regex failed|Settlement batch processing error|3DS challenge service down|Webhook signature verification failed|Payment provider returned 500 error|Currency conversion API unavailable|Fraud detection timeout exceeded|Refund amount exceeds original charge|Card declined - insufficient funds|Chargeback webhook parsing error|ACH routing number invalid|Payment vault encryption failed|Idempotency key collision detected|Transaction log write failed|Payment reconciliation mismatch"
  [order-service]="Inventory reservation service timeout|Shipping carrier API completely down|Tax calculation service HTTP 500|Database write operation timeout|Order state machine invalid transition|Address geocoding API rate limited|Payment authorization token expired|Fulfillment center capacity exceeded|Order export ERP integration failed|Database deadlock on order insert|Backorder queue processing stalled|Order validation rules engine crashed|Warehouse allocation algorithm failed|Order audit log write failed|Shipping label generation timeout|Order cancellation webhook failed|Bundle discount calculation error|Order priority queue overflow|Customer notification dispatch failed|Order search index update failed"
  [notification-service]="Email provider API outage detected|SMS gateway authentication failed|Push notification provider unreachable|Template rendering engine crashed|Recipient blacklist Redis unavailable|Message queue consumer lag critical|Webhook delivery timeout exceeded|Rate limit quota completely exhausted|Template variables missing|Notification database write failed|Channel preference lookup timeout|Email bounce processing failed|Delivery status callback parse error|Multi-channel orchestration deadlock|Unsubscribe service unavailable|Notification deduplication cache down|Provider failover all backends down|Attachment storage upload failed|Notification analytics write timeout|Quiet hours calculation error"
  [inventory-service]="Stock count critical mismatch detected|Database replication lag exceeded 10s|Warehouse integration API down|Concurrent modification deadlock|SKU not found in master catalog|Barcode scanning validation error|ERP sync batch job failed|Inventory reservation conflict|Safety stock threshold breach|Location transfer validation failed|Stock audit reconciliation error|Cycle count variance exceeds tolerance|Lot tracking data corrupted|Serial number duplicate detected|Inventory allocation algorithm crashed|Cross-dock validation failed|Replenishment order API timeout|Stock level cache inconsistent|Warehouse capacity calculation error|Inventory turnover query timeout"
  [analytics-service]="ClickHouse cluster unreachable|Data pipeline completely stalled|Aggregation query execution killed|Kafka consumer lag critical threshold|S3 data lake permission denied|Query result set exceeds memory limit|Schema evolution migration failed|Event ingestion buffer overflow|Attribution model computation timeout|Cohort analysis query deadlock|Report generation memory exhausted|Data export S3 upload failed|Real-time dashboard WebSocket dropped|Metric calculation division by zero|Sampling algorithm crashed|Cross-domain tracker reconciliation failed|Data retention policy delete failed|Query optimizer timeout exceeded|Event schema validation rejected|Anomaly detection model inference error"
  [fraud-detection]="Machine learning model inference timeout|Feature extraction service crashed|Risk scoring Redis cache unavailable|Behavioral biometrics analysis failed|Device fingerprint database down|Rules engine evaluation timeout|Velocity check database deadlock|Geolocation API rate limit hit|Whitelist/blacklist lookup failed|Manual review queue overflow|Chargeback prediction model error|Account takeover detection crashed|Synthetic identity check timeout|Transaction hold database write failed|3DS recommendation engine down|Trusted device cache inconsistent|Fraud pattern database corrupted|Investigation workflow service down|Alert notification dispatch failed|Risk threshold configuration invalid"
  [postgres-primary]="Deadlock detected - transaction aborted|Connection pool max connections reached|Disk full - unable to extend relation|Replication slot lag exceeds 1GB|Query execution timeout after 60s|Checkpoint timeout exceeded|Lock wait timeout on table|WAL segment corruption detected|Foreign key constraint violation|Out of shared memory buffers|Transaction ID wraparound imminent|Index corruption detected on scan|Prepared statement cache overflow|Autovacuum worker crashed|Extension initialization failed|Backup process terminated unexpectedly|Statistics collector process died|Connection refused - too many clients|Trigger function runtime error|Materialized view refresh deadlock"
  [redis-cache]="Out of memory - eviction policy failed|Replication master connection lost|Persistence RDB save failed|AOF file corruption detected|Cluster node unreachable timeout|Keyspace notification publish failed|Lua script execution timeout|Memory fragmentation ratio critical|Slow log threshold exceeded|Client output buffer overflow|Pub/sub pattern subscription limit|Cluster resharding failed|Sentinel failover triggered but failed|Background save fork() failed|Command processing timeout|Connection refused max clients|Hash slot migration error|Replica sync full resync required|Memory usage warning threshold|Cluster state inconsistent"
  [kafka-broker]="Broker not available for partition|Replication factor not satisfied|Offset commit timeout expired|Consumer group rebalance failed|Producer request timeout|Topic partition leader not found|Message batch compression failed|Log segment corruption detected|Disk write queue overflow|Zookeeper session timeout|Schema registry validation failed|Consumer fetch request timeout|Producer idempotence sequence error|Broker out of disk space|Network thread pool saturated|Request handler thread starvation|Controller election failed|Log retention deletion error|Replication quota exceeded|Cluster metadata inconsistent"
)

declare -A WARN_MESSAGES=(
  [api-gateway]="Response time exceeds SLA threshold|Client retry storm pattern detected|Request header size approaching limit|Deprecated API version still in use|Legacy TLS 1.1 connection detected|Upstream service latency spike|Cache hit rate below 70% threshold|Connection pool utilization high|Rate limit soft threshold reached|Gateway memory usage at 80%|Slow response time from backend|Request queue depth growing|Circuit breaker half-open state|API version sunset date approaching|Client certificate expires soon|Load balancer target unhealthy intermittently|Gateway configuration drift detected"
  [auth-service]="Password strength below policy recommendation|Multiple failed login attempts from IP|Access token nearing expiration|Concurrent session count above baseline|Refresh token reuse pattern detected|Legacy client version attempting auth|Login from geographically unusual location|MFA enrollment rate declining|Session duration unusually long|Password unchanged for 180+ days|OAuth scope creep detected|API key rotation overdue|Biometric authentication failure rate up|Device trust score declining|Account dormancy period extended|Login velocity unusual for user|Password reset frequency elevated"
  [payment-service]="Transaction amount unusually high for account|Payment card expiration date approaching|Payment processing latency elevated|Retry attempt for previously failed payment|Partial authorization received from issuer|Currency exchange rate fluctuation detected|Settlement processing delayed|Fraud score approaching threshold|Payment method verification pending|Chargeback ratio increasing|Merchant fee calculation discrepancy|Payment provider response time slow|Tokenization cache miss rate high|3DS challenge completion rate low|Refund request volume spike|Payment reconciliation gap detected"
  [order-service]="Order processing time approaching SLA limit|Order cancellation rate above baseline|Shipping zone capacity utilization high|Incomplete delivery address detected|Inventory allocation delay increasing|Order volume spike detected|Fulfillment SLA deadline at risk|Backorder queue length growing|Order priority escalation frequency up|Custom order complexity high|Order split frequency increasing|Return rate trending upward|Order export queue backlog|Tax calculation retries elevated|Address validation failure rate up|Order modification frequency unusual"
  [inventory-service]="Stock level below safety threshold|Slow-moving inventory accumulating|Warehouse capacity utilization at 85%|SKU synchronization latency elevated|Inventory variance trending upward|Reorder point approaching for multiple SKUs|Stock transfer processing delayed|Dead stock value increasing|Replenishment lead time extending|Cycle count frequency below target|Location transfer errors increasing|Batch expiration dates approaching|Stockout risk probability elevated|Inventory turnover ratio declining|SKU lifecycle transition overdue|Physical count scheduling gap"
  [notification-service]="Email open rate declining below baseline|Notification delivery latency increasing|Email bounce rate elevated above 3%|Provider failover frequency high|Template version deprecated|Retry queue depth growing|SMS delivery confirmation delayed|Push notification opt-out rate rising|Webhook timeout retry rate high|Notification queue memory usage high|Channel preference update lag|Unsubscribe rate trending upward|Attachment size warnings increasing|Delivery status callback delays|Email spam score borderline|Provider rate limit approaching|Multi-channel send coordination lag"
  [analytics-service]="Query execution time exceeds threshold|Event processing lag increasing|Data warehouse storage at 80% capacity|Sampling rate automatically increased|Cache eviction rate elevated|Dashboard load time degraded|Data pipeline throughput declining|Real-time metric freshness delayed|Attribution window edge cases rising|Cohort size calculation timeout risk|Report generation queue backlog|Data export request volume high|Cross-domain tracker sync lag|Event schema version mismatch warnings|Aggregation job duration extending|Anomaly detection false positive rate up"
  [fraud-detection]="Transaction risk score approaching review threshold|Behavioral analysis confidence declining|Device fingerprint match ambiguous|Velocity check threshold near breach|Geolocation data quality degraded|Machine learning model drift detected|Rules engine performance degrading|Whitelist cache staleness increasing|Blacklist synchronization lag|Manual review queue depth growing|Chargeback prediction uncertainty high|Account takeover signal weak|Investigation workflow SLA at risk|Risk scoring latency elevated|3DS challenge friction increasing|Trusted device list outdated|Fraud pattern database update lag"
  [postgres-primary]="Query execution plan suboptimal|Connection pool nearing max capacity|Table bloat ratio increasing|Replication lag approaching threshold|Checkpoint write duration extended|Index fragmentation detected|Long-running transaction active|Vacuum operation overdue|Shared buffer hit ratio declining|Lock contention increasing|Statistics stale for query planning|Autovacuum worker falling behind|Extension version update available|Slow query log entry count rising|Connection churn rate elevated|Transaction ID consumption accelerating|Disk I/O utilization high"
  [redis-cache]="Memory usage approaching max capacity|Cache eviction rate increasing|Replication lag to replica growing|Keyspace notification delay detected|Client connection count elevated|Command processing latency spike|Persistence save duration extended|Memory fragmentation ratio high|Slow log entries accumulating|Pub/sub channel subscriber churn|Cluster node gossip latency|Key expiration backlog growing|AOF rewrite overdue|Client output buffer approaching limit|Cache hit ratio declining|Hash slot distribution skewed"
  [kafka-broker]="Consumer group lag increasing|Produce request latency elevated|Fetch request queue depth growing|Replication under-replicated partitions|Log segment roll frequency high|Disk usage approaching threshold|Network thread utilization high|Request handler queue backlog|Controller action queue depth|Zookeeper session latency spike|Message batch size below optimal|Consumer rebalance frequency elevated|Producer retry rate increasing|Broker replica fetch lag|Topic partition count high|Log retention cleanup lag|Cluster load imbalance detected"
)

HTTP_CODES=(200 200 200 200 201 201 202 204 200 200 200 304 400 401 403 404 409 422 429 500 502 503 504)

generate_trace_id() {
  printf '%016x%016x' $((RANDOM * RANDOM)) $((RANDOM * RANDOM))
}

get_message() {
  local service=$1
  local level=$2
  local messages_var=""
  
  case "$level" in
    ERROR)
      messages_var="ERROR_MESSAGES[$service]"
      ;;
    WARN)
      messages_var="WARN_MESSAGES[$service]"
      ;;
    *)
      messages_var="SERVICE_MESSAGES[$service]"
      ;;
  esac
  
  if [[ -n "${!messages_var:-}" ]]; then
    IFS='|' read -ra MSG_ARRAY <<< "${!messages_var}"
    echo "${MSG_ARRAY[$((RANDOM % ${#MSG_ARRAY[@]}))]}"
  else
    echo "Service operation completed"
  fi
}

get_log_level() {
  local env=$1
  local rand=$((RANDOM % 100))
  
  if [[ "$env" == "dev" ]]; then
    if [ $rand -lt 15 ]; then echo "ERROR"
    elif [ $rand -lt 30 ]; then echo "WARN"
    elif [ $rand -lt 50 ]; then echo "DEBUG"
    else echo "INFO"; fi
  elif [[ "$env" == "staging" ]]; then
    if [ $rand -lt 8 ]; then echo "ERROR"
    elif [ $rand -lt 20 ]; then echo "WARN"
    elif [ $rand -lt 35 ]; then echo "DEBUG"
    else echo "INFO"; fi
  else
    if [ $rand -lt 3 ]; then echo "ERROR"
    elif [ $rand -lt 12 ]; then echo "WARN"
    elif [ $rand -lt 22 ]; then echo "DEBUG"
    else echo "INFO"; fi
  fi
}

generate_response_time() {
  local level=$1
  local base=$((RANDOM % 2000 + 50))
  
  if [[ "$level" == "ERROR" ]]; then
    base=$((base * $(( (RANDOM % 5) + 2 ))))
  elif [[ "$level" == "WARN" ]]; then
    if [[ $((RANDOM % 3)) -eq 0 ]]; then
      base=$((base * 2))
    fi
  fi
  
  if [[ $((RANDOM % 100)) -lt 5 ]]; then
    base=$((base * $(( (RANDOM % 10) + 3 ))))
  fi
  
  echo "$base"
}

pick() {
  local arr=("$@")
  echo "${arr[$((RANDOM % ${#arr[@]}))]}"
}

END_TIME=$((SECONDS + DURATION_MINUTES * 60))
COUNT=0
ERROR_COUNT=0
WARN_COUNT=0
DEBUG_COUNT=0
INFO_COUNT=0

TRACE_IDS=()

echo "========================================"
echo "OpenTelemetry Log Generator"
echo "========================================"
echo "Endpoint: $ENDPOINT"
echo "Duration: ${DURATION_MINUTES} minutes"
echo "Delay: ${DELAY}s between logs"
echo "========================================"
echo "Press Ctrl+C to stop"
echo ""

BURST_MODE=$((RANDOM % 3))

while [ "$SECONDS" -lt "$END_TIME" ]; do
  COUNT=$((COUNT + 1))
  
  if [[ $BURST_MODE -eq 0 ]] && [[ $((COUNT % 80)) -eq 0 ]]; then
    echo ""
    echo "🔥 LOG BURST - High volume spike!"
    for ((burst=0;burst<15;burst++)); do
      (
        ENV="$(pick "${ENVS[@]}")"
        REGION="$(pick "${REGIONS[@]}")"
        SVC="$(pick "${SERVICES[@]}")"
        LEVEL=$(get_log_level "$ENV")
        MESSAGE=$(get_message "$SVC" "$LEVEL")
        HTTP_CODE="$(pick "${HTTP_CODES[@]}")"
        USER_ID="$(pick "${USERS[@]}")"
        CUSTOMER="$(pick "${CUSTOMERS[@]}")"
        RESPONSE_TIME=$(generate_response_time "$LEVEL")
        TRACE_ID=$(generate_trace_id)
        
        TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")
        
        LEVEL_EMOJI="ℹ"
        case "$LEVEL" in
          DEBUG) LEVEL_EMOJI="🔍" ;;
          INFO) LEVEL_EMOJI="✓" ;;
          WARN) LEVEL_EMOJI="⚠" ;;
          ERROR) LEVEL_EMOJI="✗" ;;
        esac
        
        echo "  [burst] $LEVEL_EMOJI $LEVEL | $SVC | ${RESPONSE_TIME}ms | $HTTP_CODE | ${MESSAGE:0:50}..."
        
        STACK_TRACE=""
        ERROR_CODE=""
        if [ "$LEVEL" = "ERROR" ]; then
          ERROR_CODE=",error.code=\"$(pick E500 E503 E504 ECONNREFUSED ETIMEDOUT ENOTFOUND)\""
          if [ $((RANDOM % 3)) -eq 0 ]; then
            STACK_TRACES=(
              "at processRequest (handler.js:234)|at validateToken (auth.js:89)|at middleware (app.js:45)"
              "at executeQuery (db.js:567)|at pool.connect (pool.js:123)|at DatabaseError (error.js:89)"
              "at httpRequest (client.js:445)|at retry (retry.js:23)|at timeout (timeout.js:67)"
              "at parseJSON (parser.js:178)|at deserialize (serializer.js:92)|at TypeError (core.js:12)"
            )
            STACK_TRACE=",error.stack=\"$(pick "${STACK_TRACES[@]}")\""
          fi
        fi
        
        REQUEST_ID="req_$(printf '%08x' $((RANDOM * RANDOM)))"
        
        $DOCKER_RUN $TELEMETRYGEN_IMG logs \
          --otlp-http \
          --otlp-endpoint "$ENDPOINT" \
          "${INSECURE_FLAG[@]}" \
          --logs 1 \
          --body "$MESSAGE" \
          --otlp-attributes "service.name=\"$SVC\",env=\"$ENV\",cloud.region=\"$REGION\",level=\"$LEVEL\",http.status_code=$HTTP_CODE,user.id=\"$USER_ID\",customer=\"$CUSTOMER\",trace.id=\"$TRACE_ID\",request.id=\"$REQUEST_ID\",response.time_ms=$RESPONSE_TIME,timestamp=\"$TIMESTAMP\"$ERROR_CODE$STACK_TRACE" \
          >/dev/null 2>&1
      ) &
    done
    wait
    echo "🔥 Burst complete"
    echo ""
  fi
  
  ENV="$(pick "${ENVS[@]}")"
  REGION="$(pick "${REGIONS[@]}")"
  SVC="$(pick "${SERVICES[@]}")"
  LEVEL=$(get_log_level "$ENV")
  MESSAGE=$(get_message "$SVC" "$LEVEL")
  HTTP_CODE="$(pick "${HTTP_CODES[@]}")"
  USER_ID="$(pick "${USERS[@]}")"
  CUSTOMER="$(pick "${CUSTOMERS[@]}")"
  RESPONSE_TIME=$(generate_response_time "$LEVEL")
  
  if [ ${#TRACE_IDS[@]} -lt 30 ] || [ $((RANDOM % 4)) -eq 0 ]; then
    TRACE_ID=$(generate_trace_id)
    TRACE_IDS+=("$TRACE_ID")
    if [ ${#TRACE_IDS[@]} -gt 50 ]; then
      TRACE_IDS=("${TRACE_IDS[@]:10}")
    fi
  else
    TRACE_ID="${TRACE_IDS[$((RANDOM % ${#TRACE_IDS[@]}))]}"
  fi
  
  case "$LEVEL" in
    ERROR) ERROR_COUNT=$((ERROR_COUNT + 1)) ;;
    WARN) WARN_COUNT=$((WARN_COUNT + 1)) ;;
    DEBUG) DEBUG_COUNT=$((DEBUG_COUNT + 1)) ;;
    INFO) INFO_COUNT=$((INFO_COUNT + 1)) ;;
  esac
  
  LEVEL_EMOJI="ℹ"
  case "$LEVEL" in
    DEBUG) LEVEL_EMOJI="🔍" ;;
    INFO) LEVEL_EMOJI="✓" ;;
    WARN) LEVEL_EMOJI="⚠" ;;
    ERROR) LEVEL_EMOJI="✗" ;;
  esac

  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")
  
  TRUNCATED_MSG="${MESSAGE:0:70}"
  if [ ${#MESSAGE} -gt 70 ]; then
    TRUNCATED_MSG="${TRUNCATED_MSG}..."
  fi
  
  echo "[$COUNT] $LEVEL_EMOJI $LEVEL | $SVC | $ENV/$REGION | ${RESPONSE_TIME}ms | $HTTP_CODE | $TRUNCATED_MSG"

  STACK_TRACE=""
  ERROR_CODE=""
  if [ "$LEVEL" = "ERROR" ]; then
    ERROR_CODE=",error.code=\"$(pick E500 E503 E504 ECONNREFUSED ETIMEDOUT ENOTFOUND ECONNRESET EPIPE)\""
    if [ $((RANDOM % 2)) -eq 0 ]; then
      STACK_TRACES=(
        "at processRequest (handler.js:234)|at validateToken (auth.js:89)|at middleware (app.js:45)"
        "at executeQuery (db.js:567)|at pool.connect (pool.js:123)|at DatabaseError (error.js:89)"
        "at httpRequest (client.js:445)|at retry (retry.js:23)|at timeout (timeout.js:67)"
        "at parseJSON (parser.js:178)|at deserialize (serializer.js:92)|at TypeError (core.js:12)"
        "at kafkaProducer (kafka.js:334)|at sendBatch (producer.js:156)|at BrokerError (errors.js:45)"
        "at redisCommand (redis.js:289)|at pipeline (pipeline.js:78)|at ConnectionError (conn.js:123)"
      )
      STACK_TRACE=",error.stack=\"$(pick "${STACK_TRACES[@]}")\""
    fi
  fi
  
  REQUEST_ID="req_$(printf '%08x' $((RANDOM * RANDOM)))"
  
  BUILD_VERSION="v$(( (RANDOM % 3) + 1 )).$(( (RANDOM % 20) + 10 )).$(( RANDOM % 50 ))"
  HOSTNAME="$(echo "$SVC" | tr '-' '_')_$(printf '%04x' $RANDOM)"
  
  EXTRA_ATTRS=""
  if [[ $((RANDOM % 3)) -eq 0 ]]; then
    EXTRA_ATTRS=",host.name=\"$HOSTNAME\",service.version=\"$BUILD_VERSION\""
  fi
  
  attempt=0
  CODE=1
  until [[ $attempt -ge $RETRIES ]]; do
    set +e
    $DOCKER_RUN $TELEMETRYGEN_IMG logs \
      --otlp-http \
      --otlp-endpoint "$ENDPOINT" \
      "${INSECURE_FLAG[@]}" \
      --logs 1 \
      --body "$MESSAGE" \
      --otlp-attributes "service.name=\"$SVC\",env=\"$ENV\",cloud.region=\"$REGION\",level=\"$LEVEL\",http.status_code=$HTTP_CODE,user.id=\"$USER_ID\",customer=\"$CUSTOMER\",trace.id=\"$TRACE_ID\",request.id=\"$REQUEST_ID\",response.time_ms=$RESPONSE_TIME,timestamp=\"$TIMESTAMP\"$ERROR_CODE$STACK_TRACE$EXTRA_ATTRS" \
      >/dev/null 2>&1
    CODE=$?
    set -e

    [[ $CODE -eq 0 ]] && break
    attempt=$((attempt+1))
    [[ $attempt -lt $RETRIES ]] && sleep 0.3
  done
  
  if [[ $CODE -ne 0 ]]; then
    echo "    ⚠ Send failed after $RETRIES attempts"
  fi

  if [[ $((RANDOM % 100)) -lt 3 ]]; then
    spike_delay=$(echo "scale=3; $DELAY * $(( (RANDOM % 15) + 5 ))" | bc -l 2>/dev/null || echo "$DELAY")
    sleep "$spike_delay"
  else
    sleep "$DELAY"
  fi
  
  if (( COUNT % 100 == 0 )); then
    ELAPSED=$((SECONDS))
    REMAINING=$((END_TIME - SECONDS))
    REMAINING_MINS=$((REMAINING / 60))
    ERROR_RATE=$(awk "BEGIN {printf \"%.1f\", ($ERROR_COUNT/$COUNT)*100}" 2>/dev/null || echo "0.0")
    WARN_RATE=$(awk "BEGIN {printf \"%.1f\", ($WARN_COUNT/$COUNT)*100}" 2>/dev/null || echo "0.0")
    LOGS_PER_SEC=$(awk "BEGIN {printf \"%.1f\", $COUNT/$ELAPSED}" 2>/dev/null || echo "0.0")
    echo ""
    echo "📊 Stats: $COUNT logs | ${ELAPSED}s elapsed | ${REMAINING_MINS}m remaining"
    echo "   Rates: $LOGS_PER_SEC logs/sec | Errors: $ERROR_COUNT ($ERROR_RATE%) | Warnings: $WARN_COUNT ($WARN_RATE%)"
    echo "   Distribution: INFO=$INFO_COUNT | DEBUG=$DEBUG_COUNT | WARN=$WARN_COUNT | ERROR=$ERROR_COUNT"
    echo ""
  fi
done

echo ""
echo "========================================"
echo "✅ Complete: $COUNT logs generated"
echo "   INFO: $INFO_COUNT | DEBUG: $DEBUG_COUNT | WARN: $WARN_COUNT | ERROR: $ERROR_COUNT"
echo "   Duration: ${DURATION_MINUTES} minutes"
echo "========================================"