#!/usr/bin/env bash
set -euo pipefail

REPO="observantio/watchdog"
DEFAULT_INSTALL_DIR="${PWD}/observantio"
INSTALL_DIR="$DEFAULT_INSTALL_DIR"
VERSION=""
RESOLVED_VERSION=""
DOWNLOADER=""
COMPOSE_CMD=()
ARCH=""

USE_COLOR="0"
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  USE_COLOR="1"
fi
USE_EMOJI="0"
if [[ -t 1 && "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" == *"UTF-8"* ]]; then
  USE_EMOJI="1"
fi
if [[ "${OBSERVANTIO_EMOJI:-auto}" == "0" ]]; then
  USE_EMOJI="0"
elif [[ "${OBSERVANTIO_EMOJI:-auto}" == "1" ]]; then
  USE_EMOJI="1"
fi

C_RESET=$'\033[0m'
C_BOLD=$'\033[1m'
C_DIM=$'\033[2m'
C_CYAN=$'\033[36m'
C_GREEN=$'\033[32m'
C_YELLOW=$'\033[33m'
C_RED=$'\033[31m'
C_MAGENTA=$'\033[35m'

EM_INFO="i"
EM_OK="+"
EM_WARN="!"
EM_ERR="x"
if [[ "$USE_EMOJI" == "1" ]]; then
  EM_INFO="ⓘ"
  EM_OK="✔"
  EM_WARN="⚠"
  EM_ERR="✖"
fi

colorize() {
  local code="$1"
  shift
  if [[ "$USE_COLOR" == "1" ]]; then
    printf '%b%s%b' "$code" "$*" "$C_RESET"
  else
    printf '%s' "$*"
  fi
}

section() {
  printf '\n%s\n' "$(colorize "${C_BOLD}${C_MAGENTA}" "$*")"
  printf '%s\n' "$(colorize "${C_DIM}" "------------------------------------------------------------")"
}

info() {
  printf '%s %s %s\n' "$(colorize "$C_CYAN" "[INFO]")" "$EM_INFO" "$(colorize "$C_CYAN" "$*")"
}

ok() {
  printf '%s %s %s\n' "$(colorize "$C_GREEN" "[OK]")" "$EM_OK" "$(colorize "$C_GREEN" "$*")"
}

warn() {
  printf '%s %s %s\n' "$(colorize "$C_YELLOW" "[WARN]")" "$EM_WARN" "$(colorize "$C_YELLOW" "$*")"
}

err() {
  printf '%s %s %s\n' "$(colorize "$C_RED" "[ERROR]")" "$EM_ERR" "$(colorize "$C_RED" "$*")" >&2
}

usage() {
  cat <<'USAGE'
Usage:
  bash download.sh [version] [arch]
  bash download.sh [--version <tag>] [--arch <amd64|arm64|multi>] [--dir <path>]

Options:
  --version, -v   Release tag (example: v0.0.6). Defaults to latest release.
  --arch, -a      Asset architecture: amd64, arm64, or multi. Defaults to host-detected arch.
  --dir, -d       Install directory. Defaults to ./observantio in current directory.
  --help, -h      Show this help message.

Examples:
  bash download.sh
  bash download.sh v0.0.6
  bash download.sh v0.0.6 amd64
  bash download.sh --version v0.0.6 --arch arm64 --dir /opt/observantio
USAGE
}

