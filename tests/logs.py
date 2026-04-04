#!/usr/bin/env python3
import sys
import time
import random
import secrets
import json
import threading
from urllib.request import urlopen, Request
from urllib.error import URLError

ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "localhost:4318"
COUNT    = int(sys.argv[2]) if len(sys.argv) > 2 else 500
PARALLEL = int(sys.argv[3]) if len(sys.argv) > 3 else 12
LOOPS    = int(sys.argv[4]) if len(sys.argv) > 4 else 0
DELAY    = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0

SERVICES = [
    ("payment-service",      "v2.3.1"),
    ("order-service",        "v1.8.4"),
    ("auth-service",         "v3.1.0"),
    ("inventory-service",    "v2.0.7"),
    ("notification-service", "v1.5.2"),
    ("api-gateway",          "v4.2.1"),
    ("catalog-service",      "v2.1.3"),
    ("shipping-service",     "v1.9.0"),
    ("search-service",       "v3.0.5"),
    ("fraud-detection",      "v2.4.1"),
    ("analytics-service",    "v1.7.3"),
    ("checkout-service",     "v2.2.0"),
    ("billing-service",      "v1.4.6"),
    ("gateway-service",      "v3.3.2"),
    ("messaging-service",    "v2.0.1"),
]

REGIONS = ["us-east-1","us-west-2","eu-west-1","eu-central-1","ap-southeast-1","ap-northeast-1",
           "eu-north-1","ap-southeast-2","eu-west-3","eu-central-2","us-east-2","us-west-1"]
ENVS    = ["prod"]*4 + ["staging"]*2 + ["dev"]

SERVICE_ENDPOINTS = {
    "payment-service":      ["POST /v1/charges","POST /v1/refunds","GET /v1/charges/{id}","POST /v1/payment-methods","GET /v1/balance"],
    "order-service":        ["POST /v1/orders","GET /v1/orders/{id}","PATCH /v1/orders/{id}","GET /v1/orders","POST /v1/orders/{id}/cancel"],
    "auth-service":         ["POST /v1/auth/login","POST /v1/auth/refresh","POST /v1/auth/logout","GET /v1/auth/me","POST /v1/auth/verify"],
    "inventory-service":    ["GET /v1/inventory/{sku}","PUT /v1/inventory/{sku}/reserve","GET /v1/inventory","POST /v1/inventory/bulk"],
    "notification-service": ["POST /v1/notifications/email","POST /v1/notifications/sms","POST /v1/notifications/push","GET /v1/notifications/{id}/status"],
    "api-gateway":          ["GET /api/v1/products","POST /api/v1/cart","GET /api/v1/cart","POST /api/v1/checkout","GET /api/v1/orders"],
    "catalog-service":      ["GET /v1/products","GET /v1/products/{id}","GET /v1/categories","GET /v1/products/search","PUT /v1/products/{id}"],
    "shipping-service":     ["POST /v1/shipments","GET /v1/shipments/{id}","GET /v1/rates","POST /v1/labels","GET /v1/tracking/{id}"],
    "search-service":       ["GET /v1/search","POST /v1/search/suggest","POST /v1/index","DELETE /v1/index/{id}","GET /v1/search/facets"],
    "fraud-detection":      ["POST /v1/analyze","GET /v1/rules","POST /v1/flag","GET /v1/score/{id}","POST /v1/feedback"],
    "analytics-service":    ["POST /v1/events","GET /v1/reports","GET /v1/metrics","POST /v1/batch","GET /v1/dashboards/{id}"],
    "checkout-service":     ["POST /v1/checkout","GET /v1/checkout/{id}","POST /v1/checkout/{id}/confirm","DELETE /v1/checkout/{id}"],
    "billing-service":      ["POST /v1/invoices","GET /v1/invoices/{id}","POST /v1/subscriptions","GET /v1/subscriptions/{id}","POST /v1/billing/retry"],
    "gateway-service":      ["GET /health","POST /v1/route","GET /v1/config","POST /v1/auth","GET /v1/metrics"],
    "messaging-service":    ["POST /v1/messages","GET /v1/messages/{id}","POST /v1/topics","GET /v1/topics","POST /v1/subscribe"],
}

DB_POOLS      = ["primary","replica-1","replica-2","replica-3"]
CACHE_NODES   = ["redis-cluster-0","redis-cluster-1","redis-cluster-2"]
QUEUE_NAMES   = ["orders.created","payments.processed","notifications.pending","inventory.reserved","fraud.analyze","shipments.queued"]
USER_AGENTS   = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "okhttp/4.12.0",
    "python-httpx/0.27.0",
    "axios/1.6.8 node/20.11.0",
    "Go-http-client/2.0",
    "curl/8.6.0",
]
CURRENCIES    = ["USD","EUR","GBP","CAD","AUD","JPY","SGD","CHF"]
CARD_BRANDS   = ["Visa","Mastercard","Amex","Discover","UnionPay"]
CARRIERS      = ["UPS","FedEx","USPS","DHL","OnTrac","LaserShip","Amazon Logistics"]
EMAIL_PROVS   = ["SendGrid","Mailgun","SES","Postmark"]
SMS_PROVS     = ["Twilio","Vonage","Sinch","MessageBird"]
ML_MODELS     = ["fraud-xgb-v4.2","fraud-nn-v2.1","risk-lgbm-v3.0","anomaly-iso-v1.5"]
SEARCH_IDXS   = ["products_v8","products_v7","catalog_primary","catalog_shadow"]
WAREHOUSES    = ["WH-EAST-01","WH-WEST-02","WH-EU-01","WH-APAC-01"]
HTTP_VERSIONS = ["HTTP/1.1","HTTP/2","HTTP/3"]

def pick(lst):       return random.choice(lst)
def rand(a, b):      return random.randint(a, b)
def uid():           return f"usr_{secrets.token_hex(6)}"
def oid():           return f"ord_{secrets.token_hex(8)}"
def tid():           return f"txn_{secrets.token_hex(8)}"
def pid():           return f"pay_{secrets.token_hex(8)}"
def sid():           return f"sess_{secrets.token_hex(8)}"
def skuid():         return f"SKU-{rand(10000,99999)}-{pick(['A','B','C','D'])}"
def amount():        return f"{rand(1,9999)}.{rand(0,99):02d}"
def ip():            return f"{rand(1,254)}.{rand(1,254)}.{rand(1,254)}.{rand(1,254)}"
def db_pool():       return pick(DB_POOLS)
def cache_node():    return pick(CACHE_NODES)
def ms(lo, hi):      return rand(lo, hi)

