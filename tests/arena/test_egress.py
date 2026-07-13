"""Egress ladder (A9 Part 1): M1 audit record + M2 deny-by-default allowlist. Offline — DNS is a
fake resolver, no real network."""
import pytest

from alpha.arena.egress import DEPENDENCY_PRESET, EgressCeilings, EgressPolicy, SandboxEgressRecord


def _resolver(mapping):
    def r(host, port):
        return list(mapping.get(host, []))
    return r


def _policy(hosts, mapping):
    return EgressPolicy(hosts, resolver=_resolver(mapping))


def test_deny_by_default_off_list_host():
    rec = _policy({"api.example.com"}, {"evil.com": ["93.184.216.34"]}).evaluate("evil.com")
    assert isinstance(rec, SandboxEgressRecord)
    assert rec.allowed is False and "not on allowlist" in rec.reason
    assert rec.timestamp and rec.destination == "evil.com"


def test_allow_on_list_host_resolving_public():
    rec = _policy({"api.example.com"}, {"api.example.com": ["93.184.216.34"]}).evaluate("api.example.com")
    assert rec.allowed is True and rec.reason == "allowlisted"


def test_suffix_wildcard_matches_host_and_subdomain():
    pol = _policy({".pypi.org"}, {"pypi.org": ["93.184.216.34"], "files.pypi.org": ["1.1.1.1"]})
    assert pol.evaluate("pypi.org").allowed is True
    assert pol.evaluate("files.pypi.org").allowed is True
    assert pol.evaluate("notpypi.org").allowed is False


def test_allowlisted_host_resolving_private_is_denied():
    # DNS-allowlist-rebinding: host is on the allowlist but points at a private IP -> denied anyway.
    rec = _policy({"api.example.com"}, {"api.example.com": ["10.0.0.5"]}).evaluate("api.example.com")
    assert rec.allowed is False and "IP check" in rec.reason


def test_allowlisted_host_resolving_metadata_is_denied():
    rec = _policy({"api.example.com"}, {"api.example.com": ["169.254.169.254"]}).evaluate("api.example.com")
    assert rec.allowed is False


def test_raw_ip_destination_denied():
    rec = _policy({"93.184.216.34"}, {}).evaluate("93.184.216.34")
    assert rec.allowed is False and "raw-IP" in rec.reason


def test_undetermined_destination_fail_closed():
    rec = _policy({"api.example.com"}, {}).evaluate("<undetermined>")
    assert rec.allowed is False and "undetermined" in rec.reason


def test_dns_failure_fail_closed():
    rec = _policy({"api.example.com"}, {}).evaluate("api.example.com")   # host not in resolver map -> []
    assert rec.allowed is False


def test_method_restriction():
    pol = EgressPolicy({"api.example.com"}, resolver=_resolver({"api.example.com": ["93.184.216.34"]}),
                       method_allow={"api.example.com": frozenset({"GET"})})
    assert pol.evaluate("api.example.com", "GET").allowed is True
    assert pol.evaluate("api.example.com", "POST").allowed is False


def test_tighten_may_narrow_hosts():
    pol = _policy({"a.example.com", "b.example.com"}, {"a.example.com": ["93.184.216.34"]})
    narrowed = pol.tighten(hosts={"a.example.com"})
    assert narrowed.evaluate("a.example.com").allowed is True
    assert narrowed.evaluate("b.example.com").allowed is False


def test_tighten_rejects_widening_hosts():
    pol = _policy({"a.example.com"}, {})
    with pytest.raises(ValueError):
        pol.tighten(hosts={"a.example.com", "new.example.com"})


def test_tighten_rejects_raised_ceiling():
    pol = EgressPolicy({"a.example.com"}, ceilings=EgressCeilings(max_bytes=1000))
    with pytest.raises(ValueError):
        pol.tighten(ceilings=EgressCeilings(max_bytes=10_000))
    tighter = pol.tighten(ceilings=EgressCeilings(max_bytes=500))
    assert tighter.ceilings.max_bytes == 500


def test_from_manifest_builds_policy_with_ceilings():
    pol = EgressPolicy.from_manifest(
        {"allow_hosts": [".pypi.org"], "ceilings": {"max_bytes": 2048, "timeout_s": 5.0, "max_redirects": 2}},
        resolver=_resolver({"pypi.org": ["93.184.216.34"]}))
    assert pol.ceilings.max_bytes == 2048 and pol.ceilings.max_redirects == 2
    assert pol.evaluate("pypi.org").allowed is True


def test_dependency_preset_is_a_named_set():
    assert ".pypi.org" in DEPENDENCY_PRESET and "github.com" in DEPENDENCY_PRESET
