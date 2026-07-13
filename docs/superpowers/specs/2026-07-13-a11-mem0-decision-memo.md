# A11 — Mem0 store-of-record: DECISION MEMO (needs user ratification)

**Status:** DECISION MEMO — awaits USER decision. Per the authority chain (charter > Backend-Design >
plan > code), **code never wins silently**: this memo must be resolved (adopt OR amend the charter)
before any A11 code. No code written.

## The conflict

- **Charter (2026-07-09, user-ratified — *Memory Design → Decision for SoniaKairos*):** memory's
  **store of record is Mem0 OSS** — the Applier writes `add(infer=False)` verbatim, Kairos reads
  retrieval-only, the git journal is reconcile-authoritative.
- **This repo's substrate (as built):** H-lessons (in `HarnessState`, in `brain.json`) +
  `EpisodeStore` (SQLite `brain.db`). PIT-keyed (`learned_asof`), `for_asof` masking, the
  observation-channel bypass, verdict-symmetric `recall_store`. **No Mem0 anywhere.** A4 just added
  scope labels + a hash-chained EditLog; A5 added a git Body audit; A3 added content-addressed
  offload — all on the SQLite/JSON substrate.

The charter names Mem0 the store of record; the code has diverged. The authority rule says: decide
explicitly — **adopt** or **amend the charter to record permanent divergence** — never let the
divergence stand silently.

## Option A — ADOPT Mem0 (conform to the charter)

Map Mem0 (+ journal-replay reconcile) onto the existing gate/waist: the Applier writes
`add(infer=False)` to Mem0 at the `try_apply_op` landing; Kairos reads retrieval-only; the git
journal (now A5's Body-git + A4's hash-chained EditLog) stays reconcile-authoritative.

- **For:** honors the ratified charter; Mem0's retrieval/embedding machinery for semantic recall;
  a real external store-of-record (vs a single-file brain).
- **Against / cost:**
  - A **new hard dependency** (Mem0 OSS + its embedding/vector backend) into a codebase whose entire
    test suite is **offline, keyless, no-new-deps** (1775 tests). Mem0's `add`/`search` want an
    embedder; keeping tests offline means a `FakeMem0` seam + a real-Mem0 path that's only
    live-smoke-tested — a permanent two-path burden.
  - **Re-plumbs the PIT firewall** through a third party: `learned_asof` masking, `for_asof`
    caps, the verdict-symmetric read-only `recall_store`, the observation-channel bypass, and the
    `kind={trade,task}` fence are all load-bearing and currently OURS to enforce. Mem0's recall
    ordering/dedup is not PIT-aware — we'd have to wrap every read, re-proving symmetry.
  - **Duplicates** what A2–A7 just hardened on the SQLite/JSON substrate (scope labels, hash-chain,
    git audit, offload, forgery-resistant gate) — much of it would need re-doing against Mem0.
  - A6's spend metering now covers `make_client`; Mem0's embedder is a NEW un-metered LLM/network
    egress surface (interacts with A9's egress allowlist).

## Option B — AMEND the charter (record permanent divergence)

Amend the charter's *Memory Design* decision to record that SoniaKairos's store of record is the
**H-lessons + `EpisodeStore` (SQLite/JSON)** substrate, with the git journal (A5) + hash-chained
EditLog (A4) as the audit/reconcile authority — and that Mem0 is **not adopted**, with the reasons
above. Keep a Mem0 adapter as a *possible future retrieval backend behind the existing recall seam*
if semantic recall is later wanted, without making it the store of record.

- **For:** the substrate is already built, PIT-safe, offline-testable, and just hardened by A2–A9;
  no new dependency; no re-plumbing of the firewall; the charter becomes accurate.
- **Against:** overrides a user-ratified charter decision — which is precisely why **only the user
  can make this call** (amending upstream is a user/charter act, not a code act).

## Recommendation (advisory only — the user decides)

**Option B (amend the charter)** is the lower-risk, lower-cost path and matches what's actually
built and hardened: the SQLite/JSON substrate is PIT-safe, offline, dependency-free, and now carries
scope labels + a hash-chained EditLog + a git Body audit + content-addressed offload. Adopting Mem0
would re-plumb the PIT firewall through a third party and add a hard dependency to a deliberately
offline/keyless suite, re-doing much of A2–A9's hardening — a large cost to conform to a decision the
substrate has already outgrown. A Mem0 *retrieval adapter* behind the existing recall seam remains a
clean future option if semantic recall is wanted, without ceding store-of-record.

But this is a **charter-level decision that is yours** — the authority chain forbids code from
settling it. If you prefer Option A (adopt Mem0), say so and it becomes an arc; if Option B, I'll
draft the exact charter amendment text for your approval (I will not edit the charter without it).

## What happens next either way

- **Option A chosen →** an A11 build arc: Mem0 behind a `FakeMem0`-tested seam at the write-waist +
  read side, re-proving PIT masking / verdict symmetry / the kind fence against Mem0; A9 egress
  allowlist entry for the embedder; A6 metering of the embedder.
- **Option B chosen →** I draft the charter amendment (for your sign-off), then close G9 in
  Backend-Design as "divergence recorded, Mem0 not adopted; adapter behind the recall seam if ever
  wanted."
- **No choice →** G9 stays open; A11 is the one architecture item that cannot proceed without you.