INFO_TEMPLATES = {
    "payment-service": [
        lambda: f"Payment authorized successfully | transaction_id={tid()} user_id={uid()} amount={amount()} {pick(CURRENCIES)} card_brand={pick(CARD_BRANDS)} last4={rand(1000,9999)} acquirer_response=00 avs_result=Y cvv_result=M processing_time_ms={ms(80,350)} gateway=stripe idempotency_key={secrets.token_hex(12)}",
        lambda: f"Refund processed | refund_id=ref_{secrets.token_hex(8)} original_transaction_id={tid()} user_id={uid()} amount={amount()} {pick(CURRENCIES)} reason=customer_request refund_method=original_payment_method estimated_arrival_days={rand(3,7)} gateway_ref={secrets.token_hex(10)}",
        lambda: f"Payment method tokenized | user_id={uid()} card_brand={pick(CARD_BRANDS)} last4={rand(1000,9999)} exp_month={rand(1,12):02d} exp_year={rand(25,30)} vault=stripe fingerprint={secrets.token_hex(12)} billing_zip_verified=true",
        lambda: f"Settlement batch submitted | batch_id=batch_{secrets.token_hex(6)} transaction_count={rand(50,500)} total_amount={rand(10000,999999)}.{rand(0,99):02d} {pick(CURRENCIES)} processor=worldpay submission_time_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())} expected_settlement_date={time.strftime('%Y-%m-%d',time.gmtime())}",
        lambda: f"3DS2 authentication completed | transaction_id={tid()} user_id={uid()} eci=05 authentication_value={secrets.token_hex(20)} acs_transaction_id={secrets.token_hex(16)} ds_transaction_id={secrets.token_hex(16)} liability_shift=true challenge_required=false",
        lambda: f"Chargeback notification received | chargeback_id=cb_{secrets.token_hex(8)} original_transaction_id={tid()} amount={amount()} {pick(CURRENCIES)} reason_code=4853 reason=cardholder_dispute dispute_deadline={time.strftime('%Y-%m-%d',time.gmtime())} evidence_due_in_days={rand(7,21)}",
    ],
    "order-service": [
        lambda: f"Order created successfully | order_id={oid()} user_id={uid()} item_count={rand(1,8)} subtotal={amount()} {pick(CURRENCIES)} shipping_method={pick(['standard','express','overnight','free'])} estimated_delivery={time.strftime('%Y-%m-%d',time.gmtime())} warehouse={pick(WAREHOUSES)} carrier={pick(CARRIERS)} payment_id={pid()}",
        lambda: f"Order status transitioned | order_id={oid()} user_id={uid()} from=payment_captured to=fulfillment_queued fulfillment_center={pick(WAREHOUSES)} pick_queue_position={rand(1,200)} estimated_pick_time_minutes={rand(15,120)} worker_id=wkr_{rand(100,999)}",
        lambda: f"Partial fulfillment processed | order_id={oid()} user_id={uid()} fulfilled_items={rand(1,5)} backordered_items={rand(1,3)} backordered_skus={skuid()} estimated_restock_date={time.strftime('%Y-%m-%d',time.gmtime())} customer_notified=true split_shipment=true",
        lambda: f"Order cancellation completed | order_id={oid()} user_id={uid()} cancellation_reason=customer_request items_restocked={rand(1,5)} refund_initiated=true refund_id=ref_{secrets.token_hex(8)} inventory_released_to={pick(WAREHOUSES)} cancellation_window_hours=1",
        lambda: f"Order fraud hold released | order_id={oid()} user_id={uid()} hold_duration_minutes={rand(5,60)} fraud_score={rand(1,30)} reviewer=auto_release threshold=35 release_reason=score_below_threshold queue_backlog_before={rand(0,50)}",
    ],
    "auth-service": [
        lambda: f"User authenticated successfully | user_id={uid()} session_id={sid()} ip={ip()} user_agent='{pick(USER_AGENTS)}' mfa_method={pick(['totp','sms','email','webauthn','none'])} login_method={pick(['password','sso_google','sso_github','magic_link'])} geo_country={pick(['US','GB','DE','FR','SG','AU','CA'])} new_device={pick(['true','false','false','false'])} risk_score={rand(0,25)}",
        lambda: f"Access token issued | user_id={uid()} session_id={sid()} token_jti={secrets.token_hex(16)} expires_in_seconds=900 refresh_token_jti={secrets.token_hex(16)} refresh_expires_in_seconds=2592000 scopes=read:orders,write:cart,read:profile issued_at={int(time.time())}",
        lambda: f"Token refreshed | user_id={uid()} old_jti={secrets.token_hex(16)} new_jti={secrets.token_hex(16)} session_id={sid()} ip={ip()} rotation_policy=one_time_use sliding_window_extended=true session_age_minutes={rand(5,1440)}",
        lambda: f"SAML SSO assertion validated | user_id={uid()} idp=okta assertion_id={secrets.token_hex(20)} session_index={secrets.token_hex(12)} name_id={uid()}@corp.example.com attributes_mapped=email,groups,department just_in_time_provisioned=false session_id={sid()}",
        lambda: f"Password changed successfully | user_id={uid()} ip={ip()} all_sessions_revoked=true active_sessions_terminated={rand(1,8)} breach_check_passed=true hibp_pwned_count=0 new_hash_algo=argon2id notification_sent=email",
    ],
    "inventory-service": [
        lambda: f"Inventory reserved | reservation_id=res_{secrets.token_hex(8)} order_id={oid()} sku={skuid()} quantity={rand(1,10)} warehouse={pick(WAREHOUSES)} bin_location=A{rand(1,30)}-B{rand(1,20)}-C{rand(1,5)} expires_at={int(time.time())+900} available_after_reserve={rand(0,200)} soft_allocated=false",
        lambda: f"Stock level checked | sku={skuid()} warehouse={pick(WAREHOUSES)} on_hand={rand(0,500)} reserved={rand(0,100)} available={rand(0,400)} on_order={rand(0,200)} reorder_point={rand(10,50)} lead_time_days={rand(2,14)} supplier=SUP-{rand(100,999)} last_receipt_date={time.strftime('%Y-%m-%d',time.gmtime())}",
        lambda: f"Inventory sync completed | warehouse={pick(WAREHOUSES)} skus_synced={rand(100,5000)} discrepancies_found={rand(0,5)} discrepancies_resolved={rand(0,5)} sync_duration_ms={ms(200,2000)} source=wms_feed feed_sequence={rand(100000,999999)} delta_records={rand(1,500)}",
        lambda: f"Reorder triggered automatically | sku={skuid()} warehouse={pick(WAREHOUSES)} current_stock={rand(0,15)} reorder_point={rand(16,30)} reorder_quantity={rand(50,500)} supplier=SUP-{rand(100,999)} po_id=PO-{secrets.token_hex(6)} estimated_arrival_days={rand(3,14)}",
    ],
    "notification-service": [
        lambda: f"Email delivered successfully | message_id=msg_{secrets.token_hex(10)} user_id={uid()} template=order_confirmation provider={pick(EMAIL_PROVS)} to_domain={pick(['gmail.com','yahoo.com','outlook.com','company.com'])} queued_at={int(time.time())-rand(1,30)} delivered_at={int(time.time())} latency_ms={ms(200,3000)} open_tracking=true click_tracking=true",
        lambda: f"SMS delivered | message_id=sms_{secrets.token_hex(8)} user_id={uid()} provider={pick(SMS_PROVS)} to_country={pick(['US','GB','DE','AU','SG'])} segments={rand(1,3)} character_count={rand(40,459)} queued_at={int(time.time())-rand(1,15)} delivered_at={int(time.time())} delivery_receipt=delivered",
        lambda: f"Push notification delivered | user_id={uid()} device_id=dev_{secrets.token_hex(8)} platform={pick(['ios','android','web'])} provider={pick(['apns','fcm','web_push'])} message_id=pn_{secrets.token_hex(8)} payload_bytes={rand(100,3900)} ttl_seconds=86400 collapse_key=order_update priority=high delivery_latency_ms={ms(50,800)}",
        lambda: f"Bulk notification batch dispatched | campaign_id=camp_{secrets.token_hex(6)} channel={pick(['email','sms','push'])} total_recipients={rand(1000,50000)} dispatched={rand(900,49000)} failed={rand(0,100)} deduped={rand(0,500)} provider={pick(EMAIL_PROVS)} estimated_completion_minutes={rand(2,30)} rate_limit_per_second={rand(50,500)}",
    ],
    "api-gateway": [
        lambda: f"Request proxied upstream | method={pick(['GET','POST','PUT','PATCH','DELETE'])} path=/api/v{rand(1,3)}/{pick(['orders','products','cart','users','payments'])}/{secrets.token_hex(4)} upstream={pick(list(SERVICE_ENDPOINTS.keys()))} upstream_host={pick(['10.0.1','10.0.2','10.0.3'])}.{rand(1,254)} protocol={pick(HTTP_VERSIONS)} tls=true latency_ms={ms(5,200)} upstream_latency_ms={ms(3,180)} cache={pick(['miss','miss','miss','hit'])} x_forwarded_for={ip()} user_id={uid()}",
        lambda: f"Rate limit check passed | user_id={uid()} ip={ip()} plan={pick(['free','starter','pro','enterprise'])} window=1m requests_used={rand(1,800)} requests_limit={rand(1000,10000)} remaining={rand(200,9999)} x_ratelimit_reset={int(time.time())+rand(10,60)} key_type=user",
        lambda: f"Response cached | cache_key=sha256:{secrets.token_hex(32)} ttl_seconds={rand(30,3600)} content_type=application/json content_length_bytes={rand(200,50000)} vary_headers=Accept-Encoding,Accept hit_ratio_window_1m={rand(40,95)}pct upstream_saved=true",
    ],
    "catalog-service": [
        lambda: f"Product search executed | query='{pick(['running shoes','wireless headphones','laptop stand','coffee maker','yoga mat'])}' index={pick(SEARCH_IDXS)} hits={rand(0,2000)} took_ms={ms(5,150)} filters=category:{pick(['electronics','sports','home','clothing'])} sort={pick(['relevance','price_asc','price_desc','rating'])} page={rand(1,20)} page_size={rand(10,50)} boosted_skus={rand(0,5)}",
        lambda: f"Product retrieved from cache | product_id=prod_{secrets.token_hex(8)} sku={skuid()} cache_node={cache_node()} cache_age_seconds={rand(0,3600)} serialized_bytes={rand(500,8000)} variants={rand(1,20)} media_assets={rand(1,10)} last_modified={time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}",
        lambda: f"Search index rebuild completed | index={pick(SEARCH_IDXS)} documents_indexed={rand(10000,500000)} took_seconds={rand(30,600)} shards={rand(3,12)} replicas=1 index_size_mb={rand(100,5000)} previous_index=products_v{rand(5,7)} alias_swapped=true zero_downtime=true",
    ],
    "shipping-service": [
        lambda: f"Shipment created | shipment_id=ship_{secrets.token_hex(8)} order_id={oid()} carrier={pick(CARRIERS)} service_level={pick(['ground','2day','overnight','priority_mail'])} tracking_number={secrets.token_hex(10).upper()} origin_warehouse={pick(WAREHOUSES)} destination_zip={rand(10000,99999)} weight_oz={rand(4,320)} dimensions_in={rand(4,24)}x{rand(4,18)}x{rand(2,12)} rate_usd={amount()}",
        lambda: f"Label generated | shipment_id=ship_{secrets.token_hex(8)} carrier={pick(CARRIERS)} tracking_number={secrets.token_hex(10).upper()} label_format={pick(['ZPL','PDF','PNG'])} label_size={pick(['4x6','4x8','letter'])} label_bytes={rand(5000,80000)} generation_ms={ms(100,800)} label_stored=s3://labels/{secrets.token_hex(20)}",
        lambda: f"Tracking event received | tracking_number={secrets.token_hex(10).upper()} carrier={pick(CARRIERS)} event={pick(['picked_up','in_transit','out_for_delivery','delivered','delivery_attempted','exception'])} location={pick(['Chicago, IL','Dallas, TX','Los Angeles, CA','Memphis, TN','Louisville, KY'])} event_timestamp={int(time.time())-rand(0,86400)} customer_notified=true",
    ],
    "search-service": [
        lambda: f"Search query completed | query='{pick(['red shoes size 10','gaming laptop under 1000','organic coffee beans','standing desk','noise cancelling headphones'])}' index={pick(SEARCH_IDXS)} total_hits={rand(0,5000)} returned={rand(10,50)} took_ms={ms(3,120)} query_type={pick(['match','multi_match','bool','function_score'])} filters={rand(0,5)} facets_computed={rand(0,8)} synonyms_expanded={rand(0,3)} spell_corrected={pick(['true','false','false','false'])}",
        lambda: f"Autocomplete suggestion served | prefix='{pick(['lap','wire','cof','run','yog'])}' index={pick(SEARCH_IDXS)} suggestions_returned={rand(3,10)} took_ms={ms(1,15)} model=completion_v{rand(2,4)} personalized={pick(['true','false'])} user_id={uid()} ctr_model=xgb_v3",
        lambda: f"Document indexed | doc_id=prod_{secrets.token_hex(8)} index={pick(SEARCH_IDXS)} shard={rand(0,11)} seq_no={rand(100000,9999999)} primary_term={rand(1,5)} took_ms={ms(5,80)} refresh={pick(['false','false','wait_for'])} pipeline=catalog_enrich_v2",
    ],
    "fraud-detection": [
        lambda: f"Transaction risk scored | transaction_id={tid()} user_id={uid()} amount={amount()} {pick(CURRENCIES)} score={rand(0,100)} model={pick(ML_MODELS)} decision={pick(['allow','allow','allow','review','block'])} features_used=47 inference_ms={ms(5,80)} ip_risk_score={rand(0,100)} email_age_days={rand(0,3650)} device_fingerprint={secrets.token_hex(12)} velocity_1h={rand(0,10)}",
        lambda: f"Fraud rule evaluation completed | transaction_id={tid()} rules_evaluated={rand(20,150)} rules_triggered={rand(0,5)} triggered_rule_ids=[{','.join([f'rule_{rand(100,999)}' for _ in range(rand(0,3))])}] max_severity={pick(['none','low','medium'])} final_decision=allow override=false evaluation_ms={ms(1,20)}",
        lambda: f"User velocity check | user_id={uid()} window=1h transactions_count={rand(1,20)} transaction_ids_sample=[{tid()},{tid()}] total_volume_usd={amount()} velocity_score={rand(0,50)} baseline_txns_per_hour={rand(1,5)} anomaly_ratio={rand(100,200)/100:.2f} flagged=false",
    ],
    "analytics-service": [
        lambda: f"Event ingested | event_type={pick(['page_view','add_to_cart','checkout_started','purchase_completed','search','product_view','coupon_applied'])} user_id={uid()} session_id={sid()} event_id=evt_{secrets.token_hex(10)} timestamp={int(time.time())} properties_count={rand(5,30)} schema_version=3 pipeline=kinesis_ingest partition={rand(0,63)} offset={rand(0,9999999)}",
        lambda: f"Report generated | report_id=rpt_{secrets.token_hex(8)} report_type={pick(['daily_revenue','cohort_retention','funnel_analysis','ab_test_results','inventory_summary'])} date_range={rand(1,90)}d rows_processed={rand(1000,10000000)} computation_ms={ms(500,30000)} cache_hit=false output_format={pick(['json','csv','parquet'])} destination=s3://reports/{secrets.token_hex(10)}",
        lambda: f"A/B test metrics updated | experiment_id=exp_{secrets.token_hex(6)} variant={pick(['control','treatment_a','treatment_b'])} metric={pick(['conversion_rate','revenue_per_user','session_duration','bounce_rate'])} sample_size={rand(1000,100000)} current_value={rand(0,100)/100:.4f} baseline={rand(0,100)/100:.4f} p_value={rand(0,100)/1000:.4f} power={rand(70,99)/100:.2f} significant={pick(['false','false','true'])}",
    ],
    "checkout-service": [
        lambda: f"Checkout session initiated | checkout_id=chk_{secrets.token_hex(8)} user_id={uid()} cart_items={rand(1,10)} cart_value={amount()} {pick(CURRENCIES)} shipping_options_available={rand(1,5)} coupons_applied={rand(0,2)} estimated_tax={rand(0,50)}.{rand(0,99):02d} payment_methods_on_file={rand(1,4)} session_ttl_seconds=1800",
        lambda: f"Order confirmed from checkout | checkout_id=chk_{secrets.token_hex(8)} order_id={oid()} user_id={uid()} payment_id={pid()} amount_charged={amount()} {pick(CURRENCIES)} items={rand(1,8)} fulfillment_center={pick(WAREHOUSES)} confirmation_email_queued=true inventory_reserved=true fraud_score={rand(0,30)}",
        lambda: f"Cart validation completed | checkout_id=chk_{secrets.token_hex(8)} user_id={uid()} items_validated={rand(1,8)} price_changes_detected={rand(0,2)} out_of_stock_items={rand(0,1)} coupon_validity_checked=true shipping_rates_refreshed=true validation_ms={ms(50,400)}",
    ],
    "billing-service": [
        lambda: f"Invoice generated | invoice_id=inv_{secrets.token_hex(8)} customer_id={uid()} subscription_id=sub_{secrets.token_hex(8)} period_start={int(time.time())-2592000} period_end={int(time.time())} line_items={rand(1,10)} subtotal={amount()} tax={rand(0,50)}.{rand(0,99):02d} total={amount()} {pick(CURRENCIES)} due_date={time.strftime('%Y-%m-%d',time.gmtime())} pdf_generated=true",
        lambda: f"Subscription renewed | subscription_id=sub_{secrets.token_hex(8)} customer_id={uid()} plan={pick(['starter','growth','pro','enterprise'])} billing_cycle={pick(['monthly','annual'])} amount={amount()} {pick(CURRENCIES)} payment_method_last4={rand(1000,9999)} next_billing_date={time.strftime('%Y-%m-%d',time.gmtime())} renewal_attempt=1 proration_applied=false",
        lambda: f"Payment retry succeeded | invoice_id=inv_{secrets.token_hex(8)} customer_id={uid()} attempt_number={rand(2,4)} amount={amount()} {pick(CURRENCIES)} previous_failure_code={pick(['card_declined','insufficient_funds','expired_card'])} retry_strategy=exponential_backoff days_past_due={rand(1,30)} account_reactivated=true",
    ],
    "gateway-service": [
        lambda: f"Request routed | route_id=rt_{rand(100,999)} method={pick(['GET','POST','PUT','DELETE'])} path=/v{rand(1,3)}/{pick(['orders','payments','auth','inventory','catalog'])}/{secrets.token_hex(4)} upstream={pick(list(SERVICE_ENDPOINTS.keys()))} strategy={pick(['round_robin','least_connections','weighted','ip_hash'])} upstream_pod=pod-{secrets.token_hex(4)} response_ms={ms(5,300)} retried=false",
        lambda: f"Health check cycle completed | checked_upstreams={rand(5,15)} healthy={rand(10,15)} degraded={rand(0,2)} unhealthy={rand(0,1)} check_interval_seconds=10 total_check_ms={ms(50,500)} circuit_breakers_open={rand(0,1)} passive_checks_updated=true",
        lambda: f"Config hot-reloaded | config_version=v{rand(1,100)} source=consul previous_version=v{rand(1,99)} changes_detected={rand(1,10)} routes_updated={rand(0,5)} upstreams_updated={rand(0,3)} zero_downtime=true workers_reloaded={rand(2,16)} reload_ms={ms(10,200)}",
    ],
    "messaging-service": [
        lambda: f"Message published | message_id=msg_{secrets.token_hex(10)} topic={pick(QUEUE_NAMES)} partition={rand(0,23)} offset={rand(0,9999999)} key={secrets.token_hex(8)} payload_bytes={rand(50,65536)} producer_id=prod_{secrets.token_hex(6)} acks={pick(['all','-1','1'])} compression={pick(['none','gzip','snappy','lz4'])} latency_ms={ms(1,50)}",
        lambda: f"Consumer group rebalanced | group_id=grp_{secrets.token_hex(6)} topic={pick(QUEUE_NAMES)} assigned_partitions={rand(1,24)} revoked_partitions={rand(0,12)} generation_id={rand(1,500)} protocol={pick(['range','roundrobin','sticky'])} consumer_count={rand(2,20)} rebalance_ms={ms(100,3000)} lag_after={rand(0,10000)}",
        lambda: f"Dead letter queue entry | original_topic={pick(QUEUE_NAMES)} dlq_topic={pick(QUEUE_NAMES)}.dlq message_id=msg_{secrets.token_hex(10)} failure_reason={pick(['deserialization_error','processing_timeout','consumer_exception','schema_mismatch'])} attempt_count={rand(3,5)} first_failure_epoch={int(time.time())-rand(300,86400)} payload_bytes={rand(50,8192)}",
    ],
}

