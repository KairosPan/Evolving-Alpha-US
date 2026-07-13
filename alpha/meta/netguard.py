"""netguard.py — SSRF-hardened HTTP(S) fetch (stdlib-only).

The fetches the harness itself makes (cockpit URL ingest, alpha/meta/ingest.py::_urllib_fetcher)
take URLs a user pastes or a model emits — the genuine untrusted-URL surface. Plain urllib will
fetch http://169.254.169.254/ (cloud metadata → IAM creds), http://127.0.0.1:6379/ (loopback
services), RFC-1918 LAN, or a public hostname whose DNS record points at any of those (DNS
rebinding). This module blocks that:

  1. resolve the hostname ONCE (fail-closed on DNS failure/empty answer),
  2. require EVERY resolved IP be globally routable (any private/loopback/link-local/reserved/
     multicast/metadata address -> block),
  3. connect by the PINNED IP while preserving the Host header (and TLS SNI) — never re-resolving
     between the check and the connect (defeats the TOCTOU rebind window),
  4. re-validate every redirect hop through the same gate (redirects are not transport-followed),
  5. cap the response body.

Real, kernel-independent enforcement: we own the resolver and the socket for in-process fetches.
It is NOT a sandbox egress boundary — arbitrary subprocess network in LocalEnv is out of reach (that
is SandboxedEnv, deferred). See docs/superpowers/specs/2026-07-13-a9-egress-creds-ssrf-design.md.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlsplit

_ALLOWED_SCHEMES = ("http", "https")

# Explicit cloud-metadata addresses — redundant with link-local/ULA rejection below, but named so the
# audit reason is precise. 169.254.169.254 = AWS/GCP/OpenStack/Azure; fd00:ec2::254 = AWS IPv6.
_METADATA_IPS = frozenset({
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("fd00:ec2::254"),
})

_DEFAULT_MAX_BYTES = 5_000_000
_DEFAULT_TIMEOUT = 15.0
_DEFAULT_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class NetguardError(Exception):
    """A fetch destination was blocked (fail-closed). Callers turn it into a friendly message."""


def _to_ip(ip: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    addr = ipaddress.ip_address(ip)
    # Unwrap IPv4-mapped IPv6 (::ffff:127.0.0.1) so category checks see the real IPv4 — a bypass
    # otherwise, since the wrapper's own flags do not report the mapped address's category.
    if addr.version == 6 and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr


def assert_public_ip(ip: str) -> None:
    """Raise NetguardError unless *ip* is a globally routable public address."""
    try:
        addr = _to_ip(ip)
    except ValueError as e:
        raise NetguardError(f"not an IP address: {ip!r}") from e
    if addr in _METADATA_IPS:
        raise NetguardError(f"blocked cloud-metadata address: {ip}")
    # The is_global check alone suffices in current CPython, but the explicit category clause covers
    # is_global edge cases that have varied across patch versions (and names CGNAT 100.64.0.0/10).
    blocked = (addr.is_private or addr.is_loopback or addr.is_link_local
               or addr.is_reserved or addr.is_multicast or addr.is_unspecified)
    if blocked or not addr.is_global:
        raise NetguardError(f"blocked non-global address: {ip}")


def _default_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise NetguardError(f"DNS resolution failed for {host!r}: {e}") from e
    return [info[4][0] for info in infos]


def resolve_and_pin(host: str, port: int, *, resolver: Callable = _default_resolver) -> str:
    """Resolve *host* ONCE; require EVERY candidate IP be public; return the pinned IP.

    An IP literal is validated directly (no DNS). Requiring *all* candidates be public — not just the
    one we connect to — defeats the resolver-returns-[public,private] and multi-record rebind tricks.
    """
    try:
        ipaddress.ip_address(host)          # literal? validate + pin without DNS
        assert_public_ip(host)
        return host
    except ValueError:
        pass                                # not a literal -> resolve
    candidates = list(resolver(host, port))
    if not candidates:
        raise NetguardError(f"no addresses resolved for {host!r}")
    for ip in candidates:
        assert_public_ip(ip)
    return candidates[0]                     # pin the first validated IP


# --------------------------------------------------------------------------- transport (pinned IP)
class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, pinned_ip: str, **kw):
        super().__init__(host, **kw)
        self._pinned_ip = pinned_ip

    def connect(self):  # connect to the pinned IP; http.client sets Host from self.host (the name)
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, pinned_ip: str, *, context=None, **kw):
        super().__init__(host, context=context, **kw)
        self._pinned_ip = pinned_ip

    def connect(self):  # connect to the pinned IP; wrap TLS with SNI = self.host (the name) for certs
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


@dataclass(frozen=True)
class _Response:
    status: int
    headers: dict
    body: bytes


def _default_opener(*, host, pinned_ip, port, scheme, method, path, headers, timeout, max_bytes):
    if scheme == "https":
        conn = _PinnedHTTPSConnection(host, pinned_ip, port=port, timeout=timeout,
                                      context=ssl.create_default_context())
    else:
        conn = _PinnedHTTPConnection(host, pinned_ip, port=port, timeout=timeout)
    try:
        conn.request(method, path, headers=headers)
        resp = conn.getresponse()
        body = resp.read(max_bytes)          # read at most max_bytes — bounds a hostile large body
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        return _Response(status=resp.status, headers=hdrs, body=body)
    finally:
        conn.close()


# --------------------------------------------------------------------------- fetch (redirect loop)
@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    headers: dict
    text: str


def _split(url: str) -> tuple[str, str, int, str]:
    try:
        parts = urlsplit(url)
        host = parts.hostname                 # raises ValueError on a malformed IPv6 literal
        port = parts.port                     # raises ValueError on a bad/out-of-range port
    except ValueError as e:                   # fail CLOSED with the public-API error, not raw ValueError
        raise NetguardError(f"malformed URL {url!r}: {e}") from e
    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise NetguardError(f"scheme not allowed: {scheme or 'none'} (only http/https)")
    if not host:
        raise NetguardError(f"no host in URL: {url!r}")
    port = port or (443 if scheme == "https" else 80)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return scheme, host, port, path


def _charset(content_type: str) -> str | None:
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _finalize(url: str, resp: _Response) -> FetchResult:
    charset = _charset(resp.headers.get("content-type", "")) or "utf-8"
    return FetchResult(url=url, status=resp.status, headers=resp.headers,
                       text=resp.body.decode(charset, errors="replace"))


def guarded_fetch(url: str, *, timeout: float = _DEFAULT_TIMEOUT, max_bytes: int = _DEFAULT_MAX_BYTES,
                  max_redirects: int = _DEFAULT_MAX_REDIRECTS, headers: dict | None = None,
                  resolver: Callable = _default_resolver,
                  opener: Callable = _default_opener) -> FetchResult:
    """SSRF-guarded GET. Every hop (initial + each redirect) is resolve-once + all-IPs-public + pin.
    `resolver` and `opener` are injection seams for offline tests (no real DNS/socket)."""
    current = url
    for _ in range(max_redirects + 1):
        scheme, host, port, path = _split(current)
        pinned = resolve_and_pin(host, port, resolver=resolver)
        req_headers = {"Host": host, "User-Agent": "sonia-kairos/1.0", "Accept-Encoding": "identity"}
        if headers:
            req_headers.update(headers)
        resp = opener(host=host, pinned_ip=pinned, port=port, scheme=scheme, method="GET",
                      path=path, headers=req_headers, timeout=timeout, max_bytes=max_bytes)
        if resp.status in _REDIRECT_STATUSES:
            loc = resp.headers.get("location")
            if not loc:
                return _finalize(current, resp)
            current = urljoin(current, loc)   # re-validated on the next iteration
            continue
        return _finalize(current, resp)
    raise NetguardError(f"too many redirects (> {max_redirects})")


def guarded_fetch_text(url: str, *, timeout: float = _DEFAULT_TIMEOUT,
                       max_bytes: int = _DEFAULT_MAX_BYTES,
                       max_redirects: int = _DEFAULT_MAX_REDIRECTS, headers: dict | None = None,
                       resolver: Callable = _default_resolver,
                       opener: Callable = _default_opener) -> str:
    """Drop-in for _urllib_fetcher: SSRF-guarded fetch returning decoded, byte-capped text."""
    return guarded_fetch(url, timeout=timeout, max_bytes=max_bytes, max_redirects=max_redirects,
                         headers=headers, resolver=resolver, opener=opener).text
