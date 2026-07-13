# A9 — Egress ladder + two-class credential split + SSRF IP-range hardening

> Task A9 of DEVELOPMENT-PLAN §2 ("closes G4 + G3 long-term"). Answers the activity-space spec §10
> open question on the `LocalEnv` `network` allowlist shape. Charter sections: *Security Boundary:
> Two-Class Credentials*; *Sandbox egress: default-deny + destination allowlist*; *Immutable Kernel*.
> Design date 2026-07-13. Baseline: local main @ 6a2ea2d, 1672 offline tests, lint 0, tcb-check 0.

## 0. What this arc is, and is not

Three additions, all stdlib-only, all offline-testable, all **additive with byte-identical
defaults** so merging changes nothing until a policy/env/guard is opted in — except the one leg that
is *intentionally* fail-closed-on-by-default at its seam (the SSRF guard on the cockpit fetcher,
which only ever *rejects* a private/metadata destination a legitimate URL never has).

| Leg | Module | Enforcement reality | Default |
|---|---|---|---|
| **SSRF IP-range hardening** (Part 3, priority) | `alpha/meta/netguard.py` (NEW) | **Real** — we own the socket for fetches the harness itself makes | fail-closed, **on** at `_urllib_fetcher` |
| **M1/M2 egress ladder** (Part 1) | `alpha/arena/egress.py` (NEW) + `environment.py` wiring | **Advisory + audit** on `LocalEnv` (no kernel netns); real teeth deferred to `SandboxedEnv` | **off** (no policy attached) |
| **Two-class credential split** (Part 2) | `alpha/arena/credentials.py` (NEW) + `environment.py` `env=` | **Real** for the env-custody leg (subprocess env is a dict we build) | **off** (env inherited) |

The honesty line, stated once and repeated in every docstring: on `LocalEnv` there is **no kernel
network namespace**, so a spawned subprocess can open a socket the harness never sees. The egress
ladder therefore *audits and gates the declared network intent* (`net=True`) and best-effort
destinations, and unconditionally IP-validates allowlisted hosts through `netguard` — but it does
**not** confine arbitrary subprocess packets. That confinement is `SandboxedEnv`'s job (A10,
deferred, commercial). The SSRF guard, by contrast, *is* real: it governs the fetches the harness
makes in-process, where we control the resolver and the socket.

---

## Part 3 — SSRF IP-range hardening (`alpha/meta/netguard.py`) — the testable core

### 3.1 Threat

`urllib.urlopen(user_or_model_supplied_url)` will happily fetch `http://169.254.169.254/…` (cloud
metadata → IAM creds), `http://127.0.0.1:6379/…` (loopback services), `http://10.x/…` (RFC-1918
LAN), or a public hostname whose DNS record points at any of those (DNS rebinding). The cockpit
ingest fetcher `alpha/meta/ingest.py::_urllib_fetcher` takes URLs a user pastes or a model emits —
the genuine untrusted-URL surface. Today it has only a *scheme* allowlist (http/https), noted
in-file as leaving private-IP SSRF for "a separate hardening still gated on non-localhost serving."
This is that hardening, and it is the **blocking precondition** before any non-localhost / multi-user
serving of the cockpit (the `ingest_attachments` cap and the no-Origin/CSRF loopback-approval
accepted risk ride the same precondition).

### 3.2 Algorithm (DNS-rebinding-safe)

For a fetch of `url`:

