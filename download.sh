#!/usr/bin/env bash
set -euo pipefail

REPO="observantio/watchdog"
INSTALL_DIR="${HOME}/observantio"
VERSION="${1:-}"
RESOLVED_VERSION=""
DOWNLOADER=""
COMPOSE_CMD=()

detect_arch() {
  local machine
  machine="$(uname -m)"
  case "$machine" in
    x86_64) printf 'amd64' ;;
    aarch64|arm64) printf 'arm64' ;;
    *) printf 'multi' ;;
  esac
}

ARCH="${2:-$(detect_arch)}"

usage() {
  cat <<'EOF'
Usage: bash download.sh [version] [arch]

Arguments:
  version   Optional release tag such as v0.0.3. Defaults to the latest GitHub release.
  arch      Optional asset architecture: amd64, arm64, or multi. Defaults to detected architecture.

Examples:
  bash download.sh
  bash download.sh v0.0.3
  bash download.sh v0.0.3 amd64
EOF
}

app_label() {
  if [[ -n "${RESOLVED_VERSION}" ]]; then
    printf '(Observantio %s)' "${RESOLVED_VERSION}"
  elif [[ -n "${VERSION}" ]]; then
    printf '(Observantio %s)' "${VERSION}"
  else
    printf '(Observantio)'
  fi
}

log() {
  printf '%s %s\n' "$(app_label)" "$*"
}

ok() {
  printf '%s ✓ %s\n' "$(app_label)" "$*"
}

warn() {
  printf '%s ! %s\n' "$(app_label)" "$*" >&2
}

fail() {
  printf '%s ERROR: %s\n' "$(app_label)" "$*" >&2
  exit 1
}

clear || true

printf '%s\n' \
"Starting installation..." \
"This script will download the latest release of Observantio from GitHub, extract it into:" \
"  ${INSTALL_DIR}" \
"and launch the included installer." \
"You can specify a version and architecture as arguments," \
"or run it without arguments to use the latest release and detected architecture." \
""

print_banner() {
  cat <<'EOF'


    ____  _                                     _   _       
   / __ \| |                                   | | (_)      
  | |  | | |__  ___  ___ _ ____   ____ _ _ __  | |_ _  ___  
  | |  | | '_ \/ __|/ _ \ '__\ \ / / _` | '_ \ | __| |/ _ \ 
  | |__| | |_) \__ \  __/ |   \ V / (_| | | | || |_| | (_) |
   \____/|_.__/|___/\___|_|    \_/ \__,_|_| |_| \__|_|\___/

  Please review the license terms at github.com/observantio/watchdog/blob/main/LICENSE
  Hope Observantio serves you well and encourages you to contribute back to the project!
  We also welcome feedback and suggestions for improvement. Also you may reach out to me on https://www.linkedin.com/in/stefan-kumarasinghe/
  if you have any questions or need assistance with the installation or usage of Observantio.



EOF
}

print_summary() {
  cat <<EOF
$(app_label) Repository : ${REPO}
$(app_label) Install dir: ${INSTALL_DIR}
$(app_label) Version    : ${RESOLVED_VERSION}
$(app_label) Arch       : ${ARCH}
EOF
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
    wget -qO "$dest" "$url"
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

  if ! docker info >/dev/null 2>&1; then
    if command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
      fail "Docker is only accessible via sudo on this host. Add your user to the docker group before continuing."
    fi
    fail "Docker is installed but not usable by the current user. Add your user to the docker group or configure non-interactive access first."
  fi

  local version_output major
  version_output="$(docker version --format '{{.Server.Version}}' 2>/dev/null)" || fail "Unable to determine Docker server version."
  major="$(printf '%s' "$version_output" | cut -d. -f1)"

  [[ "$major" =~ ^[0-9]+$ ]] || fail "Could not parse Docker version from: ${version_output}"
  (( major >= 18 )) || fail "Docker ${version_output} is too old. Version 18 or above is required."
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
    if sudo -n docker compose version >/dev/null 2>&1 || { command -v docker-compose >/dev/null 2>&1 && sudo -n docker-compose version >/dev/null 2>&1; }; then
      fail "Docker Compose is only accessible via sudo on this host. Add your user to the docker group before continuing."
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
  local candidate
  for candidate in "$root/install.sh" "$root/release/install.sh"; do
    if [[ -f "$candidate" ]]; then
      chmod +x "$candidate"
      printf '%s\n' "$candidate"
      return 0
    fi
  done
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

  print_banner

  pick_downloader
  ok "Downloader ready: ${DOWNLOADER}"

  require_docker_access
  ok "Docker is available"

  require_compose_access
  ok "Docker Compose is available"

  if [[ -z "$VERSION" ]]; then
    log "Resolving latest release"
    RESOLVED_VERSION="$(resolve_latest_version)"
  else
    RESOLVED_VERSION="$VERSION"
  fi

  local asset="observantio-${RESOLVED_VERSION}-linux-${ARCH}.tar.gz"
  local url="https://github.com/${REPO}/releases/download/${RESOLVED_VERSION}/${asset}"
  local archive_path="${INSTALL_DIR}/${asset}"
  local extract_dir="${INSTALL_DIR}/observantio-${RESOLVED_VERSION}-linux-${ARCH}"
  local install_script

  mkdir -p "$INSTALL_DIR"

  print_summary
  log "Preparing download"
  log "Asset: ${asset}"
  printf "\n"
  fetch_file "$url" "$archive_path" || fail "Failed to download ${url}"
  printf "\n"
  ok "Download complete"

  log "Extracting package"
  extract_asset "$archive_path" "$extract_dir"
  ok "Extraction complete"

  install_script="$(find_install_script "$extract_dir")" || fail "install.sh was not found in the extracted release"

  for helper in restart.sh uninstall.sh; do
    [[ -f "$extract_dir/$helper" ]] && chmod +x "$extract_dir/$helper" || true
  done

  ok "Installer ready"
  log "Launching installer..."
  printf "\n"
  cd "$extract_dir"
  exec "$install_script"
}

main "$@"