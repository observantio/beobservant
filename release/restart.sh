#!/usr/bin/env bash

# Observantio Release Installation Script
# This script sets up the environment for running Observantio from a release bundle.
# All Rights Reserved. (c) 2026 Stefan Kumarasinghe

set -euo pipefail

PURGE_VOLUMES=false

if [[ "${1:-}" == "--purge" ]]; then
  PURGE_VOLUMES=true
  shift
fi

if [[ $# -gt 0 ]]; then
  echo "Unknown option: $1" >&2
  echo "Usage: $0 [--purge]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/docker-compose.prod.yml" ]]; then
  ROOT_DIR="${SCRIPT_DIR}"
elif [[ -f "${SCRIPT_DIR}/../docker-compose.prod.yml" ]]; then
  ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
  echo "docker-compose.prod.yml not found next to this script or in its parent directory." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "docker compose (plugin) or docker-compose is required." >&2
  exit 1
fi

cd "${ROOT_DIR}"
RUN_OPTIMAL_SCRIPT="${ROOT_DIR}/scripts/run_optimal_config.sh"
if [[ ! -f "${RUN_OPTIMAL_SCRIPT}" ]]; then
  echo "Missing required script: ${RUN_OPTIMAL_SCRIPT}" >&2
  echo "This release bundle is incomplete. Re-download the release tarball." >&2
  exit 1
fi
chmod +x "${RUN_OPTIMAL_SCRIPT}"
"${RUN_OPTIMAL_SCRIPT}"
echo ""
if [[ "$PURGE_VOLUMES" == true ]]; then
  echo "Stopping stack and removing named volumes..."
  "${COMPOSE_CMD[@]}" -f docker-compose.prod.yml down --volumes --remove-orphans
else
  "${COMPOSE_CMD[@]}" -f docker-compose.prod.yml down
fi
echo ""
echo "Pulling latest configured images for this bundle..."
"${COMPOSE_CMD[@]}" -f docker-compose.prod.yml pull
echo ""
"${COMPOSE_CMD[@]}" -f docker-compose.prod.yml up -d
echo ""
echo "Observantio production stack restarted with updated configurations, please wait a few moments for all services to be up and running."
echo ""