WARN_TEMPLATES = {
    "payment-service": [
        lambda: f"Payment retry attempt | transaction_id={tid()} user_id={uid()} attempt={rand(2,4)} of 4 failure_code={pick(['gateway_timeout','network_error','processor_unavailable'])} next_retry_in_seconds={rand(30,300)} amount={amount()} {pick(CURRENCIES)} elapsed_since_first_attempt_ms={ms(1000,30000)}",
        lambda: f"High-value transaction flagged for review | transaction_id={tid()} user_id={uid()} amount={rand(5000,99999)}.{rand(0,99):02d} {pick(CURRENCIES)} fraud_score={rand(35,65)} velocity_score={rand(40,70)} rule_triggered=high_value_new_card review_queue_depth={rand(5,50)} auto_approve_threshold=5000",
        lambda: f"Card expiry approaching | user_id={uid()} card_brand={pick(CARD_BRANDS)} last4={rand(1000,9999)} expires={rand(1,12):02d}/{rand(25,26)} subscriptions_at_risk={rand(1,5)} days_until_expiry={rand(1,30)} notification_sent=email dunning_cycle_day={rand(1,7)}",
        lambda: f"Payment gateway latency elevated | gateway=stripe p50_ms={ms(200,400)} p95_ms={ms(800,1500)} p99_ms={ms(1500,3000)} error_rate_pct={rand(1,5)} degraded_since_epoch={int(time.time())-rand(60,600)} affected_transactions_last_5m={rand(10,500)} fallback_gateway=adyen eligible=true",
    ],
    "order-service": [
        lambda: f"Order processing delayed | order_id={oid()} user_id={uid()} expected_sla_minutes=5 current_age_minutes={rand(6,60)} queue_depth={rand(50,500)} worker_availability_pct={rand(40,80)} bottleneck={pick(['payment_capture','inventory_reservation','fraud_check'])} sla_breach_in_minutes={rand(1,30)}",
        lambda: f"Carrier API responding slowly | carrier={pick(CARRIERS)} p99_latency_ms={ms(2000,10000)} timeout_threshold_ms=5000 requests_last_minute={rand(10,200)} errors_last_minute={rand(0,20)} circuit_breaker_state=closed trips_to_open={rand(3,10)} fallback_available=true",
        lambda: f"Inventory hold expiring soon | reservation_id=res_{secrets.token_hex(8)} order_id={oid()} sku={skuid()} expires_in_seconds={rand(60,300)} payment_status=pending user_id={uid()} auto_extend=false release_if_not_captured=true",
    ],
    "auth-service": [
        lambda: f"Multiple failed login attempts | user_id={uid()} ip={ip()} attempts_last_15m={rand(5,20)} lockout_threshold=10 user_agent='{pick(USER_AGENTS)}' geo_country={pick(['RU','CN','KP','IR','NG'])} existing_sessions={rand(0,3)} account_locked={pick(['false','false','true'])} captcha_triggered=true",
        lambda: f"Suspicious token usage detected | user_id={uid()} token_jti={secrets.token_hex(16)} ip={ip()} previous_ip={ip()} geo_distance_km={rand(500,12000)} time_since_issue_seconds={rand(10,120)} impossible_travel={pick(['true','false'])} session_id={sid()} action=flag_for_review",
        lambda: f"OAuth provider degraded | provider={pick(['google','github','microsoft','okta'])} success_rate_5m={rand(70,95)}pct p99_ms={ms(1000,5000)} errors_last_5m={rand(5,50)} fallback_to_password=true affected_logins_last_5m={rand(2,100)} degraded_since_epoch={int(time.time())-rand(60,600)}",
    ],
    "inventory-service": [
        lambda: f"Low stock threshold reached | sku={skuid()} warehouse={pick(WAREHOUSES)} current_stock={rand(1,15)} reorder_point={rand(16,30)} reorder_quantity_suggested={rand(50,500)} days_of_supply_remaining={rand(1,7)} supplier=SUP-{rand(100,999)} avg_daily_velocity={rand(2,20)} stockout_risk=high",
        lambda: f"Inventory sync lag detected | warehouse={pick(WAREHOUSES)} expected_sync_interval_seconds=60 actual_lag_seconds={rand(120,600)} last_successful_sync_epoch={int(time.time())-rand(120,600)} pending_updates={rand(10,500)} wms_api_status=degraded stale_records_pct={rand(1,20)}",
        lambda: f"Reservation conflict detected | sku={skuid()} warehouse={pick(WAREHOUSES)} available_qty={rand(0,5)} requested_qty={rand(6,20)} conflicting_reservations={rand(2,10)} oldest_reservation_age_minutes={rand(1,60)} resolution_strategy=oldest_first order_ids_affected={rand(1,5)}",
    ],
    "notification-service": [
        lambda: f"Email bounce rate elevated | provider={pick(EMAIL_PROVS)} domain={pick(['gmail.com','yahoo.com','hotmail.com'])} bounce_rate_pct={rand(5,15)} hard_bounces={rand(10,100)} soft_bounces={rand(5,50)} threshold_pct=5 emails_sent_1h={rand(1000,50000)} list_hygiene_recommended=true",
        lambda: f"SMS delivery delayed | provider={pick(SMS_PROVS)} destination_country={pick(['US','GB','AU'])} p99_delivery_ms={ms(10000,60000)} expected_p99_ms=5000 queued_messages={rand(100,5000)} carrier_status=degraded retry_queue_depth={rand(50,500)} fallback_provider={pick(SMS_PROVS)}",
        lambda: f"Push notification delivery rate dropping | platform={pick(['ios','android'])} provider={pick(['apns','fcm'])} delivery_rate_5m={rand(70,90)}pct baseline_delivery_rate=97pct unregistered_tokens={rand(10,500)} token_refresh_needed={rand(5,200)} provider_status_page=degraded",
    ],
    "api-gateway": [
        lambda: f"Upstream latency spike detected | upstream={pick(list(SERVICE_ENDPOINTS.keys()))} p99_ms={ms(1000,5000)} baseline_p99_ms={ms(100,500)} spike_factor={rand(3,15):.1f}x requests_in_flight={rand(10,500)} circuit_breaker_threshold_ms=2000 circuit_state=closed consecutive_slow_count={rand(5,20)}",
        lambda: f"Connection pool saturation | upstream={pick(list(SERVICE_ENDPOINTS.keys()))} pool_size={rand(50,200)} active_connections={rand(45,200)} idle_connections={rand(0,5)} queued_requests={rand(1,50)} wait_time_p99_ms={ms(50,500)} pool_utilization_pct={rand(85,99)} scale_out_recommended=true",
        lambda: f"Backend health degraded | upstream={pick(list(SERVICE_ENDPOINTS.keys()))} healthy_nodes={rand(1,3)} total_nodes={rand(4,8)} failing_node=10.0.{rand(1,4)}.{rand(1,254)} failure_reason={pick(['tcp_timeout','http_503','http_429'])} active_connections_rerouted={rand(10,200)} degraded_capacity_pct={rand(50,80)}",
    ],
    "catalog-service": [
        lambda: f"Search index replication lag | primary_index={pick(SEARCH_IDXS)} replica_lag_ms={ms(500,5000)} expected_lag_ms=200 documents_behind={rand(100,10000)} replication_factor=2 lagging_replicas=[replica-{rand(0,2)}] index_size_gb={rand(1,50):.1f} catch_up_eta_seconds={rand(30,300)}",
        lambda: f"Product data quality warning | sku={skuid()} missing_fields=[{','.join(random.sample(['description','weight','dimensions','brand','category','images'],rand(1,3)))}] price_anomaly={pick(['true','false'])} image_count={rand(0,2)} minimum_required_images=3 completeness_score={rand(40,75)}pct indexing_suppressed=false",
    ],
    "shipping-service": [
        lambda: f"Carrier rate API degraded | carrier={pick(CARRIERS)} error_rate_pct={rand(5,30)} p99_ms={ms(3000,10000)} timeout_count_5m={rand(5,50)} fallback_to_cached_rates=true cached_rates_age_minutes={rand(15,120)} rate_accuracy_warning=true affected_shipments_queued={rand(10,200)}",
        lambda: f"Delivery exception detected | tracking_number={secrets.token_hex(10).upper()} carrier={pick(CARRIERS)} exception_type={pick(['address_correction_required','recipient_unavailable','weather_delay','customs_hold'])} shipment_id=ship_{secrets.token_hex(8)} order_id={oid()} days_delayed={rand(1,5)} customer_notification_queued=true",
    ],
    "search-service": [
        lambda: f"Query latency degraded | index={pick(SEARCH_IDXS)} p50_ms={ms(50,200)} p95_ms={ms(200,800)} p99_ms={ms(500,2000)} baseline_p99_ms=200 slow_queries_last_5m={rand(10,200)} jvm_heap_used_pct={rand(70,90)} gc_pause_ms={ms(200,1000)} gc_type={pick(['G1GC','ZGC','Shenandoah'])} shard_count={rand(3,12)}",
        lambda: f"Index segment merge pressure | index={pick(SEARCH_IDXS)} segment_count={rand(100,1000)} merge_threads_active={rand(2,8)} merge_throttle_pct={rand(50,100)} disk_io_wait_ms={ms(100,2000)} indexing_rate_docs_per_sec={rand(100,5000)} merge_backlog_estimated_minutes={rand(5,60)}",
    ],
    "fraud-detection": [
        lambda: f"Model staleness warning | model={pick(ML_MODELS)} trained_epoch={int(time.time())-rand(604800,2592000)} current_auc={rand(85,92)/100:.4f} baseline_auc=0.9450 drift_detected=true feature_drift_score={rand(10,30):.2f} retraining_recommended=true last_retrain_days_ago={rand(7,30)}",
        lambda: f"False positive rate elevated | model={pick(ML_MODELS)} fpr_24h={rand(5,15)}pct baseline_fpr=2pct blocked_good_transactions={rand(10,200)} estimated_revenue_impact_usd={rand(1000,50000)} threshold={rand(60,80)} suggested_threshold={rand(70,90)} review_queue_depth={rand(50,500)}",
    ],
    "analytics-service": [
        lambda: f"Event pipeline lag detected | pipeline=kinesis_ingest partition={rand(0,63)} consumer_lag_records={rand(1000,500000)} lag_seconds={rand(60,600)} throughput_records_per_sec={rand(100,5000)} target_throughput=10000 scaling_triggered={pick(['true','false'])} current_consumers={rand(2,10)} max_consumers=20",
        lambda: f"Data gap detected | report_type={pick(['daily_revenue','cohort','funnel'])} affected_time_range={rand(1,6)}h gap_reason={pick(['pipeline_lag','source_outage','schema_mismatch'])} gap_start_epoch={int(time.time())-rand(3600,21600)} affected_events_estimated={rand(1000,1000000)} backfill_job_queued=true",
    ],
    "checkout-service": [
        lambda: f"Payment provider response slow | provider={pick(['stripe','adyen','braintree'])} p99_ms={ms(2000,8000)} timeout_threshold_ms=5000 checkout_id=chk_{secrets.token_hex(8)} user_id={uid()} cart_value={amount()} {pick(CURRENCIES)} checkout_age_seconds={rand(30,1200)} abandon_risk=high",
        lambda: f"Session expiry warning | checkout_id=chk_{secrets.token_hex(8)} user_id={uid()} session_ttl_seconds=1800 remaining_seconds={rand(60,300)} cart_value={amount()} {pick(CURRENCIES)} items={rand(1,8)} extension_attempted=true extension_granted={pick(['true','false'])}",
    ],
    "billing-service": [
        lambda: f"Dunning cycle initiated | customer_id={uid()} subscription_id=sub_{secrets.token_hex(8)} invoice_id=inv_{secrets.token_hex(8)} amount_due={amount()} {pick(CURRENCIES)} days_past_due={rand(1,7)} dunning_step={rand(1,4)} next_action={pick(['email_reminder','sms_reminder','service_suspension','cancel'])} next_action_in_days={rand(1,5)}",
        lambda: f"Payment method expiring | customer_id={uid()} card_brand={pick(CARD_BRANDS)} last4={rand(1000,9999)} expires={rand(1,12):02d}/{rand(25,26)} subscriptions_at_risk={rand(1,5)} total_monthly_value={amount()} {pick(CURRENCIES)} days_until_expiry={rand(1,30)} update_link_sent=true",
    ],
    "gateway-service": [
        lambda: f"Circuit breaker approaching threshold | upstream={pick(list(SERVICE_ENDPOINTS.keys()))} state=closed failure_count={rand(3,8)} failure_threshold=10 failure_rate_pct={rand(30,80)} window_seconds=60 recovery_timeout_seconds=30 half_open_max_calls=5 last_failure_epoch={int(time.time())-rand(5,30)}",
        lambda: f"TLS certificate expiry approaching | domain={pick(['api.example.com','payments.example.com','auth.example.com'])} expires_epoch={int(time.time())+rand(86400,864000)} days_remaining={rand(1,10)} issuer={pick(['Let\\'s Encrypt','DigiCert','GlobalSign'])} auto_renew_configured={pick(['true','false'])} alert_sent=true",
    ],
    "messaging-service": [
        lambda: f"Consumer lag growing | group_id=grp_{secrets.token_hex(6)} topic={pick(QUEUE_NAMES)} total_lag_records={rand(1000,1000000)} lag_per_partition_max={rand(1000,100000)} consume_rate_per_sec={rand(100,5000)} produce_rate_per_sec={rand(200,6000)} eta_to_catch_up_seconds={rand(60,3600)} scaling_recommended=true",
        lambda: f"Dead letter queue accumulating | dlq_topic={pick(QUEUE_NAMES)}.dlq depth={rand(100,10000)} oldest_message_age_hours={rand(1,72)} failure_reason_breakdown=deserialization:{rand(10,50)}%,timeout:{rand(20,60)}%,exception:{rand(10,30)}% consumer_group=grp_{secrets.token_hex(6)} alerting_threshold_pct=80",
    ],
}

