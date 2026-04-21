#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
fi

set_env_key() {
  local key="$1"
  local value="$2"
  local tmp_file

  tmp_file="$(mktemp)"
  awk -F= -v k="$key" -v v="$value" '
    BEGIN { replaced=0 }
    $1 == k { print k "=" v; replaced=1; next }
    { print $0 }
    END { if (!replaced) print k "=" v }
  ' .env > "${tmp_file}"
  mv "${tmp_file}" .env
}

get_env_key() {
  local key="$1"
  if [[ ! -f ".env" ]]; then
    return 0
  fi
  awk -F= -v k="$key" '$1 == k { print substr($0, index($0, "=") + 1); exit }' .env
}

detect_host_cpus() {
  if command -v nproc >/dev/null 2>&1; then
    nproc
    return
  fi
  getconf _NPROCESSORS_ONLN
}

detect_host_memory_mb() {
  if [[ -r /proc/meminfo ]]; then
    awk '/MemTotal:/ { printf "%d\n", $2 / 1024 }' /proc/meminfo
    return
  fi

  local pages
  local page_size
  pages="$(getconf _PHYS_PAGES)"
  page_size="$(getconf PAGE_SIZE)"
  awk -v p="${pages}" -v s="${page_size}" 'BEGIN { printf "%d\n", (p * s) / 1024 / 1024 }'
}

clamp_int() {
  local value="$1"
  local min="$2"
  local max="$3"
  if (( value < min )); then
    echo "${min}"
  elif (( value > max )); then
    echo "${max}"
  else
    echo "${value}"
  fi
}

HOST_CPUS="$(detect_host_cpus)"
HOST_MEMORY_MB="$(detect_host_memory_mb)"
RESOURCE_PROFILE="$(get_env_key OBS_RESOURCE_PROFILE)"
RESOURCE_PROFILE="${RESOURCE_PROFILE:-auto}"

if [[ "${RESOURCE_PROFILE}" == "auto" ]]; then
  if (( HOST_CPUS <= 2 || HOST_MEMORY_MB <= 4096 )); then
    RESOURCE_PROFILE="tiny"
  elif (( HOST_CPUS <= 4 || HOST_MEMORY_MB <= 8192 )); then
    RESOURCE_PROFILE="small"
  elif (( HOST_CPUS <= 8 || HOST_MEMORY_MB <= 16384 )); then
    RESOURCE_PROFILE="medium"
  else
    RESOURCE_PROFILE="large"
  fi
fi

