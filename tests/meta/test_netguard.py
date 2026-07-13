"""SSRF hardening (A9 Part 3). Offline, keyless, NO real network: DNS is a fake resolver, the
transport is a fake opener (and one test monkeypatches socket.create_connection to prove the real
transport pins the IP + preserves Host without opening a socket)."""
import io

import pytest

from alpha.meta import netguard
from alpha.meta.netguard import NetguardError, assert_public_ip, guarded_fetch, guarded_fetch_text


# --------------------------------------------------------------------------- assert_public_ip
@pytest.mark.parametrize("ip", [
    "127.0.0.1",          # loopback
    "0.0.0.0",            # unspecified
    "10.0.0.5",           # RFC-1918
    "172.16.3.4",         # RFC-1918
    "192.168.1.1",        # RFC-1918
    "169.254.169.254",    # AWS/GCP cloud metadata
    "169.254.1.1",        # link-local
    "100.64.0.1",         # CGNAT shared address space
    "::1",                # IPv6 loopback
    "fe80::1",            # IPv6 link-local
    "fd00::1",            # IPv6 unique-local
    "fd00:ec2::254",      # AWS IPv6 metadata
    "::ffff:127.0.0.1",   # IPv4-mapped IPv6 loopback (bypass vector)
    "::ffff:10.0.0.1",    # IPv4-mapped IPv6 private
])
def test_assert_public_ip_rejects_non_global(ip):
    with pytest.raises(NetguardError):
        assert_public_ip(ip)


@pytest.mark.parametrize("ip", ["8.8.8.8", "93.184.216.34", "1.1.1.1", "2606:4700:4700::1111"])
def test_assert_public_ip_allows_global(ip):
    assert_public_ip(ip)  # no raise


def test_assert_public_ip_rejects_non_ip():
    with pytest.raises(NetguardError):
        assert_public_ip("not-an-ip")


# --------------------------------------------------------------------------- fake transport helpers
class _Resp:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.body = body


def _resolver(mapping):
    """host -> [ip, ...]; unknown host raises (simulated NXDOMAIN)."""
    def r(host, port):
        if host not in mapping:
            raise NetguardError(f"DNS resolution failed for {host!r}")
        return list(mapping[host])
    return r


def _opener(responses, *, record=None):
    """responses: host -> _Resp (or list of _Resp consumed in order for redirect chains)."""
    def op(*, host, pinned_ip, port, scheme, method, path, headers, timeout, max_bytes):
        if record is not None:
            record.append({"host": host, "pinned_ip": pinned_ip, "port": port,
                           "path": path, "headers": dict(headers), "max_bytes": max_bytes})
        r = responses[host]
        if isinstance(r, list):
            r = r.pop(0)
        return _Resp(r.status, r.headers, r.body[:max_bytes])
    return op


# --------------------------------------------------------------------------- DNS-rebinding / pin
def test_rejects_hostname_resolving_to_private_ip():
    resolver = _resolver({"evil.example.com": ["10.0.0.5"]})
    opener = _opener({})
    with pytest.raises(NetguardError):
        guarded_fetch("http://evil.example.com/", resolver=resolver, opener=opener)


def test_rejects_mixed_public_and_private_answer():
    # A resolver returning [public, private] must still be rejected (any-private -> block).
    resolver = _resolver({"rebind.example.com": ["93.184.216.34", "127.0.0.1"]})
    with pytest.raises(NetguardError):
        guarded_fetch("http://rebind.example.com/", resolver=resolver, opener=_opener({}))


def test_resolve_once_then_pin_passes_resolved_ip_with_original_host():
    record = []
    resolver = _resolver({"example.com": ["93.184.216.34"]})
    opener = _opener({"example.com": _Resp(200, {"content-type": "text/plain"}, b"hello")},
                     record=record)
    res = guarded_fetch("http://example.com/page?q=1", resolver=resolver, opener=opener)
    assert res.text == "hello"
    assert record[0]["pinned_ip"] == "93.184.216.34"       # connected by resolved IP
    assert record[0]["host"] == "example.com"              # Host preserved (not the IP)
    assert record[0]["headers"]["Host"] == "example.com"
    assert record[0]["path"] == "/page?q=1"


def test_dns_failure_is_fail_closed():
    with pytest.raises(NetguardError):
        guarded_fetch("http://nxdomain.example.com/", resolver=_resolver({}), opener=_opener({}))


def test_empty_resolution_is_fail_closed():
    resolver = _resolver({"empty.example.com": []})
    with pytest.raises(NetguardError):
        guarded_fetch("http://empty.example.com/", resolver=resolver, opener=_opener({}))


# --------------------------------------------------------------------------- scheme
@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://host/x", "gopher://h/", "data:text/plain,hi"])
def test_non_http_scheme_blocked(url):
    with pytest.raises(NetguardError):
        guarded_fetch(url, resolver=_resolver({}), opener=_opener({}))