ERROR_TEMPLATES = {
    "payment-service": [
        lambda: f"Payment gateway timeout | transaction_id={tid()} user_id={uid()} amount={amount()} {pick(CURRENCIES)} gateway=stripe attempt={rand(1,3)} timeout_ms=5000 elapsed_ms={ms(5001,15000)} error=ETIMEDOUT gateway_status_page=operational fallback_gateway=adyen fallback_attempted={pick(['true','false'])} order_id={oid()} customer_impact=payment_failed",
        lambda: f"Card declined by issuer | transaction_id={tid()} user_id={uid()} amount={amount()} {pick(CURRENCIES)} card_brand={pick(CARD_BRANDS)} last4={rand(1000,9999)} decline_code={pick(['do_not_honor','insufficient_funds','card_velocity_exceeded','transaction_not_permitted','stolen_card'])} avs_result={pick(['N','X','U'])} cvv_result={pick(['N','P'])} retry_recommended=false",
        lambda: f"Duplicate transaction detected | transaction_id={tid()} user_id={uid()} idempotency_key={secrets.token_hex(12)} original_transaction_id={tid()} original_created_at_epoch={int(time.time())-rand(1,60)} amount={amount()} {pick(CURRENCIES)} action=reject error_code=DUPLICATE_TRANSACTION matching_field=idempotency_key",
        lambda: f"Fraud check service unavailable | transaction_id={tid()} user_id={uid()} amount={amount()} {pick(CURRENCIES)} fraud_service_error=connection_refused host=fraud-detection-svc.internal:{rand(8080,9090)} timeout_ms=3000 circuit_breaker_state=open fallback_policy=block_high_value blocked={pick(['true','false'])} revenue_at_risk={amount()}",
    ],
    "order-service": [
        lambda: f"Inventory reservation failed | order_id={oid()} user_id={uid()} sku={skuid()} requested_qty={rand(1,10)} available_qty=0 warehouse={pick(WAREHOUSES)} reservation_error=INSUFFICIENT_STOCK order_total={amount()} {pick(CURRENCIES)} rollback_triggered=true compensating_transactions=[payment_void,cart_restore] customer_notified=true",
        lambda: f"Database write timeout | order_id={oid()} user_id={uid()} operation=INSERT table=orders db_host={db_pool()}.internal query_hash={secrets.token_hex(8)} timeout_ms=5000 elapsed_ms={ms(5001,20000)} connection_pool_size={rand(20,100)} active_connections={rand(19,100)} deadlock_detected={pick(['true','false'])} retry_count={rand(1,3)} saga_compensated=true",
        lambda: f"Payment authorization expired | order_id={oid()} user_id={uid()} payment_id={pid()} authorized_amount={amount()} {pick(CURRENCIES)} authorization_epoch={int(time.time())-rand(3600,86400)} expiry_epoch={int(time.time())-rand(1,3600)} reauthorization_attempted=true reauth_result={pick(['declined','timeout'])} order_cancelled=true",
    ],
    "auth-service": [
        lambda: f"Session store unreachable | user_id={uid()} session_id={sid()} redis_host={cache_node()}.internal:{rand(6379,6380)} error=ECONNREFUSED retry_count={rand(1,5)} last_retry_ms={ms(100,5000)} fallback=jwt_stateless_mode degraded_features=[session_revocation,concurrent_session_limit] impact=reduced_security_posture",
        lambda: f"OAuth provider timeout | provider={pick(['google','github','microsoft','okta'])} operation={pick(['token_exchange','userinfo','introspect'])} timeout_ms=5000 elapsed_ms={ms(5001,15000)} user_id={uid()} redirect_uri=https://app.example.com/auth/callback error=provider_timeout retry_after_seconds={rand(10,60)} fallback_available=false login_failed=true",
        lambda: f"Account locked due to brute force | user_id={uid()} ip={ip()} failed_attempts={rand(10,50)} lock_duration_minutes={rand(15,60)} geo_country={pick(['RU','CN','KP','IR'])} user_agent='{pick(USER_AGENTS)}' security_event_id=evt_{secrets.token_hex(8)} alert_sent_to_security_team=true account_compromise_risk={pick(['medium','high'])}",
    ],
    "inventory-service": [
        lambda: f"Database deadlock on reservation | sku={skuid()} warehouse={pick(WAREHOUSES)} order_ids_involved=[{oid()},{oid()}] deadlock_cycle_detected=true victim_transaction={tid()} winner_transaction={tid()} retry_attempt={rand(1,5)} total_wait_ms={ms(500,5000)} deadlock_graph=circular_wait resolution=victim_rollback",
        lambda: f"Warehouse API connection failed | warehouse={pick(WAREHOUSES)} wms_host=wms-{pick(['east','west','eu'])}.internal:{rand(8080,9090)} error={pick(['ECONNREFUSED','ETIMEDOUT','ENOTFOUND'])} retry_count={rand(3,5)} backoff_ms=[100,200,400,800,1600] total_elapsed_ms={ms(2000,10000)} circuit_breaker_opened=true fallback=cached_stock_levels stale_data_age_minutes={rand(5,60)}",
        lambda: f"SKU not found across all warehouses | sku={skuid()} warehouses_checked=[{','.join(random.sample(WAREHOUSES,min(3,len(WAREHOUSES))))}] order_id={oid()} user_id={uid()} catalog_exists=true catalog_last_updated_epoch={int(time.time())-rand(3600,86400)} wms_sync_lag_suspected=true escalated_to_ops=true",
    ],
    "notification-service": [
        lambda: f"All email providers failed | message_id=msg_{secrets.token_hex(10)} user_id={uid()} template=order_confirmation providers_attempted=[{','.join(random.sample(EMAIL_PROVS,min(3,len(EMAIL_PROVS))))}] errors=[timeout,auth_failure,rate_limited] retry_queue_enqueued=true retry_after_seconds={rand(60,600)} dead_letter_after_attempts=5 current_attempt={rand(3,5)}",
        lambda: f"Template rendering failed | template=order_{pick(['confirmation','shipped','refunded','cancelled'])} user_id={uid()} message_id=msg_{secrets.token_hex(10)} template_engine=handlebars error=missing_partial partial='{pick(['header','footer','product_card','address_block'])}' template_version=v{rand(1,10)} fallback_to_plain_text={pick(['true','false'])} rendering_ms={ms(50,500)}",
    ],
    "api-gateway": [
        lambda: f"All upstream nodes unhealthy | upstream={pick(list(SERVICE_ENDPOINTS.keys()))} healthy_nodes=0 total_nodes={rand(3,8)} failing_nodes=[{','.join([f'10.0.{rand(1,4)}.{rand(1,254)}' for _ in range(rand(2,4))])}] failure_reasons=[tcp_refused,http_503] circuit_breaker_opened=true requests_rejected_last_minute={rand(100,5000)} client_error_code=503 fallback_response=cached_{pick(['true','false'])}",
        lambda: f"Request timeout before upstream response | method={pick(['POST','GET','PUT'])} path=/api/v{rand(1,3)}/{pick(['checkout','payment','orders'])}/{secrets.token_hex(4)} upstream={pick(list(SERVICE_ENDPOINTS.keys()))} timeout_ms=30000 elapsed_ms={ms(30001,60000)} user_id={uid()} retry_safe={pick(['false','true'])} request_id=req_{secrets.token_hex(8)} client_ip={ip()}",
    ],
    "catalog-service": [
        lambda: f"Search service unavailable | user_id={uid()} query='{pick(['shoes','laptop','coffee'])}' search_host=search-service.internal:{rand(9200,9201)} error=ECONNREFUSED circuit_breaker_state=open fallback=elasticsearch_backup fallback_available={pick(['true','false'])} affected_endpoints=[/v1/products/search,/v1/search/suggest] degraded_mode=keyword_only",
        lambda: f"Index corruption detected | index={pick(SEARCH_IDXS)} shard={rand(0,11)} corrupted_segments={rand(1,10)} affected_documents_estimated={rand(1000,50000)} corruption_type={pick(['checksum_mismatch','file_truncation','mapping_inconsistency'])} recovery_action={pick(['restore_from_snapshot','force_merge','reindex'])} snapshot_epoch={int(time.time())-rand(3600,86400)} data_loss_risk=low",
    ],
    "shipping-service": [
        lambda: f"Carrier API down | carrier={pick(CARRIERS)} operation={pick(['create_shipment','get_rates','print_label','track'])} error={pick(['ECONNREFUSED','HTTP_503','API_KEY_INVALID'])} retry_count={rand(3,5)} total_elapsed_ms={ms(5000,30000)} shipments_queued_for_retry={rand(10,200)} estimated_recovery_minutes={rand(5,60)} fallback_carrier={pick(CARRIERS)} fallback_activated={pick(['true','false'])}",
        lambda: f"Invalid address — label generation failed | shipment_id=ship_{secrets.token_hex(8)} order_id={oid()} carrier={pick(CARRIERS)} validation_errors=[{','.join(random.sample(['invalid_zip','unrecognized_street','missing_suite','invalid_state_code'],rand(1,3)))}] address_correction_suggested={pick(['true','false'])} customer_notified=true support_ticket_created=TKT-{rand(10000,99999)}",
    ],
    "search-service": [
        lambda: f"Index unavailable | index={pick(SEARCH_IDXS)} shard_failures=[shard-{rand(0,5)},shard-{rand(6,11)}] red_shards={rand(1,6)} yellow_shards={rand(0,4)} cluster_status=red primary_unassigned={rand(1,6)} node_count={rand(3,9)} min_required_nodes=3 recovery_action=await_node_rejoin estimated_recovery_minutes={rand(5,30)}",
        lambda: f"Query parse exception | query_string='{pick(['color:red AND (size:L OR size:XL)','brand:Nike && price:[50 TO 200]','category:electronics NOT brand:unknown'])}' index={pick(SEARCH_IDXS)} error=query_shard_exception root_cause=failed_to_parse_query user_id={uid()} request_id=req_{secrets.token_hex(8)} fallback_query_executed={pick(['true','false'])}",
    ],
    "fraud-detection": [
        lambda: f"ML model inference failed | model={pick(ML_MODELS)} transaction_id={tid()} user_id={uid()} error={pick(['model_file_not_found','feature_vector_shape_mismatch','onnx_runtime_exception','gpu_oom'])} inference_timeout_ms=200 elapsed_ms={ms(201,5000)} fallback_model={pick(['rule_engine_only','legacy_lr_v1'])} fallback_activated=true impact=reduced_fraud_detection_accuracy",
        lambda: f"Rules engine timeout | transaction_id={tid()} user_id={uid()} rules_evaluated={rand(5,50)} total_rules={rand(100,300)} timeout_ms=500 elapsed_ms={ms(501,2000)} timed_out_rules=[rule_{rand(100,999)},rule_{rand(100,999)}] decision_made_with_partial_rules=true decision=review risk_increased_due_to_timeout=true",
    ],
    "analytics-service": [
        lambda: f"Pipeline failure | pipeline=kinesis_ingest stage={pick(['deserialization','enrichment','schema_validation','storage_write'])} error={pick(['SchemaRegistryUnavailable','S3PutObjectFailed','KinesisThrottledException','SparkOutOfMemoryError'])} records_failed={rand(100,100000)} checkpoint_epoch={int(time.time())-rand(300,3600)} recovery_action={pick(['restart_from_checkpoint','skip_and_dlq','manual_intervention'])} data_loss_risk={pick(['none','low','medium'])}",
        lambda: f"Storage write failed | store={pick(['s3','bigquery','clickhouse','redshift'])} table={pick(['events','sessions','orders_fact','users_dim'])} records_attempted={rand(1000,100000)} records_failed={rand(1000,100000)} error={pick(['AccessDenied','QuotaExceeded','NetworkError','SchemaEvolutionConflict'])} retry_count={rand(1,5)} dead_lettered={pick(['true','false'])} pipeline_paused=true",
    ],
    "checkout-service": [
        lambda: f"Session expired during checkout | checkout_id=chk_{secrets.token_hex(8)} user_id={uid()} session_age_seconds={rand(1800,7200)} cart_value={amount()} {pick(CURRENCIES)} items={rand(1,8)} payment_captured=false inventory_released=true revenue_lost={amount()} session_extension_failed=true abandonment_event_fired=true",
        lambda: f"Payment service unavailable during checkout | checkout_id=chk_{secrets.token_hex(8)} user_id={uid()} payment_host=payment-service.internal:{rand(8080,9090)} error=ECONNREFUSED cart_value={amount()} {pick(CURRENCIES)} retry_count={rand(1,3)} fallback_payment_provider=none checkout_abandoned=true circuit_breaker_state=open",
    ],
    "billing-service": [
        lambda: f"Retry exhausted on invoice | invoice_id=inv_{secrets.token_hex(8)} customer_id={uid()} subscription_id=sub_{secrets.token_hex(8)} amount_due={amount()} {pick(CURRENCIES)} attempt_count={rand(4,6)} last_failure_code={pick(['card_declined','insufficient_funds','card_expired','do_not_honor'])} days_past_due={rand(7,30)} next_action=service_suspension suspension_scheduled_epoch={int(time.time())+rand(86400,259200)} revenue_at_risk={amount()}",
        lambda: f"Invoice generation failed | customer_id={uid()} subscription_id=sub_{secrets.token_hex(8)} billing_period_start={int(time.time())-2592000} error={pick(['template_render_timeout','pdf_service_unavailable','tax_api_timeout','line_item_calculation_overflow'])} retry_count={rand(1,3)} manual_review_required=true support_case=BILL-{rand(10000,99999)}",
    ],
    "gateway-service": [
        lambda: f"Certificate expired — TLS handshake failing | domain={pick(['api.example.com','payments.example.com','auth.example.com'])} expired_epoch={int(time.time())-rand(3600,86400)} issuer={pick(['Let\\'s Encrypt','DigiCert'])} error=SSL_CERTIFICATE_EXPIRED affected_routes={rand(5,50)} client_errors_per_minute={rand(100,5000)} cert_renewed={pick(['true','false'])} rollout_pending={pick(['true','false'])}",
        lambda: f"Auth service unreachable — all requests failing authentication | auth_host=auth-service.internal:{rand(8080,9090)} error=ECONNREFUSED circuit_breaker=open affected_routes={rand(10,100)} requests_rejected_per_minute={rand(500,10000)} emergency_bypass_policy={pick(['none','allowlist_only','jwt_local_verify'])} bypass_activated={pick(['true','false'])} incident_id=INC-{rand(1000,9999)}",
    ],
    "messaging-service": [
        lambda: f"Broker unreachable | broker={pick(['kafka-0','kafka-1','kafka-2'])}.internal:{rand(9092,9094)} error=ECONNREFUSED bootstrap_servers_tried={rand(1,3)} last_successful_connection_epoch={int(time.time())-rand(60,3600)} producer_id=prod_{secrets.token_hex(6)} messages_in_send_buffer={rand(100,10000)} durability_risk={pick(['low','medium','high'])} reconnect_backoff_ms={ms(100,5000)}",
        lambda: f"Consumer crash and partition rebalance | group_id=grp_{secrets.token_hex(6)} topic={pick(QUEUE_NAMES)} crashed_consumer=consumer-{rand(0,10)} partitions_orphaned={rand(1,12)} rebalance_triggered=true rebalance_duration_ms={ms(500,5000)} lag_increase_during_rebalance={rand(1000,100000)} root_cause={pick(['OOM_killed','pod_evicted','network_partition','liveness_probe_failed'])}",
    ],
}

