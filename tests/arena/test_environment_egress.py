"""LocalEnv A9 wiring (Part 1 M1/M2 + Part 2 env): egress audit/allowlist + two-class subprocess env.
Offline — harmless `true`/`printenv` commands in a temp workspace, DNS is a fake resolver."""
from alpha.arena.credentials import build_sandbox_env
from alpha.arena.egress import EgressPolicy
from alpha.arena.environment import LocalEnv


def _resolver(mapping):
    def r(host, port):
        return list(mapping.get(host, []))
    return r


def test_net_run_produces_audit_record_and_denies_off_list(tmp_path):
    records = []
    pol = EgressPolicy({"api.example.com"}, resolver=_resolver({"evil.com": ["93.184.216.34"]}))
    env = LocalEnv(tmp_path, egress_policy=pol, egress_audit=records.append)
    res = env.run(["curl", "http://evil.com/x"], net=True)
    assert res.ok is False and "egress denied" in res.stderr        # M2: off-list denied
    assert len(records) == 1                                        # M1: monitored
    assert records[0].destination == "evil.com" and records[0].allowed is False


def test_net_run_allowed_when_on_list(tmp_path):
    records = []
    pol = EgressPolicy({"api.example.com"}, resolver=_resolver({"api.example.com": ["93.184.216.34"]}))
    env = LocalEnv(tmp_path, egress_policy=pol, egress_audit=records.append)
    res = env.run(["true", "http://api.example.com/ok"], net=True)
    assert res.ok is True and records[0].allowed is True            # not blocked; audited as allowed


def test_no_policy_is_byte_identical_net_noop(tmp_path):
    # Default LocalEnv (no egress_policy): net=True stays the advisory no-op — the command still runs.
    env = LocalEnv(tmp_path)
    res = env.run(["true", "http://anything/x"], net=True)
    assert res.ok is True


def test_env_none_inherits_and_env_dict_is_used(tmp_path):
    import os
    # SECRET_MARKER is secret-shaped (contains SECRET) -> build_sandbox_env strips it.
    os.environ["SECRET_MARKER"] = "leaked"
    read_env = ["printenv", "SECRET_MARKER"]     # bare command -> not caught by the path-guard
    try:
        # env=None -> inherit: the parent's var is visible (byte-identical to pre-A9 behavior).
        assert "leaked" in LocalEnv(tmp_path).run(read_env).stdout
        # env=build_sandbox_env(...) -> the secret is stripped; the subprocess cannot read it.
        clean = build_sandbox_env(os.environ)
        assert "leaked" not in LocalEnv(tmp_path, env=clean).run(read_env).stdout
    finally:
        del os.environ["SECRET_MARKER"]
