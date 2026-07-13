# A4 — Session organ, phase 1 (design)

Status: drafted 2026-07-13. Closes **G1 (first slice)**. Additive, offline byte-identical by
default. Authority chain: charter (*Trust Roots & Principal Authentication*; *The External Channel*;
*Session Is Not the Context Window → Traces*; *Memory Design → scope labels from day one*) >
Backend-Design.md G1 > DEVELOPMENT-PLAN §2 A4 > this spec > code.

A4 lands the **non-deferred kernel of the deferred Traces design** (charter *Session Is Not the
Context Window → Traces*): the four pieces "carved out non-deferred because decided mechanisms
already depend on them" — the **principal-origin stamp**, the **append-time integrity chain**, the
**attribution tuple**, and the **kernel counter-event schema** — plus the **scope label** the
charter names as un-retrofittable. Everything richer in Traces stays deferred.

## Why now (the un-retrofittable risks)

Two of A4's three parts close a risk that **cannot be retrofitted** onto data already written:

- **Origin (a).** Today a tool result is re-injected into the conversation as a `role="user"`
  message whose text carries a `"[tool:{name} result]"` **string prefix** (`alpha/converse/loop.py`).
  Tool-result origin is therefore a *text convention the model itself can forge*: a model that
  emits the literal string `"[tool:search result] …"` is byte-indistinguishable from a real tool
  result once persisted. No principled origin class exists. The charter's *Event-level principal
  origin* rule — "stamped at intake, from the physical entry path, never inferred from content" —
  is the fix.
- **Scope (c).** The charter's *Memory Design → scope labels from day one* rule says every
  learned-context write must carry a scope field so learning "can be split later when a second
  user or instance arrives." Until A4, learning accumulates **unlabeled** — a recorded timing
  deviation (2026-07-10). Labels added now ride every future write; they can never be recovered
  for writes that already happened unlabeled.

Part (b) (integrity chain) is corruption-detection groundwork for A5/A10.

## Vocabulary home: `alpha/trace.py`

One new leaf module, `alpha/trace.py` — the non-deferred trace kernel. Imports only pydantic,
typing, and `alpha.__version__` (no `alpha.harness`/`alpha.memory` imports → no cycle, safe for the
low-level `alpha/llm/chat.py` to import). Mirrors the existing top-level cross-cutting utilities
`alpha/redact.py` and `alpha/integrity.py`. Houses:

- `MessageOrigin = Literal["kernel", "system", "tool", "user", "model"]` — the principal-origin
  vocabulary, adapted from the charter's origin channels to this repo's message capture.
- `is_tool_result(msg) -> bool` — the consumer-side predicate: `getattr(msg, "origin", None) == "tool"`.
  Consumers key off the **stamp**, never the `"[tool:"` string.