DEBUG_TEMPLATES = [
    lambda: f"Cache lookup | key={pick(['product','user','session','cart','rate_limit'])}:{secrets.token_hex(8)} node={cache_node()} result={pick(['hit','hit','hit','miss'])} ttl_remaining_seconds={rand(0,3600)} size_bytes={rand(50,8192)} serialization_format={pick(['json','msgpack','protobuf'])}",
    lambda: f"SQL query executed | db={db_pool()} query_hash={secrets.token_hex(8)} duration_ms={ms(1,500)} rows_returned={rand(0,1000)} rows_scanned={rand(0,50000)} index_used={pick(['PRIMARY','idx_user_id','idx_created_at','idx_status','full_scan'])} query_plan=IndexScan table={pick(['orders','payments','users','inventory','sessions'])} connection_id={rand(1,1000)}",
    lambda: f"HTTP outbound call | method={pick(['GET','POST','PUT'])} url=http://{pick(list(SERVICE_ENDPOINTS.keys()))}.internal/{pick(['health','v1/check','v1/validate'])} status={pick([200,200,200,201,204])} duration_ms={ms(2,300)} retried=false connection_reused=true tls=false http_version={pick(['HTTP/1.1','HTTP/2'])}",
    lambda: f"Span completed | trace_id={secrets.token_hex(16)} span_id={secrets.token_hex(8)} parent_span_id={secrets.token_hex(8)} operation={pick(['db.query','cache.get','http.request','queue.publish','grpc.call'])} duration_ms={ms(1,500)} status={pick(['ok','ok','ok','error'])} service={pick([s[0] for s in SERVICES])}",
    lambda: f"Config value read | key={pick(['feature_flags.new_checkout','rate_limits.api_key','circuit_breaker.timeout_ms','cache.ttl_seconds','auth.token_expiry'])} value={pick(['true','false','5000','900','3600','0.95'])} source={pick(['consul','env_var','vault','remote_config'])} cache_age_ms={rand(0,60000)} namespace={pick(['production','global','service'])}",
    lambda: f"Lock acquired | lock_key={pick(['order','inventory','payment','session'])}:{secrets.token_hex(8)} lock_id={secrets.token_hex(12)} backend={pick(['redis','postgres_advisory','zookeeper'])} wait_time_ms={ms(0,200)} ttl_ms={rand(1000,30000)} owner=worker-{rand(0,63)} acquired_at_epoch={int(time.time())}",
    lambda: f"Middleware chain completed | route={pick(['/v1/orders','/v1/payments','/v1/auth/me','/v1/inventory'])} middlewares=[auth,rate_limit,request_id,logging,cors] total_middleware_ms={ms(1,50)} auth_ms={ms(1,20)} rate_limit_ms={ms(0,5)} logging_ms={ms(0,2)} request_id=req_{secrets.token_hex(8)}",
    lambda: f"gRPC call completed | service={pick(list(SERVICE_ENDPOINTS.keys()))} method={pick(['/grpc.health.v1.Health/Check','/order.v1.OrderService/CreateOrder','/payment.v1.PaymentService/Charge'])} status={pick(['OK','OK','OK','UNAVAILABLE','DEADLINE_EXCEEDED'])} duration_ms={ms(2,400)} attempt={rand(1,3)} deadline_remaining_ms={rand(100,5000)} bytes_sent={rand(50,4096)} bytes_received={rand(50,8192)}",
    lambda: f"Retry scheduled | operation={pick(['payment_capture','inventory_reserve','email_send','webhook_delivery'])} attempt={rand(2,5)} of {rand(5,10)} delay_ms={rand(100,30000)} backoff_strategy={pick(['exponential','linear','constant'])} jitter_ms={rand(0,1000)} job_id=job_{secrets.token_hex(8)} queue={pick(QUEUE_NAMES)}",
    lambda: f"Feature flag evaluated | flag={pick(['new_checkout_flow','split_payments','loyalty_points_v2','ai_recommendations','instant_refunds'])} user_id={uid()} result={pick(['enabled','disabled','disabled','disabled'])} rule_matched={pick(['percentage_rollout','user_segment','allowlist','default'])} rollout_pct={rand(0,100)} variant={pick(['control','treatment'])} evaluation_ms={ms(0,5)}",
    lambda: f"Webhook delivered | webhook_id=wh_{secrets.token_hex(8)} url=https://hooks.{pick(['slack.com','zapier.com','customer.io','segment.com'])}/services/{secrets.token_hex(10)} event={pick(['order.created','payment.succeeded','shipment.delivered','subscription.renewed'])} attempt={rand(1,3)} response_status={pick([200,200,200,200,429,500])} response_ms={ms(50,2000)} payload_bytes={rand(200,4096)}",
    lambda: f"Connection pool stats | pool={db_pool()} total={rand(20,100)} active={rand(5,80)} idle={rand(5,50)} waiting={rand(0,10)} max_wait_ms={ms(0,500)} checkout_ms_p99={ms(1,100)} overflow_count_1m={rand(0,5)} pool_created_epoch={int(time.time())-rand(3600,86400)}",
]