print_banner() {
  printf '\n'
  printf '%s\n' "$(colorize "${C_MAGENTA}${C_BOLD}" "    ____  _                                     _   _")"
  printf '%s\n' "$(colorize "${C_MAGENTA}${C_BOLD}" "   / __ \\| |                                   | | (_)")"
  printf '%s\n' "$(colorize "${C_CYAN}${C_BOLD}" "  | |  | | |__  ___  ___ _ ____   ____ _ _ __  | |_ _  ___")"
  printf '%s\n' "$(colorize "${C_CYAN}${C_BOLD}" "  | |  | | '_ \\/ __|/ _ \\ '__\\ \\ / / _\` | '_ \\ | __| |/ _ \\")"
  printf '%s\n' "$(colorize "${C_GREEN}${C_BOLD}" "  | |__| | |_) \\__ \\  __/ |   \\ V / (_| | | | || |_| | (_) |")"
  printf '%s\n' "$(colorize "${C_GREEN}${C_BOLD}" "   \\____/|_.__/|___/\\___|_|    \\_/ \\__,_|_| |_| \\__|_|\\___/")"
  printf '\n'
}

detect_arch() {
  local machine
  machine="$(uname -m)"
  case "$machine" in
    x86_64) printf 'amd64' ;;
    aarch64|arm64) printf 'arm64' ;;
    *) printf 'multi' ;;
  esac
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    err "Missing required command: $1"
    exit 1
  }
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
  err "Need curl or wget to download release assets."
  exit 1
}

fetch_text() {
  local url="$1"
  if [[ "$DOWNLOADER" == "curl" ]]; then
    curl -fsSL --connect-timeout 10 --retry 3 --retry-delay 1 "$url"
  else
    wget -qO- --timeout=10 "$url"
  fi
}

fetch_file() {
  local url="$1"
  local dest="$2"
  if [[ "$DOWNLOADER" == "curl" ]]; then
    curl -fL --connect-timeout 10 --retry 3 --retry-delay 1 "$url" -o "$dest"
  else
    wget -O "$dest" "$url"
  fi
}

resolve_latest_version() {
  local api_url="https://api.github.com/repos/${REPO}/releases/latest"
  local body tag
  body="$(fetch_text "$api_url")" || {
    err "Unable to resolve the latest release from GitHub."
    exit 1
  }
  tag="$(printf '%s' "$body" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
  [[ -n "$tag" ]] || {
    err "GitHub response did not include a release tag."
    exit 1
  }
  printf '%s\n' "$tag"
}

require_docker_access() {
  require_command docker

  if ! docker info >/dev/null 2>&1; then
    if command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
      err "Docker is only accessible via sudo on this host. Add your user to the docker group."
      exit 1
    fi
    err "Docker is installed but not usable by the current user."
    exit 1
  fi

  local version_output major
  version_output="$(docker version --format '{{.Server.Version}}' 2>/dev/null)" || {
    err "Unable to determine Docker server version."
    exit 1
  }
  major="$(printf '%s' "$version_output" | cut -d. -f1)"
  [[ "$major" =~ ^[0-9]+$ ]] || {
    err "Could not parse Docker version from: ${version_output}"
    exit 1
  }
  (( major >= 18 )) || {
    err "Docker ${version_output} is too old. Version 18+ is required."
    exit 1
  }
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
      err "Docker Compose is only accessible via sudo. Add your user to the docker group first."
      exit 1
    fi
  fi

  err "Missing Docker Compose. Install the docker compose plugin or docker-compose first."
  exit 1
}

ensure_install_dir() {
  mkdir -p "$INSTALL_DIR" || {
    err "Failed to create install directory: ${INSTALL_DIR}"
    exit 1
  }
  [[ -d "$INSTALL_DIR" ]] || {
    err "Install path is not a directory: ${INSTALL_DIR}"
    exit 1
  }
  [[ -w "$INSTALL_DIR" ]] || {
    err "Install directory is not writable: ${INSTALL_DIR}"
    exit 1
  }
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

parse_args() {
  local positional=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      -v|--version)
        [[ $# -ge 2 ]] || { err "--version requires a value"; exit 1; }
        VERSION="$2"
        shift 2
        ;;
      -a|--arch)
        [[ $# -ge 2 ]] || { err "--arch requires a value"; exit 1; }
        ARCH="$2"
        shift 2
        ;;
      -d|--dir)
        [[ $# -ge 2 ]] || { err "--dir requires a value"; exit 1; }
        INSTALL_DIR="$2"
        shift 2
        ;;
      --)
        shift
        while [[ $# -gt 0 ]]; do
          positional+=("$1")
          shift
        done
        ;;
      -*)
        err "Unknown option: $1"
        usage >&2
        exit 1
        ;;
      *)
        positional+=("$1")
        shift
        ;;
    esac
  done

  if [[ "${#positional[@]}" -gt 2 ]]; then
    err "Too many positional arguments."
    usage >&2
    exit 1
  fi

  if [[ -z "$VERSION" && "${#positional[@]}" -ge 1 ]]; then
    VERSION="${positional[0]}"
  fi
  if [[ -z "$ARCH" && "${#positional[@]}" -ge 2 ]]; then
    ARCH="${positional[1]}"
  fi
}

print_summary() {
  printf '%s\n' "$(colorize "${C_BOLD}${C_CYAN}" "Download Summary")"
  printf '  %-14s %s\n' "Repository:" "$REPO"
  printf '  %-14s %s\n' "Version:" "$RESOLVED_VERSION"
  printf '  %-14s %s\n' "Architecture:" "$ARCH"
  printf '  %-14s %s\n' "Install dir:" "$INSTALL_DIR"
  printf '  %-14s %s\n' "Downloader:" "$DOWNLOADER"
}

main() {
  parse_args "$@"

  if [[ -z "$ARCH" ]]; then
    ARCH="$(detect_arch)"
  fi

  case "$ARCH" in
    amd64|arm64|multi) ;;
    *)
      err "Unsupported arch '$ARCH'. Use one of: amd64, arm64, multi."
      exit 1
      ;;
  esac

  print_banner
  section "Preflight Checks"

  pick_downloader
  ok "Downloader ready: ${DOWNLOADER}"

  require_command tar
  ok "Archive tool ready: tar"

  require_docker_access
  ok "Docker is available"

  require_compose_access
  ok "Docker Compose is available (${COMPOSE_CMD[*]})"

  ensure_install_dir
  ok "Install directory is writable"

  if [[ -z "$VERSION" ]]; then
    info "Resolving latest release tag from GitHub..."
    RESOLVED_VERSION="$(resolve_latest_version)"
    ok "Latest release resolved: ${RESOLVED_VERSION}"
  else
    RESOLVED_VERSION="$VERSION"
    info "Using requested release tag: ${RESOLVED_VERSION}"
  fi

  local asset="observantio-${RESOLVED_VERSION}-linux-${ARCH}.tar.gz"
  local url="https://github.com/${REPO}/releases/download/${RESOLVED_VERSION}/${asset}"
  local archive_path="${INSTALL_DIR}/${asset}"
  local extract_dir="${INSTALL_DIR}/observantio-${RESOLVED_VERSION}-linux-${ARCH}"
  local install_script

  section "Release Download"
  print_summary
  info "Downloading asset: ${asset}"
  if ! fetch_file "$url" "$archive_path"; then
    err "Download failed for ${url}"
    warn "Check if the version/arch exists. Example: bash download.sh v0.0.6 amd64"
    exit 1
  fi
  ok "Download complete"

  info "Extracting release bundle..."
  if ! extract_asset "$archive_path" "$extract_dir"; then
    err "Failed to extract ${archive_path}. The archive may be incomplete or invalid."
    exit 1
  fi
  ok "Extraction complete"

  install_script="$(find_install_script "$extract_dir")" || {
    err "install.sh was not found in extracted release bundle."
    exit 1
  }

  for helper in restart.sh uninstall.sh; do
    [[ -f "$extract_dir/$helper" ]] && chmod +x "$extract_dir/$helper" || true
    [[ -f "$extract_dir/release/$helper" ]] && chmod +x "$extract_dir/release/$helper" || true
  done

  section "Handoff"
  ok "Installer located: ${install_script}"
  info "Switching to release directory and launching installer..."

  cd "$extract_dir"
  exec "$install_script"
}

main "$@"
