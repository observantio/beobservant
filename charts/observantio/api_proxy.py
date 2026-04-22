#!/usr/bin/env python3

from __future__ import annotations

import http.client
import http.server
import socketserver
import ssl
import sys
import urllib.parse


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def _target_path(self) -> str:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            return urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        return self.path

    def _forward(self) -> None:
        content_length = self.headers.get("Content-Length")
        body = b""
        if content_length is not None:
            try:
                body = self.rfile.read(max(0, int(content_length)))
            except ValueError:
                body = b""

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }
        listen_port = self.server.server_address[1]
        client_host = self.headers.get("Host", f"127.0.0.1:{listen_port}")
        headers["Host"] = client_host
        headers["X-Forwarded-For"] = self.headers.get("X-Forwarded-For", self.client_address[0])
        headers["X-Forwarded-Host"] = client_host
        headers["X-Forwarded-Proto"] = "http"
        headers["X-Forwarded-Port"] = str(listen_port)

        try:
            if self.server.upstream_is_https:
                conn = http.client.HTTPSConnection(
                    "127.0.0.1",
                    self.server.upstream_port,
                    timeout=30,
                    context=self.server.upstream_ssl_context,
                )
            else:
                conn = http.client.HTTPConnection(
                    "127.0.0.1",
                    self.server.upstream_port,
                    timeout=30,
                )
            conn.request(self.command, self._target_path(), body=body if body else None, headers=headers)
            resp = conn.getresponse()
        except Exception as exc:
            self.send_error(502, f"Upstream unavailable: {exc}")
            return

        try:
            self.send_response(resp.status, resp.reason)
            response_body = resp.read()
            for key, value in resp.getheaders():
                if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "content-length":
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        finally:
            conn.close()

    def do_GET(self) -> None:
        self._forward()

    def do_HEAD(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def do_PUT(self) -> None:
        self._forward()

    def do_PATCH(self) -> None:
        self._forward()

    def do_DELETE(self) -> None:
        self._forward()

    def do_OPTIONS(self) -> None:
        self._forward()


def _build_upstream_ssl_context(cafile: str | None) -> ssl.SSLContext:
    if cafile:
        context = ssl.create_default_context(cafile=cafile)
    else:
        context = ssl.create_default_context()
    # The port-forward terminates on localhost, so verify the internal CA without hostname matching.
    context.check_hostname = False
    return context


def main() -> int:
    if len(sys.argv) not in {4, 5}:
        print(
            "Usage: api_proxy.py <listen_port> <upstream_port> <upstream_is_https> [ca_bundle_path]",
            file=sys.stderr,
        )
        return 1

    listen_port = int(sys.argv[1])
    upstream_port = int(sys.argv[2])
    upstream_is_https = sys.argv[3].lower() == "true"
    ca_bundle_path = sys.argv[4] if len(sys.argv) == 5 else None

    server = ThreadingHTTPServer(("127.0.0.1", listen_port), ProxyHandler)
    server.upstream_port = upstream_port
    server.upstream_is_https = upstream_is_https
    server.upstream_ssl_context = _build_upstream_ssl_context(ca_bundle_path) if upstream_is_https else None

    print(
        f"API proxy listening on 127.0.0.1:{listen_port} -> 127.0.0.1:{upstream_port} "
        f"({'https' if upstream_is_https else 'http'})",
        flush=True,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())