def get_message(level, svc):
    if level == "DEBUG":
        return pick(DEBUG_TEMPLATES)()
    templates = {
        "INFO":  INFO_TEMPLATES,
        "WARN":  WARN_TEMPLATES,
        "ERROR": ERROR_TEMPLATES,
    }.get(level, INFO_TEMPLATES)
    svc_templates = templates.get(svc)
    if not svc_templates:
        svc_templates = templates.get("api-gateway", [lambda: "Operation completed"])
    return pick(svc_templates)()

def get_level(env):
    r = rand(1, 100)
    if env == "prod":
        if r <= 2:  return "ERROR"
        if r <= 8:  return "WARN"
        if r <= 15: return "DEBUG"
        return "INFO"
    if env == "staging":
        if r <= 5:  return "ERROR"
        if r <= 15: return "WARN"
        if r <= 35: return "DEBUG"
        return "INFO"
    if r <= 10: return "ERROR"
    if r <= 25: return "WARN"
    if r <= 50: return "DEBUG"
    return "INFO"

def get_status(level):
    if level == "ERROR": return pick([400,401,403,404,409,422,429,500,502,503,504])
    if level == "WARN":  return pick([200,200,200,429,503])
    return pick([200,200,200,200,201,201,202,204])

def get_duration(level, endpoint):
    if any(x in endpoint for x in ["search","suggest"]):
        base = rand(50, 200)
    elif any(x in endpoint for x in ["charges","checkout","orders","payment"]):
        base = rand(150, 600)
    else:
        base = rand(20, 120)
    if level == "ERROR":                      base *= rand(3, 8)
    elif level == "WARN" and rand(1,3) == 1:  base *= 2
    if rand(1, 100) <= 2:                     base *= rand(5, 15)
    return base