- `Scope = Literal["agent-global", "per-party", "per-session"]` + `DEFAULT_SCOPE = "agent-global"`
  (the charter's exact three values, verbatim including hyphens).
- `AttributionTuple(BaseModel, frozen)` — `body_digest: str | None`, `model_id: str | None`,
  `kernel_version: str` — plus `attribution_of(*, body_digest, model_id) -> AttributionTuple`
  filling `kernel_version` from `alpha.__version__`.
- `KernelCounterEvent(BaseModel, frozen)` — the minimal per-component counter schema
  (schema-only; live derivation is the deferred Component-Lifecycle arc).

## (a) Origin-stamp vocabulary + emit seam

**Field.** `ChatMessage` (`alpha/llm/chat.py`) and the sonia `Message` (`alpha/meta/models.py`)
each gain `origin: MessageOrigin | None = None`. Default `None` = **legacy / unstamped** — the
honest value for a message with no recorded physical entry path (mirrors `EditProvenance = None`
for legacy/ungated records). `None` never equals `"tool"`, so a legacy message can never be
mistaken for a stamped tool result.

**Emit seam** (stamp from the physical entry path, never inferred from content):
- `converse_project` (`alpha/converse/session.py`): the user's turn → `origin="user"`.
- `run_conversation` (`alpha/converse/loop.py`): the model's reply → `origin="model"`; the
  re-injected tool result → `origin="tool"`.
- sonia `app.py`: the user turn → `origin="user"`; the assistant turn → `origin="model"`.

**Persistence.** `SqliteProjectStore` (converse) gains an `origin` column on `messages` with a
guarded `ALTER TABLE` migration (mirrors `EpisodeStore`'s `kind` migration); `get()` restores it.
Sonia's `Message` persists via `model_dump(mode="json")` so the field rides for free.

**Forged-origin regression (acceptance).** A model-authored message whose text is literally
`"[tool:search result]\n{…}"` carries `origin="model"`; a real re-injected tool result carries
`origin="tool"`. The naive string check `text.startswith("[tool:")` matches **both** (proving the
string convention is forgeable); `is_tool_result()` distinguishes them (proving the stamp is not).
The property survives a persist→reload round trip.

**Honest limit.** As in the charter, the stamp authenticates *channel of entry*, not *authorship*:
a user who pastes model-authored text still produces a `user`-stamped message. A4 narrows the
tool-result-forgery edge; the user-as-courier edge is out of scope (charter *Trust Roots*).

## (b) Hash-chained EditLog + external anchor

`edit_log.py` **is TCB.** Change is minimal-additive; no existing enforcement/immutability
behavior changes.

**Fields.** `EditRecord` gains `prev_chain_hash: str | None = None` and
`chain_hash: str | None = None` (default `None` = unchained). The chain hash covers the record's
content **excluding the two chain fields**, salted by the predecessor's `chain_hash`:
`chain_hash = sha256_canonical_json({"prev": prev_chain_hash, "rec": <record minus chain fields>})`
via `alpha.integrity` (the one canonicalizer).

**Finalized at persist time.** The store's `save()` calls `log.finalize_chain()` before dumping —
`SnapshotStore.save` (TCB, +1 line) and `LiveBrainStore.save` (non-TCB). `to_dict()` stays **pure**
(no finalize): serialization is not persistence. This is load-bearing — the evolution packet
(`alpha/meta/evolution.py`, TCB) compares a delta dumped via per-record `model_dump` against the
same delta dumped via `to_dict`, so `to_dict` **must** equal `model_dump` and must not inject
chain fields the other side lacks. Keeping `to_dict` pure leaves `evolution.py` untouched and
byte-identical. Persist-time (not append-time) because `stamp_last()` rewrites the last record
*after* append; `stamp_last` clears the rewritten record's chain so the next `finalize_chain`
recomputes it.

**Finalize from genesis; legacy tolerated on load, chained on first persist.** `finalize_chain()`
hashes every currently-**unchained** record from genesis, preserving already-chained records (a
loaded, previously-persisted brain keeps its hashes byte-for-byte — idempotent). A legacy snapshot
(records with no chain fields) is tolerated by `verify_chain()` **on load** (an unchained prefix,
nothing to check); on its first persist under the feature the whole log is chained forward. The
adopt path (`evolution.py`) reconstructs a log from a packet whose delta is unchained and re-stamps
provenance; `bstore.save` then `finalize_chain`s **after** the re-stamp, so the adopted brain's
chain covers the stamped content — the reason `to_dict` is pure and there is no sealing (sealing
would leave adopted deltas permanently unchained). The honest limit below (external anchor) covers
"cannot prove pre-feature history", so chaining a legacy log forward adds no false assurance.

**`verify_chain() -> bool`.** Walks records: a leading run of unchained records is tolerated (the
legacy prefix); once the chained region begins, each record's `prev_chain_hash` must equal the
prior chained record's `chain_hash` and its `chain_hash` must recompute; a `None` **hole after
chaining started** = corruption/reorder → `False` (unless it is a pure trailing not-yet-finalized
run). Verification is O(n), run at load/rollback.

**External anchor.** `EditLog.chain_head()` returns the last record's `chain_hash` (or `None`).
Surfaced on `/evolution` via `save_evolution.evolution_view(...)["chain_head"]` — the operator can
eyeball or git-commit it. **Honest limit, stated in code + here:** under the accepted T2-shell
operator-trust posture (Axiom H — host is total root; kairos-mining §2.9) the chain is
**corruption-detection only** without the anchor. It detects storage-side loss/reorder/interior
edit below the host root; it does **not** detect the host itself (rewrite-and-recompute), an
emit-side omission, or tail truncation past the last recorded head. Value downgraded 4→2-3. WORM /
signed heads stay deferred with Tier 2.

**Ordering invariant: redact (A1) before hash (A4).** The EditLog chain hashes **verbatim**
record content — `EditRecord.payload` is a rollback-replay payload that `alpha/redact.py` forbids
routing through redaction, so the audit log is not redacted. Redaction runs on the **session
message** stream (`SqliteProjectStore`, `SessionStore`), which A4 does not chain. The two streams
do not compose in A4; the invariant is pinned forward-looking for A10's `BodyLog` / any session-log
chain: **the persist waist's redacted output is what a hash would cover** — a secret is redacted
*before* it could enter a hash preimage, never after. Pinned by a regression at the message store.

**Rollback acceptance.** `verify_chain()` is green on a log loaded from a snapshot, and stays green
across `HarnessManager.rollback_to(v)` (the restored log was chained when saved).

## (c) Scope label on every learned-context write

`Lesson` (`alpha/harness/memory.py`), `Skill` (`alpha/harness/skill.py`), and `Episode`
(`alpha/memory/episodes.py`) each gain `scope: Scope = DEFAULT_SCOPE`.

- Lessons/skills persist through `HarnessState.to_dict/from_dict` (`model_dump`/`model_validate`)
  — the field rides automatically; `from_seed` leaves unlabeled seeds at the default.
- Episodes persist through `EpisodeStore` (**TCB**): `scope` joins `_COLS`, `_SCHEMA` (with
  `DEFAULT 'agent-global'`), `_row_to_episode`, and a guarded `ALTER TABLE` migration — a minimal
  additive change mirroring the existing `kind` migration exactly. Persisting (not
  in-memory-only-defaulting) is the point: the charter's un-retrofittable rationale requires the
  label to be captured **at write time and durably**.

**Default = `"agent-global"` — a judgment call, flagged for the user.** Today's entire
lessons/skills/episodes corpus is Kairos's trading *craft*, which the charter classes as
agent-global ("Kairos's craft"), and the charter states the scope-mismatch check is "vacuous under
a single User." So agent-global is the honest description of existing writes, not a widening. A4
lands **only the labels**; the wider-than-evidence **gate** that consumes them is **A8**, which
owns how to treat unlabeled/legacy evidence scope (e.g. fail-toward-strict). If the user prefers a
fail-closed narrow default (`per-session`) for the evidence leg, that is an A8 policy decision on
top of these labels.

## Trace pieces (all four non-deferred)

1. **Principal-origin stamp** — part (a).
2. **Append-time integrity chain** — part (b).
3. **Attribution tuple** (`body-version × model-id × kernel-version`) — `AttributionTuple` +
   `attribution_of()`. A1's `h_digest` (`harness_digest`) is the body-version leg (composed by the
   caller and passed in, so `alpha/trace.py` stays harness-free). Stamped on `ProjectTurn`
   (`attribution: AttributionTuple | None = None`), populated in `converse_project`:
   `body_digest=harness_digest(h)`, `model_id=getattr(chat_llm, "model", None)`,
   `kernel_version=alpha.__version__`. Watchdog incident attribution (charter *Edit Acceptance
   Protocol*) is the decided mechanism that depends on it.
4. **Kernel counter-event schema** — `KernelCounterEvent`: `component_id`, `component_class`,
   `invocations`, `exceptions`, `latency_ms`, `cost`, `origin: MessageOrigin = "kernel"`.
   Schema-only; the live kernel-derived counter is the deferred Component-Lifecycle arc (charter:
   "counters ride the session event log as kernel-stamped events"). Landing the schema now
   reconciles the v2.5 prerequisite with the Traces deferral.

## TCB accounting

Three TCB files touched, all minimal-additive, `tcb.lock` regenerated (`python
scripts/gen_tcb_lock.py`), zero enforcement/immutability change:

- **`alpha/harness/edit_log.py`** (+66/−1) — chain fields on `EditRecord` +
  `finalize_chain`/`verify_chain`/`chain_head` + `_record_chain_hash` helper + `stamp_last`
  chain-reset. `to_dict`/`from_dict` stay pure. The append-only audit contract is unchanged; the
  chain is a read-time integrity check, never a write gate.
- **`alpha/harness/snapshot.py`** (+1) — `SnapshotStore.save` calls `log.finalize_chain()` before
  dumping. The version authority / atomic-checkpoint behavior is unchanged.
- **`alpha/memory/store.py`** (+7/−3) — one `scope` column in `_COLS`/`_SCHEMA`/`_row_to_episode`
  + a guarded `ALTER TABLE` migration (mirrors the existing `kind` migration). PIT recall
  (`for_asof`) unchanged.

`manager.py` and `evolution.py` are **untouched** — the pure-`to_dict` design keeps the evolution
packet's serialization consistent, and rollback flows through `SnapshotStore`. Scope on
lessons/skills rides existing harness serialization (`state.py`, non-TCB).

## Test plan (TDD)

`tests/harness/test_edit_log_chain.py`, `tests/trace/test_trace_vocab.py`,
`tests/converse/test_origin_stamp.py`, `tests/memory/test_scope_label.py`:

- forged-origin regression (model `"[tool:…]"` string ≠ stamped tool result; survives persist).
- `verify_chain()` green on a fresh chained log; green across a `rollback_to`; green on a
  legacy unchained-prefix log; **red** on an interior tampered/holed record.
- scope label present on new Lesson/Skill/Episode; legacy (unlabeled) reads default to
  agent-global; episode scope round-trips through `EpisodeStore` (incl. the migration path).
- attribution tuple composed + stamped on a live `converse_project` turn; `kernel_version` present.
- `KernelCounterEvent` validates and is kernel-origin.
- redact-before-hash: a secret in message text is redacted by the store before persistence; a
  hash over the stored text = hash(redacted) ≠ hash(raw).
- default-path byte-identity: brain/episode/turn round-trips unchanged when the new fields are at
  their defaults.

## Deliberately not done

- The live kernel-derived counter (Component-Lifecycle arc) — only the schema lands.
- Chaining the **session** message log — A4 chains the deliberation/EditLog only; session-log
  integrity is A10's `BodyLog`.
- The wider-than-evidence **gate** — A8 (A4 lands the labels A8 consumes).
- Persisting the message-**origin** or the attribution tuple as their own hash-chain — A4 stamps
  and persists them; chaining the session log is A10's `BodyLog`.
- WORM / signed chain heads / an out-of-band committed anchor file — deferred with Tier 2 (honest
  limit above); A4 surfaces the head on `/evolution` only.
