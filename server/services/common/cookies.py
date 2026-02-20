"""
Ensure cookies are marked Secure when appropriate based on the request scheme
and proxy headers, with support for trusting specific proxy CIDRs when
determining if the original request was made over HTTPS.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address
from typing import Sequence

_Network = IPv4Network | IPv6Network

def is_secure_cookie_request(
    request,
    *,
    trust_proxy_headers: bool,
    trusted_proxy_networks: list[_Network] | None = None,
) -> bool:
    """
    Return True when a cookie should be marked Secure for the given request.

    trust_proxy_headers without trusted_proxy_networks is intentionally
    rejected — trusting headers from any peer is a misconfiguration.
    """
    if request.url.scheme == "https":
        return True

    if not trust_proxy_headers:
        return False

    if not trusted_proxy_networks:
        raise ValueError(
            "trust_proxy_headers=True requires trusted_proxy_networks to be "
            "a non-empty list. Trusting proxy headers from any peer is insecure."
        )

    client = request.client
    if not client:
        return False

    raw_ip = client.host.strip()
    try:
        peer_ip = ip_address(raw_ip)
    except ValueError:
        return False

    if not any(peer_ip in net for net in trusted_proxy_networks):
        return False

    proto = request.headers.get("x-forwarded-proto", "")
    return proto.split(",")[0].strip().lower() == "https"