case "${RESOURCE_PROFILE}" in
  manual)
    LOKI_CPUS="$(get_env_key LOKI_CPUS)"
    LOKI_CPUS="${LOKI_CPUS:-1.0}"
    LOKI_MEM_LIMIT="$(get_env_key LOKI_MEM_LIMIT)"
    LOKI_MEM_LIMIT="${LOKI_MEM_LIMIT:-768m}"
    LOKI_DEPLOY_RESERVATION_CPUS="$(get_env_key LOKI_DEPLOY_RESERVATION_CPUS)"
    LOKI_DEPLOY_RESERVATION_CPUS="${LOKI_DEPLOY_RESERVATION_CPUS:-0.25}"
    LOKI_DEPLOY_RESERVATION_MEMORY="$(get_env_key LOKI_DEPLOY_RESERVATION_MEMORY)"
    LOKI_DEPLOY_RESERVATION_MEMORY="${LOKI_DEPLOY_RESERVATION_MEMORY:-256M}"
    TEMPO_CPUS="$(get_env_key TEMPO_CPUS)"
    TEMPO_CPUS="${TEMPO_CPUS:-1.0}"
    TEMPO_MEM_LIMIT="$(get_env_key TEMPO_MEM_LIMIT)"
    TEMPO_MEM_LIMIT="${TEMPO_MEM_LIMIT:-768m}"
    TEMPO_DEPLOY_RESERVATION_CPUS="$(get_env_key TEMPO_DEPLOY_RESERVATION_CPUS)"
    TEMPO_DEPLOY_RESERVATION_CPUS="${TEMPO_DEPLOY_RESERVATION_CPUS:-0.25}"
    TEMPO_DEPLOY_RESERVATION_MEMORY="$(get_env_key TEMPO_DEPLOY_RESERVATION_MEMORY)"
    TEMPO_DEPLOY_RESERVATION_MEMORY="${TEMPO_DEPLOY_RESERVATION_MEMORY:-256M}"
    MIMIR_CPUS="$(get_env_key MIMIR_CPUS)"
    MIMIR_CPUS="${MIMIR_CPUS:-1.5}"
    MIMIR_MEM_LIMIT="$(get_env_key MIMIR_MEM_LIMIT)"
    MIMIR_MEM_LIMIT="${MIMIR_MEM_LIMIT:-1536m}"
    MIMIR_DEPLOY_RESERVATION_CPUS="$(get_env_key MIMIR_DEPLOY_RESERVATION_CPUS)"
    MIMIR_DEPLOY_RESERVATION_CPUS="${MIMIR_DEPLOY_RESERVATION_CPUS:-0.25}"
    MIMIR_DEPLOY_RESERVATION_MEMORY="$(get_env_key MIMIR_DEPLOY_RESERVATION_MEMORY)"
    MIMIR_DEPLOY_RESERVATION_MEMORY="${MIMIR_DEPLOY_RESERVATION_MEMORY:-256M}"
    ;;
  tiny)
    LOKI_CPUS="0.50"
    LOKI_MEM_LIMIT="512m"
    LOKI_DEPLOY_RESERVATION_CPUS="0.25"
    LOKI_DEPLOY_RESERVATION_MEMORY="192M"
    TEMPO_CPUS="0.50"
    TEMPO_MEM_LIMIT="512m"
    TEMPO_DEPLOY_RESERVATION_CPUS="0.25"
    TEMPO_DEPLOY_RESERVATION_MEMORY="192M"
    MIMIR_CPUS="0.75"
    MIMIR_MEM_LIMIT="1024m"
    MIMIR_DEPLOY_RESERVATION_CPUS="0.25"
    MIMIR_DEPLOY_RESERVATION_MEMORY="256M"
    ;;
  small)
    LOKI_CPUS="0.75"
    LOKI_MEM_LIMIT="640m"
    LOKI_DEPLOY_RESERVATION_CPUS="0.25"
    LOKI_DEPLOY_RESERVATION_MEMORY="256M"
    TEMPO_CPUS="0.75"
    TEMPO_MEM_LIMIT="640m"
    TEMPO_DEPLOY_RESERVATION_CPUS="0.25"
    TEMPO_DEPLOY_RESERVATION_MEMORY="256M"
    MIMIR_CPUS="1.00"
    MIMIR_MEM_LIMIT="1280m"
    MIMIR_DEPLOY_RESERVATION_CPUS="0.25"
    MIMIR_DEPLOY_RESERVATION_MEMORY="320M"
    ;;
  medium)
    LOKI_CPUS="1.0"
    LOKI_MEM_LIMIT="768m"
    LOKI_DEPLOY_RESERVATION_CPUS="0.25"
    LOKI_DEPLOY_RESERVATION_MEMORY="256M"
    TEMPO_CPUS="1.0"
    TEMPO_MEM_LIMIT="768m"
    TEMPO_DEPLOY_RESERVATION_CPUS="0.25"
    TEMPO_DEPLOY_RESERVATION_MEMORY="256M"
    MIMIR_CPUS="1.5"
    MIMIR_MEM_LIMIT="1536m"
    MIMIR_DEPLOY_RESERVATION_CPUS="0.25"
    MIMIR_DEPLOY_RESERVATION_MEMORY="256M"
    ;;
  large)
    LOKI_CPUS="1.5"
    LOKI_MEM_LIMIT="1024m"
    LOKI_DEPLOY_RESERVATION_CPUS="0.50"
    LOKI_DEPLOY_RESERVATION_MEMORY="384M"
    TEMPO_CPUS="1.5"
    TEMPO_MEM_LIMIT="1024m"
    TEMPO_DEPLOY_RESERVATION_CPUS="0.50"
    TEMPO_DEPLOY_RESERVATION_MEMORY="384M"
    MIMIR_CPUS="2.0"
    MIMIR_MEM_LIMIT="3072m"
    MIMIR_DEPLOY_RESERVATION_CPUS="0.50"
    MIMIR_DEPLOY_RESERVATION_MEMORY="512M"
    ;;
  *)
    echo "Unsupported OBS_RESOURCE_PROFILE=${RESOURCE_PROFILE}. Use auto, manual, tiny, small, medium, or large." >&2
    exit 1
    ;;
