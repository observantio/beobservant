#!/usr/bin/env bash
set -euo pipefail

REPO="observantio/watchdog"
INSTALL_DIR="${HOME}/observantio"
ARCH="${2:-multi}"
VERSION="${1:-}"

usage() {
  cat <<'USAGE'
Usage: bash download.sh [version] [arch]

Arguments:
  version   Optional release tag such as v0.0.2. Defaults to the latest GitHub release.
  arch      Optional asset architecture: amd64, arm64, or multi. Defaults to multi.
USAGE
}

log() {
  printf '[watchdog-download] %s\n' "$*"
}

fail() {
  printf '[watchdog-download] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

pick_downloader() {
  if command -v curl >/dev/null 2>&1; then
    DOWNLOADER="curl"
    return
  fi
  if command -v wget >/dev/null 2>&1; then
    DOWNLOADER="wget"
    return
  fi
  fail "Need curl or wget to download release assets"
}

fetch_text() {
  local url="$1"
  if [[ "$DOWNLOADER" == "curl" ]]; then
    curl -fsSL "$url"
  else
    wget -qO- "$url"
  fi
}

fetch_file() {
  local url="$1"
  local dest="$2"
  if [[ "$DOWNLOADER" == "curl" ]]; then
    curl -fL "$url" -o "$dest"
  else
    wget -O "$dest" "$url"
  fi
}

resolve_latest_version() {
  local api_url="https://api.github.com/repos/${REPO}/releases/latest"
  local body tag
  body="$(fetch_text "$api_url")" || fail "Unable to resolve the latest release from GitHub"
  tag="$(printf '%s' "$body" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
  [[ -n "$tag" ]] || fail "GitHub latest release response did not include a tag_name"
  printf '%s\n' "$tag"
}

require_docker_access() {
  require_command docker

  if docker info >/dev/null 2>&1; then
    DOCKER_PREFIX=()
    return
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    fail "Docker is only accessible via sudo on this host. The installer runs docker commands directly, so run this as a user in the docker group before continuing."
  fi

  fail "Docker is installed but not usable by the current user. Add your user to the docker group or configure non-interactive access first."
}

require_compose_access() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
    return
  fi

  if command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
    return
  fi

  if command -v sudo >/dev/null 2>&1; then
    if sudo -n docker compose version >/dev/null 2>&1; then
      fail "Docker Compose is only accessible via sudo on this host. The installer expects direct compose access, so run this as a user in the docker group before continuing."
    fi
    if command -v docker-compose >/dev/null 2>&1 && sudo -n docker-compose version >/dev/null 2>&1; then
      fail "docker-compose is only accessible via sudo on this host. The installer expects direct compose access, so run this as a user in the docker group before continuing."
    fi
  fi

  fail "Missing Docker Compose. Install the docker compose plugin or docker-compose first."
}

extract_asset() {
  local archive="$1"
  local target_dir="$2"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  tar -xzf "$archive" -C "$target_dir" --strip-components=1
}

find_install_script() {
  local root="$1"
  if [[ -x "$root/install.sh" ]]; then
    printf '%s\n' "$root/install.sh"
    return
  fi
  if [[ -f "$root/install.sh" ]]; then
    chmod +x "$root/install.sh"
    printf '%s\n' "$root/install.sh"
    return
  fi
  if [[ -x "$root/release/install.sh" ]]; then
    printf '%s\n' "$root/release/install.sh"
    return
  fi
  if [[ -f "$root/release/install.sh" ]]; then
    chmod +x "$root/release/install.sh"
    printf '%s\n' "$root/release/install.sh"
    return
  fi
  return 1
}

main() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi

  case "$ARCH" in
    amd64|arm64|multi) ;;
    *) fail "Unsupported arch '$ARCH'. Use one of: amd64, arm64, multi" ;;
  esac

  pick_downloader
  require_docker_access
  require_compose_access

  if [[ -z "$VERSION" ]]; then
    log "Resolving latest release for ${REPO}"
    VERSION="$(resolve_latest_version)"
  fi

  local asset="observantio-${VERSION}-linux-${ARCH}.tar.gz"
  local url="https://github.com/${REPO}/releases/download/${VERSION}/${asset}"
  local archive_path="${INSTALL_DIR}/${asset}"
  local extract_dir="${INSTALL_DIR}/observantio-${VERSION}-linux-${ARCH}"
  local install_script

  mkdir -p "$INSTALL_DIR"

  log "Using release ${VERSION} (${ARCH})"
  log "Downloading ${url}"
  fetch_file "$url" "$archive_path" || fail "Failed to download ${url}"

  log "Extracting release into ${extract_dir}"
  extract_asset "$archive_path" "$extract_dir"

  install_script="$(find_install_script "$extract_dir")" || fail "install.sh was not found in the extracted release"

  if [[ -f "$extract_dir/restart.sh" ]]; then
    chmod +x "$extract_dir/restart.sh" || true
  fi
  if [[ -f "$extract_dir/uninstall.sh" ]]; then
    chmod +x "$extract_dir/uninstall.sh" || true
  fi

  log "Starting installer"
  cd "$extract_dir"
  exec "$install_script"
}

main "$@"
