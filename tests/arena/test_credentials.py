"""Two-class credential split (A9 Part 2). Offline, no real secrets — fake env dicts."""
import pytest

from alpha.arena.credentials import (
    CredentialError,
    WorkToken,
    assert_work_token_contained,
    build_sandbox_env,
)


def test_build_sandbox_env_strips_class_b_secrets_keeps_rest():
    host = {
        "PATH": "/usr/bin", "LANG": "en_US.UTF-8",
        "OPENAI_API_KEY": "sk-xxx", "ALPACA_SECRET_KEY": "s", "ANTHROPIC_API_KEY": "a",
        "DEEPSEEK_TOKEN": "t", "DB_PASSWORD": "p", "AWS_ACCESS_KEY_ID": "k",
        "GCP_CREDENTIALS": "c", "SSH_PRIVATE_KEY": "pk",
    }
    env = build_sandbox_env(host)
    assert env["PATH"] == "/usr/bin" and env["LANG"] == "en_US.UTF-8"
    for secret in ("OPENAI_API_KEY", "ALPACA_SECRET_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_TOKEN",
                   "DB_PASSWORD", "AWS_ACCESS_KEY_ID", "GCP_CREDENTIALS", "SSH_PRIVATE_KEY"):
        assert secret not in env, f"Class B secret leaked into sandbox env: {secret}"


def test_allowlist_posture_strips_secrets_a_denylist_would_miss():
    """The containment primitive is default-DENY: names a substring denylist misses (no API_KEY/
    SECRET/TOKEN marker, or credentials embedded in a URL) are stripped anyway, while the known-safe
    process/locale set survives."""
    leaky = {n: "x" for n in (
        "OPENAI_KEY", "STRIPE_KEY", "SENDGRID_KEY", "GH_PAT", "GITHUB_PAT", "AWS_SESSION",
        "DEPLOY_KEY", "ENCRYPTION_KEY", "SIGNING_KEY", "DATABASE_URL", "REDIS_URL", "AUTH",
        "BEARER", "GPG_KEY", "SSH_AUTH_SOCK", "NETRC", "AWS_SECRET_ACCESS_KEY")}
    safe = {"PATH": "/usr/bin", "HOME": "/home/u", "LANG": "C", "LC_ALL": "C",
            "TERM": "xterm", "TZ": "UTC", "USER": "u", "SHELL": "/bin/sh"}
    env = build_sandbox_env({**leaky, **safe})
    for name in leaky:
        assert name not in env, f"denylist-missed secret leaked into sandbox env: {name}"
    for name, val in safe.items():
        assert env[name] == val, f"known-safe var was dropped: {name}"


def test_keep_allows_extra_nonsecret_var():
    env = build_sandbox_env({"NPM_CONFIG_REGISTRY": "r", "MY_TOOL_CFG": "v", "DROPPED": "d"},
                            keep={"NPM_CONFIG_REGISTRY", "MY_TOOL_CFG"})
    assert env["NPM_CONFIG_REGISTRY"] == "r" and env["MY_TOOL_CFG"] == "v"
    assert "DROPPED" not in env                            # not in default keep nor the keep= set


def test_keep_refuses_secret_shaped_name():
    with pytest.raises(CredentialError):
        build_sandbox_env({"OPENAI_API_KEY": "x"}, keep={"OPENAI_API_KEY"})
    with pytest.raises(CredentialError):
        build_sandbox_env({"DATABASE_URL": "postgres://u:p@h/db"}, keep={"DATABASE_URL"})


def test_work_token_injected_and_is_only_credential():
    host = {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-xxx"}
    token = WorkToken(value="ghp_work", repo_scope=frozenset({"github.com/acme/project"}))
    env = build_sandbox_env(host, work_token=token)
    assert env["WORK_GIT_TOKEN"] == "ghp_work"
    assert "OPENAI_API_KEY" not in env
    # the only credential-shaped value present is the work token we chose to inject
    assert "sk-xxx" not in env.values()


def test_secret_shaped_work_token_var_name_holds_only_injected_value():
    # If host env already carries WORK_GIT_TOKEN (secret-shaped: contains TOKEN), the strip pass
    # removes it; only the value we inject survives — custody is never the inherited one.
    host = {"WORK_GIT_TOKEN": "STALE_INHERITED"}
    env = build_sandbox_env(host, work_token="ghp_fresh")
    assert env["WORK_GIT_TOKEN"] == "ghp_fresh"
    env_no_token = build_sandbox_env(host)             # no work_token -> the stale one is gone
    assert "WORK_GIT_TOKEN" not in env_no_token


def test_assert_contained_passes_for_disjoint_scope():
    token = WorkToken("t", frozenset({"github.com/acme/project", "https://gitlab.com/acme/other"}))
    assert_work_token_contained(token, body_remote_host="git.body-remote.internal")  # no raise


def test_assert_contained_raises_when_scope_reaches_body_remote():
    token = WorkToken("t", frozenset({"github.com/acme/project"}))
    with pytest.raises(CredentialError):
        assert_work_token_contained(token, body_remote_host="github.com")


def test_assert_contained_raises_on_empty_or_wildcard_scope():
    with pytest.raises(CredentialError):
        assert_work_token_contained(WorkToken("t", frozenset()), body_remote_host="github.com")
    with pytest.raises(CredentialError):
        assert_work_token_contained(WorkToken("t", frozenset({"*"})), body_remote_host="github.com")
