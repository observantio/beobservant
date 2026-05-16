"""
IP-based rate limiter for Watchdog middleware.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network

from config import config
from fastapi import Request


def _valid_ip(value: str) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    try:
        ip_address(candidate)
        return candidate
    except ValueError:
        return None


def _request_client_host(request: Request) -> str:
    client = request.client
    host = getattr(client, "host", "") if client is not None else ""
    return str(host or "").strip()


def client_ip(request: Request) -> str:
    def _peer_in_trusted_cidrs(peer: object, cidrs: list[str]) -> bool:
        try:
            peer_ip = ip_address(str(peer))
        except ValueError:
            return False
        if peer_ip.is_loopback:
            return True
        for cidr in cidrs:
            try:
                if peer_ip in ip_network(cidr, strict=False):
                    return True
            except ValueError:
                continue
        return False

    def _trusted_proxy_peer() -> bool:
        if not config.TRUST_PROXY_HEADERS:
            return False
        trusted_cidrs = getattr(config, "TRUSTED_PROXY_CIDRS", []) or []
        if not trusted_cidrs:
            return True

        direct = _request_client_host(request)
        validated = _valid_ip(direct)
        return _peer_in_trusted_cidrs(validated, trusted_cidrs) if validated else False

    resolved_ip: str | None = None
    if _trusted_proxy_peer():
        forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded_for:
            first = forwarded_for.split(",", 1)[0].strip()
            valid_first = _valid_ip(first)
            if valid_first:
                resolved_ip = valid_first

        if resolved_ip is None:
            real_ip = (request.headers.get("x-real-ip") or "").strip()
            valid_real_ip = _valid_ip(real_ip)
            if valid_real_ip:
                resolved_ip = valid_real_ip

    if resolved_ip is None:
        direct = _request_client_host(request)
        resolved_ip = _valid_ip(direct)
    return resolved_ip or "unknown"