def build_payload(svc, version, env, region, host, endpoint, status, duration, level, message, trace_id, request_id):
    method, route = endpoint.split(maxsplit=1)
    attrs = [
        {"key": "service.name",     "value": {"stringValue": svc}},
        {"key": "service.version",  "value": {"stringValue": version}},
        {"key": "env",              "value": {"stringValue": env}},
        {"key": "cloud.region",     "value": {"stringValue": region}},
        {"key": "host.name",        "value": {"stringValue": host}},
        {"key": "http.method",      "value": {"stringValue": method}},
        {"key": "http.route",       "value": {"stringValue": route}},
        {"key": "http.status_code", "value": {"intValue": status}},
        {"key": "duration_ms",      "value": {"intValue": duration}},
        {"key": "request.id",       "value": {"stringValue": request_id}},
    ]
    if level == "ERROR":
        attrs.append({"key": "error.code", "value": {"stringValue": pick(["ECONNREFUSED","ETIMEDOUT","ENOTFOUND","E500","E503","E504"])}})

    return {
        "resourceLogs": [{
            "resource":  {"attributes": [{"key": "service.name", "value": {"stringValue": svc}}]},
            "scopeLogs": [{"scope": {"name": "log-gen"}, "logRecords": [{
                "timeUnixNano":   str(time.time_ns()),
                "severityNumber": {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}[level],
                "severityText":   level,
                "body":           {"stringValue": message},
                "attributes":     attrs,
                "traceId":        trace_id,
            }]}],
        }]
    }

