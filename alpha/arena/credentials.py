"""Two-class credential split (A9 Part 2; charter *Security Boundary: Two-Class Credentials — the
Work Token Is Contained; Everything Else Never Enters*).

Class A — the WORK TOKEN: repo-scoped, sandbox-resident, readable there (containment, not secrecy),
  and physically incapable of reaching the Body remote.
Class B — EVERYTHING ELSE (provider API keys, vault creds): never enters the sandbox env.

Today `LocalEnv` spawns subprocesses that inherit the full `os.environ`, so the arena shell can
`env | grep KEY` every provider secret. `build_sandbox_env` closes that with an ALLOWLIST
(default-deny) posture: keep ONLY a known-safe set of non-secret process/locale vars (+ an explicit
`keep=` for the rare legit extra) and inject the work token; EVERYTHING else is stripped, so Class B
"Never Enters" is structurally true regardless of the secret's *name* — a denylist over secret-shaped
names can never be complete (`OPENAI_KEY`, `DATABASE_URL` embedding `user:pass@host`, `GH_PAT`,
`BEARER`, … all slip a substring denylist). `assert_work_token_contained` is the "cannot reach the
Body remote" invariant as a check.

NOT a security boundary on its own — LocalEnv has no kernel isolation (repo CLAUDE.md; the
compensating control is workbench's boot assert). This removes Class B from the subprocess ENV,
which is real; it does not hide the work token from code in the sandbox, nor stop a subprocess
reading a secret from a file the operator left in the workspace. Kernel-side custody = A10.
"""
from __future__ import annotations

from dataclasses import dataclass

# Env vars kept by default: known-safe, non-secret process/locale settings the sandbox needs to
# function. Everything NOT in here (nor the LC_ locale family, nor an explicit keep=) is stripped —
# the allowlist / default-deny posture is what makes "Everything Else Never Enters" structural.
_DEFAULT_KEEP: frozenset[str] = frozenset({
    "PATH", "HOME", "LANG", "LANGUAGE", "TERM", "TZ",
    "USER", "LOGNAME", "SHELL", "TMPDIR", "PWD", "HOSTNAME",
})

# Secret-shaped name markers — used to REFUSE a secret-shaped name in the keep-allowlist (so an
# operator can't accidentally `keep={"API_KEY"}`) and to defensively drop a secret-shaped LC_* name.
# The markers do NOT drive stripping (the allowlist does); they are the "no config re-admits a
# credential" fail-closed guard on the escape hatch.
_SECRET_MARKERS = ("API_KEY", "APIKEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD",
                   "CREDENTIAL", "PRIVATE_KEY", "ACCESS_KEY", "KEY", "PAT", "AUTH",
                   "BEARER", "CREDS", "URL")


class CredentialError(Exception):
    """A credential-containment invariant was violated (fail-closed)."""


@dataclass(frozen=True)
class WorkToken:
    """A Class-A work-repo token: contained, repo-scoped. `repo_scope` enumerates the hosts/repo
    URLs this token may push to — never empty, never a wildcard (see assert_work_token_contained)."""
    value: str
    repo_scope: frozenset[str]


def _is_secret_name(name: str) -> bool:
    up = name.upper()
    return any(marker in up for marker in _SECRET_MARKERS)


def _kept(name: str, keep_set: frozenset[str]) -> bool:
    if name in keep_set:                                   # default-safe + validated explicit keep
        return True
    return name.startswith("LC_") and not _is_secret_name(name)   # locale family, secret-guarded


def build_sandbox_env(host_env, *, work_token: WorkToken | str | None = None,
                      work_token_var: str = "WORK_GIT_TOKEN", keep=()) -> dict[str, str]:
    """The env a sandbox subprocess may see, built with an ALLOWLIST (default-deny) posture: keep ONLY
    the known-safe non-secret set (`_DEFAULT_KEEP` + the LC_ locale family + any explicit *keep*
    names), strip everything else, and inject the work token LAST under *work_token_var*. Because the
    default is DENY, a secret never enters regardless of its name (Class B "Never Enters" is
    structural). *keep* is the escape hatch for a rare legit extra var — a secret-shaped keep name is
    REFUSED (no config re-admits a credential). The work-token var is stripped like any other name
    then re-injected, so its custody is only the value we place."""
    bad = sorted(k for k in keep if _is_secret_name(k))
    if bad:
        raise CredentialError(f"keep-allowlist may not include secret-shaped names: {bad}")
    keep_set = _DEFAULT_KEEP | frozenset(keep)
    out = {k: v for k, v in dict(host_env).items() if _kept(k, keep_set)}
    if work_token is not None:
        out[work_token_var] = work_token.value if isinstance(work_token, WorkToken) else str(work_token)
    return out


def _entry_host(entry: str) -> str:
    stripped = entry.split("://", 1)[-1]          # drop any scheme
    return stripped.split("/", 1)[0].lower()      # host portion, before any path


def assert_work_token_contained(token: WorkToken, *, body_remote_host: str) -> None:
    """Raise CredentialError unless the work token is physically incapable of reaching the Body
    remote: its scope must be non-empty, non-wildcard, and must not include the Body remote host."""
    scope = token.repo_scope
    if not scope:
        raise CredentialError("work token scope is empty — enumerate the work repos it may reach")
    if "*" in scope or "" in scope:
        raise CredentialError("work token scope may not be a wildcard")
    body = body_remote_host.lower()
    for entry in scope:
        if _entry_host(entry) == body:
            raise CredentialError(
                f"work token scope reaches the Body remote host {body_remote_host!r} — "
                "the two-class split requires the Body remote be unreachable with the work token")
