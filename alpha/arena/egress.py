"""Sandbox egress ladder (A9 Part 1): M1 monitor-everything + M2 deny-by-default allowlist.

The activity-space spec §10 open question — "exact `network` allowlist shape for `LocalEnv`" — is
answered here: a HOSTNAME allowlist, deny-by-default, with private/metadata-IP blocking (via
netguard) applied even to allowlisted hosts, resource ceilings from an image manifest that a runtime
policy may only TIGHTEN, and one governance surface (registry-derived, dependency preset).

HONEST LIMIT: on `LocalEnv` there is no kernel network namespace, so this cannot intercept the
packets an arbitrary subprocess emits. It audits + gates the DECLARED net intent (`net=True`) and a
best-effort destination, and IP-validates allowlisted hosts. Real per-packet confinement is
`SandboxedEnv` (A10, deferred). See the A9 spec + charter *Sandbox egress: default-deny + allowlist*.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from alpha.meta import netguard

# Un-credentialed dependency hosts a NOW policy may approve once as a named preset (charter: the
# allowlist is derived from the connector registry; this is the registry-style preset for deps).
DEPENDENCY_PRESET: frozenset[str] = frozenset({
    ".pypi.org", ".pythonhosted.org", ".npmjs.org", ".npmjs.com",
    "github.com", ".github.com", ".githubusercontent.com",
})


@dataclass(frozen=True)
class SandboxEgressRecord:
    """One audit record for one declared egress touch (M1: monitor-everything)."""
    destination: str      # host (best-effort) or "<undetermined>"
    method: str           # "net-run" (LocalEnv declared net) | an HTTP method when known
    timestamp: str        # ISO-8601 UTC
    allowed: bool
    reason: str


@dataclass(frozen=True)
class EgressCeilings:
    """Resource ceilings declared in the image manifest; a runtime policy may only TIGHTEN (lower)."""
    max_bytes: int = 5_000_000
    timeout_s: float = 15.0
    max_redirects: int = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host_matches(host: str, allow: frozenset[str]) -> bool:
    if host in allow:
        return True
    for entry in allow:
        if entry.startswith(".") and (host == entry[1:] or host.endswith(entry)):
            return True
    return False


class EgressPolicy:
    """Deny-by-default destination allowlist for declared sandbox egress (M2).

    allow_hosts: exact (`api.example.com`) or suffix (`.pypi.org` = that host + any subdomain).
    A destination not matched, a raw-IP destination, or an allowlisted host that resolves to a
    private/metadata IP are all DENIED. `resolver` is the netguard-style DNS seam (injectable offline).
    """

    def __init__(self, allow_hosts, *, ceilings: EgressCeilings | None = None,
                 method_allow: dict[str, frozenset[str]] | None = None,
                 resolver: Callable = netguard._default_resolver):
        self.allow_hosts = frozenset(allow_hosts)
        self.ceilings = ceilings or EgressCeilings()
        self.method_allow = {h: frozenset(ms) for h, ms in (method_allow or {}).items()}
        self._resolver = resolver

    @classmethod
    def from_manifest(cls, manifest: dict, *, resolver: Callable = netguard._default_resolver) -> "EgressPolicy":
        c = manifest.get("ceilings") or {}
        return cls(
            allow_hosts=manifest.get("allow_hosts", ()),
            ceilings=EgressCeilings(
                max_bytes=c.get("max_bytes", 5_000_000),
                timeout_s=c.get("timeout_s", 15.0),
                max_redirects=c.get("max_redirects", 5)),
            method_allow=manifest.get("method_allow"),
            resolver=resolver)

    def tighten(self, *, hosts=None, ceilings: EgressCeilings | None = None) -> "EgressPolicy":
        """Return a stricter policy. The host set may only shrink (subset); each ceiling may only
        lower. Any widening raises ValueError — "policy may only tighten" made executable."""
        new_hosts = self.allow_hosts if hosts is None else frozenset(hosts)
        if not new_hosts <= self.allow_hosts:
            raise ValueError(f"egress policy may only tighten: {set(new_hosts - self.allow_hosts)} not in allowlist")
        new_ceilings = self.ceilings
        if ceilings is not None:
            if (ceilings.max_bytes > self.ceilings.max_bytes
                    or ceilings.timeout_s > self.ceilings.timeout_s
                    or ceilings.max_redirects > self.ceilings.max_redirects):
                raise ValueError("egress policy may only tighten: a ceiling was raised")
            new_ceilings = ceilings
        return EgressPolicy(new_hosts, ceilings=new_ceilings, method_allow=self.method_allow,
                            resolver=self._resolver)

    def evaluate(self, destination: str, method: str = "net-run") -> SandboxEgressRecord:
        """Deny-by-default. Always returns a record (M1: every touch is audited, allowed or not)."""
        def rec(allowed: bool, reason: str) -> SandboxEgressRecord:
            return SandboxEgressRecord(destination=destination, method=method,
                                       timestamp=_now(), allowed=allowed, reason=reason)
        if not destination or destination == "<undetermined>":
            return rec(False, "destination undetermined (fail-closed)")
        try:
            ipaddress.ip_address(destination)
            return rec(False, "raw-IP destination denied (allowlist is hostnames)")
        except ValueError:
            pass
        if not _host_matches(destination, self.allow_hosts):
            return rec(False, "not on allowlist")
        allowed_methods = self.method_allow.get(destination)
        if allowed_methods is not None and method not in allowed_methods:
            return rec(False, f"method {method!r} not allowed for {destination}")
        try:
            netguard.resolve_and_pin(destination, 443, resolver=self._resolver)
        except netguard.NetguardError as e:
            return rec(False, f"allowlisted host blocked at IP check: {e}")
        return rec(True, "allowlisted")