def send(payload):
    data = json.dumps(payload).encode()
    req  = Request(f"http://{ENDPOINT}/v1/logs", data=data,
                   headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=5): pass
        return True
    except URLError as e:
        print(f"  ⚠ send failed: {e}", file=sys.stderr)
        return False

def run_log(i, loop):
    svc, version = pick(SERVICES)
    env          = pick(ENVS)
    region       = pick(REGIONS)
    host         = f"{svc}-{secrets.token_hex(4)}"
    level        = get_level(env)
    endpoint     = pick(SERVICE_ENDPOINTS.get(svc, ["GET /v1/health"]))
    message      = get_message(level, svc)
    status       = get_status(level)
    duration     = get_duration(level, endpoint)
    trace_id     = secrets.token_hex(16)
    request_id   = f"req_{secrets.token_hex(4)}"

    payload = build_payload(svc, version, env, region, host, endpoint,
                            status, duration, level, message, trace_id, request_id)
    ok   = send(payload)
    mark = {"INFO": "✓", "WARN": "⚠", "ERROR": "✗", "DEBUG": "·"}.get(level, "·")
    print(f"[loop={loop} {i:>4}] {mark} {level:<5} | {svc:<24} | {endpoint:<40} | {duration}ms | {status} | {message}")

def run_loop(loop_num):
    print(f"\n{'='*60}")
    print(f"Loop {loop_num} — {COUNT} logs | parallel={PARALLEL}")
    print(f"{'='*60}")
    sem     = threading.Semaphore(PARALLEL)
    threads = []

    def worker(i):
        with sem:
            run_log(i, loop_num)

    for i in range(1, COUNT + 1):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        t.start()
        threads.append(t)
        if DELAY > 0:
            time.sleep(DELAY)

    for t in threads:
        t.join()

    print(f"✅ Loop {loop_num} done")

print(f"{'='*60}")
print(f"OTLP Log Generator → http://{ENDPOINT}/v1/logs")
print(f"count={COUNT}  parallel={PARALLEL}  loops={'∞' if LOOPS == 0 else LOOPS}  delay={DELAY}s")
print(f"{'='*60}")

loop = 1
while True:
    run_loop(loop)
    if LOOPS != 0 and loop >= LOOPS:
        break
    loop += 1

print(f"\n{'='*60}")
print(f"✅ Done: {loop} loop(s) × {COUNT} logs")
print(f"{'='*60}")