esac

LOKI_MEM_MB="${LOKI_MEM_LIMIT%m}"
TEMPO_MEM_MB="${TEMPO_MEM_LIMIT%m}"
MIMIR_MEM_MB="${MIMIR_MEM_LIMIT%m}"

mkdir -p configs/generated

if [[ "${RESOURCE_PROFILE}" == "tiny" ]]; then
  LOKI_INGESTION_RATE_MB=2
  LOKI_MAX_QUERY_PARALLELISM=1
  LOKI_RETENTION_DELETE_WORKER_COUNT=1
  TEMPO_INGESTION_RATE_LIMIT_BYTES=10000000
  TEMPO_INGESTION_BURST_SIZE_BYTES=20000000
  TEMPO_MAX_TRACES_PER_USER=25000
  MIMIR_MAX_GLOBAL_SERIES_PER_USER=100000
  MIMIR_INGESTION_RATE=10000
elif [[ "${RESOURCE_PROFILE}" == "small" ]]; then
  LOKI_INGESTION_RATE_MB=3
  LOKI_MAX_QUERY_PARALLELISM=2
  LOKI_RETENTION_DELETE_WORKER_COUNT=2
  TEMPO_INGESTION_RATE_LIMIT_BYTES=15000000
  TEMPO_INGESTION_BURST_SIZE_BYTES=30000000
  TEMPO_MAX_TRACES_PER_USER=40000
  MIMIR_MAX_GLOBAL_SERIES_PER_USER=175000
  MIMIR_INGESTION_RATE=20000
elif [[ "${RESOURCE_PROFILE}" == "large" ]]; then
  LOKI_INGESTION_RATE_MB=8
  LOKI_MAX_QUERY_PARALLELISM=4
  LOKI_RETENTION_DELETE_WORKER_COUNT=4
  TEMPO_INGESTION_RATE_LIMIT_BYTES=40000000
  TEMPO_INGESTION_BURST_SIZE_BYTES=80000000
  TEMPO_MAX_TRACES_PER_USER=100000
  MIMIR_MAX_GLOBAL_SERIES_PER_USER=500000
  MIMIR_INGESTION_RATE=60000
else
  LOKI_INGESTION_RATE_MB=4
  LOKI_MAX_QUERY_PARALLELISM=2
  LOKI_RETENTION_DELETE_WORKER_COUNT=3
  TEMPO_INGESTION_RATE_LIMIT_BYTES=20000000
  TEMPO_INGESTION_BURST_SIZE_BYTES=40000000
  TEMPO_MAX_TRACES_PER_USER=50000
  MIMIR_MAX_GLOBAL_SERIES_PER_USER=250000
  MIMIR_INGESTION_RATE=30000
fi

LOKI_CHUNK_CACHE_MB="$(clamp_int $(( LOKI_MEM_MB / 6 )) 64 256)"
LOKI_RESULTS_CACHE_MB="$(clamp_int $(( LOKI_MEM_MB / 6 )) 64 256)"
LOKI_WAL_REPLAY_MEMORY_MB="$(clamp_int $(( LOKI_MEM_MB / 3 )) 128 512)"
LOKI_INGESTION_BURST_SIZE_MB=$(( LOKI_INGESTION_RATE_MB * 2 ))
MIMIR_INGESTION_BURST_SIZE=$(( MIMIR_INGESTION_RATE * 2 ))