1. **Scheme gate.** `scheme ∈ {http, https}` else `NetguardError`. (Belt-and-suspenders with the
   caller's own scheme check.)
2. **Resolve ONCE.** Split host/port. If host is an IP literal, validate it directly (step 3). Else
   `resolver(host, port)` (default wraps `socket.getaddrinfo`, TCP) → a list of candidate IP
   strings. Empty list or `gaierror`/timeout → `NetguardError` (**fail-closed**).
3. **Require EVERY resolved IP is globally routable.** For each candidate run `assert_public_ip`:
   - `ip = ipaddress.ip_address(s)`.
   - **Unwrap IPv4-mapped IPv6** (`::ffff:127.0.0.1` → `127.0.0.1`) via `ip.ipv4_mapped` before
     any category check — a real bypass otherwise.
   - Reject if `ip` is in the explicit **cloud-metadata denylist** (`169.254.169.254`,
     `fd00:ec2::254`, and the AWS/GCP/Azure link-local metadata address) — redundant with
     link-local rejection but gives a precise audit reason.
   - Reject unless `ip.is_global` **and not** any of
     `is_private / is_loopback / is_link_local / is_reserved / is_multicast / is_unspecified`
     (the second clause covers `is_global` edge cases that vary across CPython patch versions, plus
     CGNAT `100.64.0.0/10` shared address space).
   Rejecting when **any** candidate fails (not just the one we connect to) closes the
   "resolver returns `[public, private]`" and multi-record-rebinding tricks.
4. **Pin.** Choose one validated IP (the first). This is the address we will `connect()` to — the
   name is **never re-resolved** between check and connect (resolve-once-then-pin defeats the
   TOCTOU window between the DNS check and the socket open).
5. **Connect by pinned IP, preserve Host + SNI.** Open the TCP connection to the pinned IP, but keep
   the `Host:` header = the original hostname and (HTTPS) `server_hostname` = the original hostname
   so TLS cert validation and virtual-hosting still work. Implemented with
   `http.client.HTTP(S)Connection` subclasses whose `connect()` targets the pinned IP while
   `self.host` stays the name.
6. **Byte cap.** Read at most `max_bytes` of the response body (default 5 MB) — bounds a hostile
   large response independently of the caller's post-fetch text cap.
7. **Redirects are re-validated, never transport-followed.** The transport does **not** auto-follow
   3xx (urllib's default opener would re-resolve and bypass the pin). Instead the guard reads
   `Location`, resolves it against the current URL, and loops back to step 1 on the new target
   (full resolve-once + validate + pin), decrementing a redirect budget (`max_redirects`, default
   5). Exceeding the budget → `NetguardError`. This is what stops a public host 302-ing to
   `http://169.254.169.254/`.

### 3.3 Public API

```python
class NetguardError(Exception): ...                      # a destination was blocked (fail-closed)

def assert_public_ip(ip: str) -> None: ...               # raises NetguardError; reused by egress
def resolve_and_pin(host, port, *, resolver=...) -> str  # validates ALL, returns the pinned IP
def guarded_fetch(url, *, timeout=15.0, max_bytes=5_000_000, max_redirects=5,
                  headers=None, resolver=..., opener=...) -> FetchResult
def guarded_fetch_text(url, *, ...) -> str               # decoded, byte-capped — _urllib_fetcher drop-in
```

`FetchResult` = `(url: str, status: int, headers: dict, text: str)` (final URL after redirects).

Two **injection seams** keep the whole thing offline-testable with **no real network**:
- `resolver: Callable[[str, int], list[str]]` — inject a fake DNS map to test rebinding without DNS.
- `opener: Callable[..., _Response]` — inject a fake transport to assert the pinned IP + preserved
  Host it was handed, to return canned redirects (→ re-validation), and to return oversized bodies
  (→ byte cap). The default `opener` (real `http.client`) is exercised only by a
  `socket.create_connection`-monkeypatched transport test that asserts pin-IP + Host without opening
  a socket.

### 3.4 Wiring into `_urllib_fetcher`

`alpha/meta/ingest.py::_urllib_fetcher(url) -> str` is rewritten to
`return netguard.guarded_fetch_text(url, timeout=15, max_bytes=…)`. Signature unchanged, so
`fetch_url(url, fetcher=…)`'s injection seam is untouched: every existing ingest test passes its own
`fetcher=` and never exercises the default path, so those tests stay byte-identical. The default path
(no injected fetcher) now SSRF-validates. The scheme check in `fetch_url` stays (defence in depth).

The data-source fetchers (`AlpacaSource/EdgarSource/FinraSource/FloatFeed` each have their own
`_get_json` against a **fixed, operator-configured** vendor host — not user/model-supplied) are a
**separate, lower-priority seam**. Routing them through `netguard` is low-risk but perturbs live
vendor behaviour (pinned-IP + CDN multi-IP + legitimate redirects) and cannot be verified offline —
so it is a documented **follow-up** requiring a live smoke test, not part of this arc's default
wiring. `netguard` is dependency-free specifically so they can adopt it later.

---

## Part 1 — Egress ladder: M1 monitor-everything, M2 deny-by-default allowlist

### 1.1 The audit record (M1)

```python
@dataclass(frozen=True)
class SandboxEgressRecord:
    destination: str   # host (best-effort from argv) or "<undetermined>"
    method: str        # "net-run" (LocalEnv declared net) | HTTP method when known
    timestamp: str     # ISO-8601 UTC
    allowed: bool
    reason: str        # "allowlisted" | "not on allowlist" | "resolves to private IP: …" | …
```

Every declared arena net touch produces one record at the choke point. The choke point is
`LocalEnv.run(..., net=True)` — `LocalEnv`'s `net` flag is a documented no-op today; this is where it
gains an audit tap. Records go to an injected `egress_audit: Callable[[SandboxEgressRecord], None]`
sink (default: none → no record, byte-identical).

### 1.2 The allowlist shape (M2) — **this is the activity-space §10 answer**

`EgressPolicy` (`alpha/arena/egress.py`), the concrete answer to "exact `network` allowlist shape for
`LocalEnv`":

- **Hostname-based, deny-by-default.** `allow_hosts: frozenset[str]` — exact (`api.example.com`) or
  suffix (`.pypi.org` matches host and any subdomain). A destination host **not** matched is denied.
  **Raw-IP destinations are denied** (the allowlist is names; an IP literal can't be governed by a
  name allowlist and is the classic exfil shape).
- **Private/metadata-IP blocking is unconditional — even for an allowlisted host.** An allowlisted
  hostname is still resolved and every resolved IP run through `netguard.assert_public_ip`; if it
  resolves to a private/loopback/link-local/metadata IP the egress is denied regardless of the
  allowlist. This is what defeats *DNS-allowlist-rebinding* (attacker allowlists `evil.com`, points
  it at `169.254.169.254`). One code path for the IP rule — `netguard` — shared with Part 3.
- **Resource ceilings live in an image manifest; the runtime policy may only TIGHTEN.**
  `EgressCeilings(max_bytes, timeout_s, max_redirects)` come from `EgressPolicy.from_manifest(...)`.
  `policy.tighten(hosts=…, ceilings=…)` may only **intersect** the host set and **lower** ceilings;
  any attempt to widen the host set or raise a ceiling raises `ValueError`. "Policy may only tighten"
  is the charter's image-manifest rule made executable.
- **Derived-from-registry, one governance surface (charter).** For NOW the allowlist is an explicit
  set plus a named un-credentialed **dependency preset** (`PyPI/npm/GitHub/…`) approved once. The
  shape is registry-ready: when the connector egress registry lands, `from_registry(registry)`
  populates `allow_hosts` from approved connectors + the preset — `curl`/tunnels gated by the *same*
  mechanism that gates connectors, no second approval UX.
- **Fail-closed.** DNS failure/timeout, a `net=True` run whose destination can't be determined while
  a policy is attached, and any resolution error all deny.
- **Phase-split & method restriction (documented, from Codex Cloud).** A *setup phase* (model not in
  the loop) may run the broad dependency preset; the *action phase* drops to the registry-derived
  allowlist. Optional per-host GET-only method restriction, with the recorded caveat that it does
  **not** stop GET-string exfil (no content inspection — matches all three reference systems).

### 1.3 `LocalEnv` wiring (`alpha/arena/environment.py`, NOT a TCB file)

`LocalEnv(workspace, *, egress_policy=None, egress_audit=None, env=None)`. In `run`, when `net=True`
**and** `egress_policy` is attached: extract a best-effort destination host from `argv` (first
http(s) URL or host-looking token, else `<undetermined>`), `evaluate` it → a `SandboxEgressRecord`,
push to `egress_audit`, and if **denied** refuse the run (`ExecResult(ok=False, exit_code=126)`).
`egress_policy=None` (the default) → today's behaviour exactly (`net` advisory no-op, no record) →
byte-identical. The `policy.py` dispatch choke point (the TCB file) is **not touched**; egress is an
`environment.py`/`egress.py` concern, so no TCB regen.

---

## Part 2 — Two-class credential split (`alpha/arena/credentials.py`)

Charter *Security Boundary: Two-Class Credentials — the Work Token Is Contained; Everything Else
Never Enters*. Replaces today's env-var custody where the arena shell inherits `os.environ` and can
`env | grep KEY` every provider secret.

### 2.1 The two classes

- **Class A — the work token** (repo-scoped, *contained not secret*). For a repo Kairos edits as a
  task. It is sandbox-resident and readable there (containment, per charter — "the agent never sees
  the token" is retired). Two boundaries make containment load-bearing: (1) **repo-scoped** to the
  work repo only; (2) **physically incapable of reaching the Body remote**.
- **Class B — everything else** (provider API keys, vault creds). **Never enters the sandbox env.**
  For this class "never touches" holds literally.

### 2.2 Executable containment (offline, no real secrets)

```python
@dataclass(frozen=True)
class WorkToken:
    value: str
    repo_scope: frozenset[str]           # hosts/URLs this token may push to (never empty, never "*")

def build_sandbox_env(host_env, *, work_token=None, work_token_var="WORK_GIT_TOKEN",
                      keep=()) -> dict:
    # ALLOWLIST / default-deny posture: keep ONLY the known-safe non-secret set
    # (_DEFAULT_KEEP = {PATH, HOME, LANG, LANGUAGE, TERM, TZ, USER, LOGNAME, SHELL, TMPDIR, PWD,
    # HOSTNAME} + the LC_ locale family + explicit `keep=` names), inject the work token LAST, and
    # STRIP everything else. Because the default is DENY, a secret never enters regardless of its
    # NAME — Class B "Never Enters" is structural. `keep` is the escape hatch for a rare legit extra
    # var; a secret-shaped keep name is REFUSED (CredentialError) so no config re-admits a credential.

def assert_work_token_contained(token, *, body_remote_host) -> None:
    # Raises if body_remote_host is reachable from repo_scope, or scope is empty / a wildcard.
    # The "physically incapable of reaching the Body remote" invariant as a policy assertion.
```

`LocalEnv` gains `env=None`: default `None` → `subprocess.run` inherits `os.environ` (byte-identical
to today). Passing `build_sandbox_env(os.environ, work_token=…)` runs the subprocess with **only**
the allowlisted env + the work token — Class B stripped, Class A contained. **Why an allowlist, not a
denylist (fixed on review):** the charter says Class B "Never Enters", which is a default-deny
property. A substring denylist over secret-shaped markers can never be complete — `OPENAI_KEY`,
`DATABASE_URL` / `REDIS_URL` (which embed `user:pass@host`), `GH_PAT`, `BEARER`, `SSH_AUTH_SOCK`,
`NETRC` all slip a marker denylist — so a denylist fails the primitive's stated purpose the moment
it is wired. The allowlist keeps only enumerated non-secret vars, so containment holds regardless of
the secret's name. The work-token var is stripped like any other name (it is not in the keep set)
then re-injected explicitly, so custody is only ever the value we chose to place.

### 2.3 Honest limit

`LocalEnv` is not a security boundary (repo CLAUDE.md; the compensating control is workbench's boot
assert that the brain lives outside the workspace). `build_sandbox_env` removes Class B from the
subprocess **env**, which is real; it does not stop a subprocess reading a secret from a file the
operator left in the workspace, nor is the work token hidden from code running in the sandbox
(containment, not secrecy — as the charter states). Kernel-side credential custody (Applier-style
git, per-session minting) stays deferred to A10.

---

## 4. TCB accounting

| File | TCB? | Change | Regen? |
|---|---|---|---|
| `alpha/meta/netguard.py` | **no** (NEW; not in `TCB_FILES`) | new module | no |
| `alpha/arena/egress.py` | **no** (NEW) | new module | no |
| `alpha/arena/credentials.py` | **no** (NEW) | new module | no |
| `alpha/meta/ingest.py` | **no** (not in `TCB_FILES`) | `_urllib_fetcher` → `netguard` | no |
| `alpha/arena/environment.py` | **no** (not in `TCB_FILES`) | `LocalEnv` gains `egress_policy/egress_audit/env` kwargs | no |
| `alpha/arena/policy.py` | **YES** (in `TCB_FILES`) | **untouched** — byte-identical | no |

No file in `TCB_FILES` changes, so `scripts/gen_tcb_lock.py --check` stays 0 and no regen is needed.
**Recommendation for the user (human-only red-line, not done here):** `netguard.py` is
security-critical kernel-side code and belongs in `TCB_FILES` once this lands — adding it is a
highest-approval human act per modification-ladder §3, so it is flagged, not performed.

## 5. Test matrix (offline, keyless, no real network)

**netguard (priority):** rejects loopback/private/link-local/reserved/metadata IP literals; allows a
public IP literal; DNS-rebinding — a hostname resolving to a private IP is rejected (resolve-once via
fake resolver); mixed answer `[public, private]` rejected; IPv4-mapped IPv6 loopback rejected;
resolve-once-then-pin — the opener is handed the *resolved* IP with the *original* Host; a redirect
to a private host is re-validated and blocked; a redirect chain past the budget errors; byte cap
truncates an oversized body; a legitimate public destination is allowed end-to-end (fake resolver +
fake opener); `gaierror` → fail-closed; the default transport pins the IP + preserves Host (asserted
by monkeypatching `socket.create_connection`, no socket opened). **ingest:** default `_urllib_fetcher`
routes through the guard (a private URL is blocked); existing injected-`fetcher=` tests unchanged.
**egress:** a record is produced at the `LocalEnv` choke point on `net=True`; deny-by-default denies
an off-list host and allows an on-list host; an allowlisted host resolving to a private IP is denied;
a raw-IP destination is denied; `tighten` may narrow, widening raises; `egress_policy=None` is
byte-identical. **credentials:** `build_sandbox_env` keeps only the allowlisted non-secret set (`PATH`, `LC_ALL`, …)
and injects only the work token; secrets a marker denylist would MISS (`OPENAI_KEY`, `DATABASE_URL`,
`GH_PAT`, `BEARER`, `SSH_AUTH_SOCK`, `NETRC`, …) are all stripped by the default-deny posture; a
secret-shaped var is stripped even when it collides with the work-token var name (custody is only the
injected value); `keep=` admits an extra non-secret var but REFUSES a secret-shaped name
(`CredentialError`); `assert_work_token_contained` raises when the body remote is reachable from
scope / scope is empty / a wildcard, and passes for a disjoint scope; `LocalEnv(env=None)` is
byte-identical.

## 6. Honest limits / what remains before non-localhost serving is safe

- **`LocalEnv` egress is advisory.** Real per-packet network confinement needs `SandboxedEnv`
  (kernel netns / nftables default-drop) — A10, deferred. The ladder here monitors + gates *declared*
  intent and IP-validates allowlisted hosts; it does not stop a subprocess opening its own socket.
- **No content inspection / DLP.** GET-string exfil to an allowlisted host survives (charter records
  this residual for all three reference systems).
- **SSRF guard covers in-process fetches only.** It hardens `_urllib_fetcher` now; the data-source
  `_get_json` methods are a documented follow-up (live-smoke-test-gated).
- **Credential split protects the env, not the filesystem**, and the work token is contained not
  hidden. Kernel-side git custody + per-session minting stay deferred (A10 / *Work-credential
  hardening*).
- **Before non-localhost / multi-user serving:** the SSRF guard (this arc) is the precondition and is
  met for the cockpit fetcher; still required are the `SandboxedEnv` kernel egress boundary (A10),
  the `ingest_attachments` file/size cap already present (§3 small-pool) extended with the network
  leg, and the CSRF/Origin check on the loopback approval surface — all named as riding this same
  precondition and NOT closed by this arc.
