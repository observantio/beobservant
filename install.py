#!/usr/bin/env python3

"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import secrets
import string
import subprocess
import sys
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Sequence

REPO_URL = "https://github.com/observantio/watchdog.git"
RESOLVER_REPO_URL = "https://github.com/observantio/resolver.git"
NOTIFIER_REPO_URL = "https://github.com/observantio/notifier.git"

PASSWORD_RE = re.compile(r"^[A-Za-z0-9._@%+=:,/!+-]+$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


INTRO_TEXT = """\

IMPORTANT:
- Before you use this installer, you are agreeing to the LICENSE and NOTICE terms
  of the repositories and any included dependencies.
- This installer is NOT for production use. It is for experimentation/testing only.
- You are responsible for reviewing the code, licenses, and security posture.

If you do not agree, quit now.
"""

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
_locale_hint = (os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or os.environ.get("LANG") or "").upper()
USE_EMOJI = sys.stdout.isatty() and "UTF-8" in _locale_hint
_emoji_override = os.environ.get("OBSERVANTIO_EMOJI", "auto").strip().lower()
if _emoji_override == "0":
    USE_EMOJI = False
elif _emoji_override == "1":
    USE_EMOJI = True
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"

EM_INFO = "ⓘ" if USE_EMOJI else "i"
EM_OK = "✔" if USE_EMOJI else "+"
EM_WARN = "⚠" if USE_EMOJI else "!"
EM_ERR = "✖" if USE_EMOJI else "x"


def paint(text: str, code: str) -> str:
    if not USE_COLOR:
        return text
    return f"{code}{text}{RESET}"


def say(msg: str = "") -> None:
    print(msg)


def hr() -> None:
    print(paint("-" * 60, DIM))


def banner() -> None:
    say(paint("Observantio Installer", MAGENTA + BOLD))
    say(paint("A guided, friendly setup for local development", CYAN))



def info(msg: str) -> None:
    print(f"{paint('[INFO]', CYAN)} {EM_INFO} {paint(msg, CYAN)}")


def ok(msg: str) -> None:
    print(f"{paint('[OK]', GREEN)} {EM_OK} {paint(msg, GREEN)}")


def warn(msg: str) -> None:
    print(f"{paint('[WARN]', YELLOW)} {EM_WARN} {paint(msg, YELLOW)}")


def err(msg: str) -> None:
    print(f"{paint('[ERROR]', RED)} {EM_ERR} {paint(msg, RED)}")


def require_cmd(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise SystemExit(
            paint(
                f"Required command not found: {cmd}.\n"
                f"Please install {cmd} and ensure it is on your PATH before running this installer.",
                RED,
            )
        )


def run(cmd: Sequence[str], *, cwd: Path | None = None) -> None:
    try:
        subprocess.run(list(cmd), cwd=str(cwd) if cwd else None, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(paint(f"Command failed ({e.returncode}): {' '.join(map(str, e.cmd))}", RED)) from e


def detect_compose() -> List[str]:
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return ["docker", "compose"]
    except Exception:
        pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    raise SystemExit(paint("Docker Compose not found. Install Docker Desktop or docker compose plugin.", RED))


def require_docker_compose() -> List[str]:
    cmd = detect_compose()
    ok(f"Detected Docker Compose command: {' '.join(cmd)}")
    return cmd


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) < 3:
        raise ValueError(f"Invalid version format: {version}")
    major, minor, patch = (int(p) for p in parts[:3])
    return (major, minor, patch)


def require_buildx(required_version: str = "0.17.0") -> None:
    try:
        p = subprocess.run(
            ["docker", "buildx", "version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as e:
        raise SystemExit(
            paint(
                "Docker Buildx not found. Install Docker Buildx plugin and ensure it is available with `docker buildx`.",
                RED,
            )
        ) from e

    m = re.search(r"(\d+\.\d+\.\d+)", p.stdout or "")
    if not m:
        raise SystemExit(
            paint(f"Could not parse docker buildx version from: {p.stdout.strip()!r}.", RED)
        )
    found = m.group(1)

    try:
        found_ver = _parse_version(found)
        required_ver = _parse_version(required_version)
    except ValueError as exc:
        raise SystemExit(paint(f"Version parsing error: {exc}", RED)) from exc

    if found_ver < required_ver:
        raise SystemExit(
            paint(f"Docker Buildx version {required_version} or newer required, found {found}.", RED)
        )
    ok(f"Detected Docker Buildx version: {found}")


def ask_line(prompt: str) -> str:
    try:
        return input(paint(prompt, BOLD)).strip()
    except (KeyboardInterrupt, EOFError) as exc:
        raise UserCancelled from exc


class UserCancelled(BaseException):
    pass


def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    while True:
        ans = ask_line(f"{prompt} {suffix}: ").lower()
        if not ans:
            return default_yes
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        warn("Please answer yes or no.")


def ask_non_empty(prompt: str) -> str:
    while True:
        v = ask_line(f"{prompt}: ")
        if v:
            return v
        warn("Value cannot be empty.")


def ask_email(prompt: str) -> str:
    while True:
        v = ask_non_empty(prompt)
        if EMAIL_RE.fullmatch(v):
            return v
        warn("Invalid email. Example: user@example.com")


def ask_password() -> str:
    import getpass

    while True:
        try:
            p1 = getpass.getpass(paint("Admin password (letters, numbers, and safe punctuation): ", BOLD))
            p2 = getpass.getpass(paint("Confirm password: ", BOLD))
        except (KeyboardInterrupt, EOFError) as exc:
            raise UserCancelled from exc
        if not p1:
            warn("Password cannot be empty.")
            continue
        if len(p1) < 16:
            warn("Password must be at least 16 characters long.")
            continue
        if p1 != p2:
            warn("Passwords do not match.")
            continue
        if not PASSWORD_RE.fullmatch(p1):
            warn("Password must match: [A-Za-z0-9._@%+=:,/!+-]")
            continue
        return p1


def random_alnum(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def fernet_key() -> str:
    """Return a Fernet-compatible key, using cryptography when available."""

    try:
        from cryptography.fernet import Fernet  # pyright: ignore[reportMissingImports]

        return Fernet.generate_key().decode("ascii")
    except Exception:
        raw = secrets.token_bytes(32)
        return base64.urlsafe_b64encode(raw).decode("ascii")


def clone_repo_if_missing(url: str, dir_path: Path) -> None:
    if (dir_path / ".git").is_dir():
        ok(f"Found repository: {dir_path}")
        return

    if dir_path.exists():
        warn(f"Directory exists and is not a git repo: {dir_path}")
        if ask_yes_no(f"Remove and clone fresh '{dir_path}'?", default_yes=False):
            shutil.rmtree(dir_path)
        else:
            warn(f"Skipping clone for {dir_path}")
            return

    info(f"Cloning {url} -> {dir_path}")
    run(["git", "clone", url, str(dir_path)])
    ok(f"Cloned: {dir_path}")


def upsert_env(file_path: Path, key: str, value: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    key_prefix = f"{key}="

    lines: List[str] = []
    if file_path.exists():
        lines = file_path.read_text(encoding="utf-8").splitlines(True)

    out: List[str] = []
    done = False
    for line in lines:
        if line.startswith(key_prefix):
            out.append(f"{key}={value}\n")
            done = True
        else:
            out.append(line)

    if not done:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"{key}={value}\n")

    file_path.write_text("".join(out), encoding="utf-8")


def read_env_value(file_path: Path, key: str) -> str | None:
    if not file_path.exists():
        return None
    prefix = f"{key}="
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def upsert_env_if_missing(file_path: Path, key: str, value: str) -> None:
    if read_env_value(file_path, key) is None:
        upsert_env(file_path, key, value)


def choose_api_service_host(workdir: Path, compose_file: Path) -> str:
    try:
        text = compose_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "gateway"

    for candidate in ("watchdog", "gateway", "server", "api"):
        if re.search(rf"(?m)^\s*{re.escape(candidate)}\s*:\s*$", text):
            return candidate

    try:
        compose_cmd = detect_compose()
        p = subprocess.run(
            [*compose_cmd, "-f", str(compose_file), "--project-directory", str(workdir), "config", "--services"],
            cwd=str(workdir),
            check=True,
            capture_output=True,
            text=True,
        )
        services = [s.strip() for s in p.stdout.splitlines() if s.strip()]
        for candidate in ("watchdog", "gateway", "server", "api"):
            if candidate in services:
                return candidate
        if services:
            return services[0]
    except Exception:
        pass

    return "gateway"


def normalize_bool(v: str, default: str) -> str:
    s = v.strip().lower()
    if s in ("true", "1", "yes", "y", "on"):
        return "true"
    if s in ("false", "0", "no", "n", "off"):
        return "false"
    return default


def normalize_choice(v: str, allowed: Iterable[str], default: str) -> str:
    s = v.strip().lower()
    allowed_l = {a.lower() for a in allowed}
    return s if s in allowed_l else default


def prepare_env(
    env_file: Path,
    mode: str,
    admin_user: str,
    admin_email: str,
    admin_pass: str,
    api_service_host: str,
) -> None:
    if not env_file.exists():
        env_file.write_text("", encoding="utf-8")
        ok(f"Created: {env_file}")

    db_user = "watchdog"
    db_name = "watchdog"
    db_pass = admin_pass

    db_url = f"postgresql://{db_user}:{db_pass}@postgres:5432/{db_name}"
    bn_db_url = f"postgresql://{db_user}:{db_pass}@postgres:5432/watchdog_notified"
    bc_db_url = f"postgresql://{db_user}:{db_pass}@postgres:5432/watchdog_resolver"

    upsert_env(env_file, "APP_ENV", mode)
    upsert_env(env_file, "ENVIRONMENT", mode)

    upsert_env(env_file, "HOST", "0.0.0.0")
    upsert_env(env_file, "PORT", "4319")
    upsert_env(env_file, "LOG_LEVEL", "info")

    upsert_env(env_file, "POSTGRES_USER", db_user)
    upsert_env(env_file, "POSTGRES_PASSWORD", db_pass)
    upsert_env(env_file, "POSTGRES_DB", db_name)

    upsert_env(env_file, "DATABASE_URL", db_url)
    upsert_env(env_file, "NOTIFIER_DATABASE_URL", bn_db_url)
    upsert_env(env_file, "RESOLVER_DATABASE_URL", bc_db_url)
    upsert_env(env_file, "DB_AUTO_CREATE_SCHEMA", "true")

    upsert_env(env_file, "DEFAULT_ADMIN_BOOTSTRAP_ENABLED", "true")
    upsert_env(env_file, "DEFAULT_ADMIN_USERNAME", admin_user)
    upsert_env(env_file, "DEFAULT_ADMIN_PASSWORD", admin_pass)
    upsert_env(env_file, "DEFAULT_ADMIN_EMAIL", admin_email)
    upsert_env_if_missing(env_file, "DEFAULT_ADMIN_TENANT", "default")
    upsert_env_if_missing(env_file, "DEFAULT_ORG_ID", "default")
    upsert_env_if_missing(env_file, "MIMIR_TENANT_ID", "default")

    auth_provider = normalize_choice(
        read_env_value(env_file, "AUTH_PROVIDER") or "",
        ("local", "oidc", "keycloak"),
        "local",
    )
    upsert_env(env_file, "AUTH_PROVIDER", auth_provider)

    pw_flow = normalize_bool(read_env_value(env_file, "AUTH_PASSWORD_FLOW_ENABLED") or "", "true")
    upsert_env(env_file, "AUTH_PASSWORD_FLOW_ENABLED", pw_flow)

    upsert_env_if_missing(env_file, "JWT_ALGORITHM", "RS256")
    upsert_env_if_missing(env_file, "JWT_EXPIRATION_MINUTES", "1440")
    upsert_env(env_file, "JWT_AUTO_GENERATE_KEYS", "true")

    upsert_env_if_missing(env_file, "INBOUND_WEBHOOK_TOKEN", random_alnum(40))

    otlp_token = read_env_value(env_file, "DEFAULT_OTLP_TOKEN") or random_alnum(40)
    upsert_env(env_file, "DEFAULT_OTLP_TOKEN", otlp_token)
    upsert_env(env_file, "OTLP_INGEST_TOKEN", otlp_token)
    upsert_env(env_file, "OTEL_OTLP_TOKEN", otlp_token)
    upsert_env(env_file, "GATEWAY_STATUS_OTLP_TOKEN", otlp_token)

    upsert_env_if_missing(env_file, "GATEWAY_INTERNAL_SERVICE_TOKEN", random_alnum(40))

    bn_token = read_env_value(env_file, "NOTIFIER_SERVICE_TOKEN") or random_alnum(40)
    upsert_env(env_file, "NOTIFIER_SERVICE_TOKEN", bn_token)
    upsert_env(env_file, "NOTIFIER_EXPECTED_SERVICE_TOKEN", bn_token)
    bn_sign = read_env_value(env_file, "NOTIFIER_CONTEXT_SIGNING_KEY") or random_alnum(48)
    upsert_env(env_file, "NOTIFIER_CONTEXT_SIGNING_KEY", bn_sign)
    upsert_env(env_file, "NOTIFIER_CONTEXT_VERIFY_KEY", bn_sign)
    upsert_env(env_file, "NOTIFIER_URL", "http://notifier:4323")

    bc_token = read_env_value(env_file, "RESOLVER_SERVICE_TOKEN") or random_alnum(40)
    upsert_env(env_file, "RESOLVER_SERVICE_TOKEN", bc_token)
    upsert_env(env_file, "RESOLVER_EXPECTED_SERVICE_TOKEN", bc_token)
    bc_sign = read_env_value(env_file, "RESOLVER_CONTEXT_SIGNING_KEY") or random_alnum(48)
    upsert_env(env_file, "RESOLVER_CONTEXT_SIGNING_KEY", bc_sign)
    upsert_env(env_file, "RESOLVER_CONTEXT_VERIFY_KEY", bc_sign)
    upsert_env(env_file, "RESOLVER_URL", "http://resolver:4322")

    upsert_env(env_file, "GATEWAY_PORT", "4321")
    upsert_env(env_file, "GATEWAY_AUTH_API_URL", f"http://{api_service_host}:4319/api/internal/otlp/validate")
    upsert_env_if_missing(env_file, "GATEWAY_IP_ALLOWLIST", "")
    upsert_env(env_file, "GATEWAY_ALLOWLIST_FAIL_OPEN", "true")
    upsert_env_if_missing(env_file, "GATEWAY_TRUST_PROXY_HEADERS", "false")
    upsert_env(env_file, "RATE_LIMIT_BACKEND", "redis")
    upsert_env(env_file, "RATE_LIMIT_REDIS_URL", "redis://redis:6379/0")

    upsert_env_if_missing(env_file, "DATA_ENCRYPTION_KEY", fernet_key())
    upsert_env(env_file, "CORS_ORIGINS", "http://localhost:5173")

    upsert_env_if_missing(env_file, "GRAFANA_USERNAME", "admin")
    upsert_env(env_file, "GRAFANA_PASSWORD", admin_pass)
    upsert_env(env_file, "GF_SECURITY_ADMIN_PASSWORD", admin_pass)

    # Grafana auth proxy integration defaults
    upsert_env(env_file, "GF_SERVER_ROOT_URL", "http://localhost:8080/grafana/")
    upsert_env(env_file, "GF_SERVER_SERVE_FROM_SUB_PATH", "true")
    upsert_env(env_file, "GF_AUTH_PROXY_ENABLED", "true")
    upsert_env(env_file, "GF_AUTH_PROXY_HEADER_NAME", "X-WEBAUTH-USER")
    upsert_env(env_file, "GF_AUTH_PROXY_AUTO_SIGN_UP", "true")
    upsert_env(env_file, "GF_AUTH_PROXY_HEADERS", "Email:X-WEBAUTH-EMAIL Name:X-WEBAUTH-NAME Role:X-WEBAUTH-ROLE")
    upsert_env(env_file, "GF_AUTH_PROXY_WHITELIST", "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
    upsert_env(env_file, "GF_AUTH_ANONYMOUS_ENABLED", "false")
    upsert_env(env_file, "GF_AUTH_BASIC_ENABLED", "true")
    upsert_env(env_file, "GF_SECURITY_ALLOW_EMBEDDING", "true")
    upsert_env(env_file, "GF_USERS_ALLOW_SIGN_UP", "false")

    ok(f"Updated: {env_file}")


def print_urls() -> None:
    say()
    hr()
    say(paint("Access URLs", BOLD + CYAN))
    say(f"  {paint('UI:', CYAN)}            http://localhost:5173")
    say(f"  {paint('API:', CYAN)}           http://localhost:4319")
    say(f"  {paint('OTLP gateway:', CYAN)}   http://localhost:4320")
    say(f"  {paint('Grafana proxy:', CYAN)}  http://localhost:8080")
    hr()


def run_optimal_config(workdir: Path) -> None:
    script = workdir / "scripts" / "run_optimal_config.sh"
    if not script.is_file():
        warn(f"Optimal config script not found: {script}. Skipping config generation.")
        return

    info("Running optimal config generator")
    run(["bash", str(script)], cwd=workdir)
    ok("Generated optimal observability configs")


PORT_LABELS: dict[int, str] = {
    4319: "API",
    4320: "OTLP gateway",
    4323: "Notifier",
    5173: "UI",
    8080: "Grafana proxy",
}


def port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False


def preflight_host_ports() -> None:
    busy_ports = [(port, label) for port, label in PORT_LABELS.items() if port_is_listening(port)]
    if not busy_ports:
        return

    say()
    hr()
    err("Cannot start because one or more required host ports are already in use.")
    for port, label in busy_ports:
        warn(f"Port {port} ({label}) is busy.")
    say()
    say("Helpful checks:")
    say("  ss -ltnp 'sport = :4323'")
    say("  docker ps --format 'table {{.Names}}\t{{.Ports}}'")
    say("If this is another Observantio stack, stop it first and rerun the installer.")
    hr()
    raise SystemExit(1)


def backup_env_file(env_file: Path) -> Path | None:
    if not env_file.exists():
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_file = env_file.with_name(f"{env_file.name}.backup-{timestamp}")
    shutil.copy2(env_file, backup_file)
    ok(f"Backed up existing .env to {backup_file}")
    return backup_file


def start_stack(workdir: Path, compose_file: Path, compose_cmd: Sequence[str], *, action_label: str = "Started") -> None:
    if not compose_file.is_file():
        raise SystemExit(f"Compose file not found: {compose_file}")
    preflight_host_ports()
    run_optimal_config(workdir)
    info(f"{action_label} stack")
    run([*compose_cmd, "-f", str(compose_file), "--project-directory", str(workdir), "up", "-d", "--build"], cwd=workdir)
    ok(f"Stack {action_label.lower()}")
    print_urls()


def restart_stack(workdir: Path, compose_file: Path, compose_cmd: Sequence[str]) -> None:
    start_stack(workdir, compose_file, compose_cmd, action_label="Restarted")


def stop_stack(
    workdir: Path,
    compose_file: Path,
    compose_cmd: Sequence[str],
    *,
    purge_volumes: bool = False,
) -> None:
    if not compose_file.is_file():
        raise SystemExit(f"Compose file not found: {compose_file}")
    info("Stopping stack")
    down_cmd = [*compose_cmd, "-f", str(compose_file), "--project-directory", str(workdir), "down"]
    if purge_volumes:
        down_cmd.extend(["-v", "--remove-orphans"])
    run(down_cmd, cwd=workdir)
    if purge_volumes:
        ok("Stack stopped and volumes removed")
    else:
        ok("Stack stopped. Volumes preserved.")


def purge_stack(workdir: Path, compose_file: Path, compose_cmd: Sequence[str]) -> None:
    stop_stack(workdir, compose_file, compose_cmd, purge_volumes=True)


def resolve_existing_stack() -> tuple[Path, Path]:
    workdir = Path(ask_non_empty("Existing stack directory")).expanduser().resolve()
    compose_name = ask_line("Compose file name [docker-compose.yml]: ") or "docker-compose.yml"
    return workdir, workdir / compose_name


def choose_action_or_quit() -> str:
    while True:
        say()
        hr()
        say(paint("Choose action", BOLD + CYAN))
        say(f"  {paint('1)', CYAN)} start   (clone repos + build locally)")
        say(f"  {paint('2)', CYAN)} restart (reuse an existing stack)")
        say(f"  {paint('3)', CYAN)} stop    (keep volumes and data)")
        say(f"  {paint('4)', CYAN)} purge   (stop and remove volumes)")
        say(f"  {paint('q)', CYAN)} quit")
        hr()
        say()
        choice = ask_line(paint("Select 1, 2, 3, 4, or q: ", BOLD)).lower()
        if choice in ("q", "quit"):
            return "quit"
        if choice == "1":
            return "start"
        if choice == "2":
            return "restart"
        if choice == "3":
            return "stop"
        if choice == "4":
            return "purge"
        warn("Invalid selection.")


def setup_dev() -> Path:
    hr()
    say(paint("Dev setup", BOLD + MAGENTA))
    say("This will clone repositories into a directory you choose.")
    hr()

    while True:
        target = Path(ask_non_empty("Clone destination directory (will be created)")).expanduser().resolve()
        if not target.exists():
            break
        warn(f"Target already exists: {target}")
        if ask_yes_no("Override existing directory (delete and recreate)?", default_yes=False):
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            break
        warn("Please choose a different destination.")

    require_cmd("git")
    info("Cloning main repo")
    run(["git", "clone", REPO_URL, str(target)])
    ok(f"Cloned: {target}")

    info("Cloning dependent repos (if missing)")
    clone_repo_if_missing(RESOLVER_REPO_URL, target / "resolver")
    clone_repo_if_missing(NOTIFIER_REPO_URL, target / "notifier")
    return target


def require_acceptance() -> None:
    os.system("clear" if os.name != "nt" else "cls")
    banner()
    say(paint(INTRO_TEXT, CYAN))

    if not ask_yes_no("Do you agree to proceed under these terms?", default_yes=False):
        raise SystemExit(paint("Not accepted. Exiting. Sorry to see you go!", RED))



def main() -> int:
    try:
        require_acceptance()

        say()
        say(paint("Start a new development stack, restart an existing one, or stop/purge safely.", BOLD + CYAN))
        say()

        require_cmd("docker")
        require_cmd("git")
        require_buildx("0.17.0")
        compose_cmd = require_docker_compose()

        while True:
            action = choose_action_or_quit()
            if action == "quit":
                return 0

            if action == "start":
                require_cmd("git")
                workdir = setup_dev()
                compose_file = workdir / "docker-compose.yml"
                backup_env_file(workdir / ".env")

                api_host = choose_api_service_host(workdir, compose_file)
                ok(f"Detected API service host: {api_host}")

                hr()
                say("Bootstrap admin")
                hr()
                admin_user = ask_non_empty("Admin username")
                admin_email = ask_email("Admin email")
                admin_pass = ask_password()

                info("Writing .env")
                prepare_env(workdir / ".env", "dev", admin_user, admin_email, admin_pass, api_host)

                say()
                if ask_yes_no("Start containers now?", default_yes=True):
                    start_stack(workdir, compose_file, compose_cmd, action_label="Started")
                    say()
                    ok("Setup complete. Stack is running.")
                    return 0

                warn("Setup complete. Start later with:")
                say(f'  cd "{workdir}" && {" ".join(compose_cmd)} -f "{compose_file.name}" up -d --build')
                say()
                ok("Setup prepared.")
                return 0

            if action == "restart":
                workdir, compose_file = resolve_existing_stack()
                restart_stack(workdir, compose_file, compose_cmd)
                say()
                ok("Restart complete. Stack is running.")
                return 0

            if action in ("stop", "purge"):
                workdir, compose_file = resolve_existing_stack()
                if action == "purge" and not ask_yes_no("Remove volumes too? This cannot be undone.", default_yes=False):
                    warn("Purge cancelled.")
                    continue
                stop_stack(workdir, compose_file, compose_cmd, purge_volumes=(action == "purge"))
                return 0

            warn("Invalid selection.")
    except UserCancelled:
        say()
        warn("Cancelled by user.")
        return 130
    except SystemExit as e:
        err(str(e))
        return 1
    except Exception as e:
        err(str(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