@pytest.mark.parametrize("url", [
    "http://ex.com:99999/",   # port out of range
    "http://ex.com:abc/",     # non-numeric port
    "http://[::1/",           # unterminated IPv6 literal
    "http://[gg::1]/",        # malformed IPv6 literal
])
def test_malformed_url_fails_closed_with_netguard_error(url):
    """A malformed URL must raise NetguardError (the public-API contract), never a raw ValueError,
    and must fail BEFORE any resolve/connect — the poison opener is never reached."""
    def poison(**kw):
        raise AssertionError("opener must not be called on a malformed URL")
    with pytest.raises(NetguardError):
        guarded_fetch(url, resolver=_resolver({}), opener=poison)


# --------------------------------------------------------------------------- redirects
def test_redirect_to_private_host_is_revalidated_and_blocked():
    resolver = _resolver({"good.example.com": ["93.184.216.34"], "meta.example.com": ["169.254.169.254"]})
    opener = _opener({
        "good.example.com": _Resp(302, {"location": "http://meta.example.com/latest/meta-data/"}),
        "meta.example.com": _Resp(200, {}, b"secrets"),
    })
    with pytest.raises(NetguardError):
        guarded_fetch("http://good.example.com/", resolver=resolver, opener=opener)


def test_redirect_to_public_host_is_followed():
    resolver = _resolver({"a.example.com": ["93.184.216.34"], "b.example.com": ["1.1.1.1"]})
    opener = _opener({
        "a.example.com": _Resp(301, {"location": "http://b.example.com/final"}),
        "b.example.com": _Resp(200, {"content-type": "text/plain"}, b"arrived"),
    })
    res = guarded_fetch("http://a.example.com/", resolver=resolver, opener=opener)
    assert res.text == "arrived"
    assert res.url == "http://b.example.com/final"


def test_redirect_budget_exhausted_errors():
    resolver = _resolver({"loop.example.com": ["93.184.216.34"]})
    opener = _opener({"loop.example.com": _Resp(302, {"location": "http://loop.example.com/next"})})
    with pytest.raises(NetguardError):
        guarded_fetch("http://loop.example.com/", resolver=resolver, opener=opener, max_redirects=3)


# --------------------------------------------------------------------------- byte cap + allow public
def test_byte_cap_truncates_body():
    resolver = _resolver({"big.example.com": ["93.184.216.34"]})
    opener = _opener({"big.example.com": _Resp(200, {"content-type": "text/plain"}, b"z" * 10_000)})
    res = guarded_fetch("http://big.example.com/", resolver=resolver, opener=opener, max_bytes=100)
    assert len(res.text) == 100


def test_public_ip_literal_allowed():
    record = []
    opener = _opener({"93.184.216.34": _Resp(200, {"content-type": "text/plain"}, b"ok")}, record=record)
    # IP literal: no DNS needed. Guard validates the literal is public and pins it.
    res = guarded_fetch("http://93.184.216.34/", resolver=_resolver({}), opener=opener)
    assert res.text == "ok"
    assert record[0]["pinned_ip"] == "93.184.216.34"


def test_private_ip_literal_blocked():
    with pytest.raises(NetguardError):
        guarded_fetch("http://127.0.0.1:6379/", resolver=_resolver({}), opener=_opener({}))


def test_guarded_fetch_text_returns_decoded_body():
    resolver = _resolver({"example.com": ["93.184.216.34"]})
    opener = _opener({"example.com": _Resp(200, {"content-type": "text/html; charset=utf-8"}, b"<p>hi</p>")})
    assert guarded_fetch_text("http://example.com/", resolver=resolver, opener=opener) == "<p>hi</p>"


# --------------------------------------------------------------------------- real transport (no socket opened)
def test_default_opener_pins_ip_and_preserves_host_and_cap(monkeypatch):
    captured = {}
    body = b"x" * 100_000
    raw = (b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\nContent-Type: text/plain\r\n\r\n" + body)

    class FakeSock:
        def sendall(self, data):
            captured["request"] = data
        def makefile(self, *a, **k):
            return io.BytesIO(raw)
        def settimeout(self, t):
            pass
        def close(self):
            pass

    def fake_create_connection(addr, timeout=None, *a, **k):
        captured["addr"] = addr
        return FakeSock()

    monkeypatch.setattr(netguard.socket, "create_connection", fake_create_connection)
    res = guarded_fetch("http://example.com/page", resolver=_resolver({"example.com": ["93.184.216.34"]}),
                        max_bytes=10)
    assert captured["addr"] == ("93.184.216.34", 80)      # pinned IP, not a re-resolve of the name
    assert b"Host: example.com" in captured["request"]     # Host header preserved
    assert len(res.text) == 10                             # byte cap enforced by the real transport
