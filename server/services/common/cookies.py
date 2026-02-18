from ipaddress import ip_address, ip_network


def is_secure_cookie_request(request, *, trust_proxy_headers: bool, trusted_proxy_cidrs: list[str] | None = None) -> bool:
    """Return True when cookie should be marked Secure for the given request."""
    if request.url.scheme == "https":
        return True

    if not trust_proxy_headers:
        return False

    trusted_cidrs = trusted_proxy_cidrs or []
    direct_peer = (request.client.host if request.client else "").strip()

    if trusted_cidrs:
        try:
            peer_ip = ip_address(direct_peer)
            for cidr in trusted_cidrs:
                try:
                    if peer_ip in ip_network(cidr, strict=False):
                        return request.headers.get("x-forwarded-proto", "").lower() == "https"
                except ValueError:
                    continue
        except ValueError:
            return False
        return False

    return request.headers.get("x-forwarded-proto", "").lower() == "https"
