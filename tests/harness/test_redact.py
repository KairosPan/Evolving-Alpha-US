"""Value-based secret redaction (kairos-mining §1.5/§4.3): key/credential-scoped only."""
from alpha.redact import collect_secrets, redact


def test_collect_secrets_matches_name_pattern_and_length_floor():
    env = {
        "DEEPSEEK_API_KEY": "sk-aaaabbbbcccc",
        "MY_TOKEN": "tok-12345678",
        "SOME_PASSWORD": "hunter2hunter2",
        "SHORT_KEY": "abc",              # < 8 chars: never collected
        "PLAIN_VAR": "not-a-secret-var", # name doesn't match: never collected
    }
    s = collect_secrets(env)
    assert set(s) == {"DEEPSEEK_API_KEY", "MY_TOKEN", "SOME_PASSWORD"}


def test_redact_replaces_values_recursively():
    secrets = {"APCA_API_SECRET_KEY": "supersecretvalue"}
    obj = {
        "stdout": "APCA_API_SECRET_KEY=supersecretvalue\nPATH=/usr/bin",
        "nested": [{"text": "prefix supersecretvalue suffix"}, 42, None],
    }
    out = redact(obj, secrets)
    assert "supersecretvalue" not in str(out)
    assert out["stdout"] == "APCA_API_SECRET_KEY=[REDACTED:APCA_API_SECRET_KEY]\nPATH=/usr/bin"
    assert out["nested"][0]["text"] == "prefix [REDACTED:APCA_API_SECRET_KEY] suffix"
    assert out["nested"][1] == 42 and out["nested"][2] is None


def test_redact_no_secrets_is_identity():
    obj = {"a": ["x", {"b": "y"}]}
    assert redact(obj, {}) == obj