LOKI_CONFIG_FILE="$(get_env_key LOKI_CONFIG_FILE)"
LOKI_CONFIG_FILE="${LOKI_CONFIG_FILE:-./configs/generated/loki.yaml}"
TEMPO_CONFIG_FILE="$(get_env_key TEMPO_CONFIG_FILE)"
TEMPO_CONFIG_FILE="${TEMPO_CONFIG_FILE:-./configs/generated/tempo.yaml}"
MIMIR_CONFIG_FILE="$(get_env_key MIMIR_CONFIG_FILE)"
MIMIR_CONFIG_FILE="${MIMIR_CONFIG_FILE:-./configs/generated/mimir.yaml}"

for CONFIG_FILE in "${LOKI_CONFIG_FILE}" "${TEMPO_CONFIG_FILE}" "${MIMIR_CONFIG_FILE}"; do
  if [ -d "${CONFIG_FILE}" ]; then
    rm -rf "${CONFIG_FILE}"
  fi
  mkdir -p "$(dirname "${CONFIG_FILE}")"
  if [ "${CONFIG_FILE#./}" != "${CONFIG_FILE}" ]; then
    CONFIG_FILE_NO_DOT=${CONFIG_FILE#./}
  else
    CONFIG_FILE_NO_DOT=${CONFIG_FILE}
  fi
  touch "${CONFIG_FILE_NO_DOT}"
done

cat > "${LOKI_CONFIG_FILE#./}" <<EOF
auth_enabled: true

server:
  http_listen_port: 3100
  grpc_listen_port: 9096
  log_level: warn
  grpc_server_max_recv_msg_size: 8388608
  grpc_server_max_send_msg_size: 8388608

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

storage_config:
  tsdb_shipper:
    active_index_directory: /loki/tsdb-index
    cache_location: /loki/tsdb-cache
    cache_ttl: 24h
  filesystem:
    directory: /loki/chunks

chunk_store_config:
  chunk_cache_config:
    embedded_cache:
      enabled: true
      max_size_mb: ${LOKI_CHUNK_CACHE_MB}
      ttl: 1h

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: ${LOKI_RESULTS_CACHE_MB}
        ttl: 10m
  cache_results: true
  parallelise_shardable_queries: true

frontend:
  compress_responses: true
  log_queries_longer_than: 5s

ingester:
  chunk_idle_period: 5m
  chunk_retain_period: 30s
  max_chunk_age: 30m
  chunk_target_size: 1048576
  chunk_encoding: snappy
  flush_check_period: 1m
  wal:
    dir: /loki/wal
    enabled: true
    flush_on_shutdown: true
    checkpoint_duration: 5m
    replay_memory_ceiling: ${LOKI_WAL_REPLAY_MEMORY_MB}MB

limits_config:
  allow_structured_metadata: true
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  ingestion_rate_mb: ${LOKI_INGESTION_RATE_MB}
  ingestion_burst_size_mb: ${LOKI_INGESTION_BURST_SIZE_MB}
  max_streams_per_user: 1000
  max_global_streams_per_user: 1000
  per_stream_rate_limit: 1MB
  per_stream_rate_limit_burst: 4MB
  max_query_series: 2000
  max_entries_limit_per_query: 10000
  max_query_parallelism: ${LOKI_MAX_QUERY_PARALLELISM}
  query_timeout: 1m
  split_queries_by_interval: 15m
  retention_period: 168h
  volume_enabled: true

compactor:
  working_directory: /loki/compactor
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: ${LOKI_RETENTION_DELETE_WORKER_COUNT}
  delete_request_store: filesystem
EOF

cat > "${TEMPO_CONFIG_FILE#./}" <<EOF
server:
  http_listen_port: 3200

multitenancy_enabled: true

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318

ingester:
  max_block_duration: 30m

compactor:
  compaction:
    block_retention: 72h

storage:
  trace:
    backend: local
    wal:
      path: /tmp/tempo/wal
    local:
      path: /tmp/tempo/blocks

overrides:
  max_search_duration: 168h
  max_bytes_per_trace: 5000000
  ingestion_rate_limit_bytes: ${TEMPO_INGESTION_RATE_LIMIT_BYTES}
  ingestion_burst_size_bytes: ${TEMPO_INGESTION_BURST_SIZE_BYTES}
  max_traces_per_user: ${TEMPO_MAX_TRACES_PER_USER}
EOF

cat > "${MIMIR_CONFIG_FILE#./}" <<EOF
server:
  http_listen_port: 9009
  grpc_listen_port: 9095
  log_level: info

multitenancy_enabled: true

common:
  storage:
    backend: filesystem
    filesystem:
      dir: /data

memberlist:
  join_members:
    - mimir

blocks_storage:
  storage_prefix: blocks
  tsdb:
    dir: /data/tsdb
  bucket_store:
    sync_dir: /data/tsdb-sync

ruler:
  rule_path: /data/ruler
  alertmanager_url: http://alertmanager:9093

distributor:
  ring:
    kvstore:
      store: memberlist

ingester:
  ring:
    kvstore:
      store: memberlist
    replication_factor: 1

compactor:
  data_dir: /data/compactor
  sharding_ring:
    kvstore:
      store: memberlist

limits:
  max_global_series_per_user: ${MIMIR_MAX_GLOBAL_SERIES_PER_USER}
  ingestion_rate: ${MIMIR_INGESTION_RATE}
  ingestion_burst_size: ${MIMIR_INGESTION_BURST_SIZE}
  out_of_order_time_window: 5m
EOF

set_env_key "OBS_RESOURCE_PROFILE" "${RESOURCE_PROFILE}"
set_env_key "LOKI_CONFIG_FILE" "${LOKI_CONFIG_FILE}"
set_env_key "TEMPO_CONFIG_FILE" "${TEMPO_CONFIG_FILE}"
set_env_key "MIMIR_CONFIG_FILE" "${MIMIR_CONFIG_FILE}"
set_env_key "LOKI_CPUS" "${LOKI_CPUS}"
set_env_key "LOKI_MEM_LIMIT" "${LOKI_MEM_LIMIT}"
set_env_key "LOKI_DEPLOY_RESERVATION_CPUS" "${LOKI_DEPLOY_RESERVATION_CPUS}"
set_env_key "LOKI_DEPLOY_RESERVATION_MEMORY" "${LOKI_DEPLOY_RESERVATION_MEMORY}"
set_env_key "TEMPO_CPUS" "${TEMPO_CPUS}"
set_env_key "TEMPO_MEM_LIMIT" "${TEMPO_MEM_LIMIT}"
set_env_key "TEMPO_DEPLOY_RESERVATION_CPUS" "${TEMPO_DEPLOY_RESERVATION_CPUS}"
set_env_key "TEMPO_DEPLOY_RESERVATION_MEMORY" "${TEMPO_DEPLOY_RESERVATION_MEMORY}"
set_env_key "MIMIR_CPUS" "${MIMIR_CPUS}"
set_env_key "MIMIR_MEM_LIMIT" "${MIMIR_MEM_LIMIT}"
set_env_key "MIMIR_DEPLOY_RESERVATION_CPUS" "${MIMIR_DEPLOY_RESERVATION_CPUS}"
set_env_key "MIMIR_DEPLOY_RESERVATION_MEMORY" "${MIMIR_DEPLOY_RESERVATION_MEMORY}"
echo ""
echo "Rendered observability sizing profile:"
echo " - host_cpus=${HOST_CPUS}"
echo " - host_memory_mb=${HOST_MEMORY_MB}"
echo " - profile=${RESOURCE_PROFILE}"
echo " - loki=${LOKI_CPUS} CPU / ${LOKI_MEM_LIMIT}"
echo " - tempo=${TEMPO_CPUS} CPU / ${TEMPO_MEM_LIMIT}"
echo " - mimir=${MIMIR_CPUS} CPU / ${MIMIR_MEM_LIMIT}"
echo " - generated configs in configs/generated/"
