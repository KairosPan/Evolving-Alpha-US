# alpha/data/integrity_check.py
"""D6: CHECKSUMS integrity manifest — write once at capture time, verify at read time.

Manifest format: `CHECKSUMS` at the PIT root, one line per regular file under root (except
CHECKSUMS itself): `"{sha256}  {posix-relpath}"`, sorted by relpath. `write_checksums` produces
it (called last by `alpha.data.capture.capture_window`, so both capture CLIs inherit it);
`verify_checksums` re-hashes every file on disk and diffs it against the manifest, typing each
discrepancy `mismatch:` (digest differs), `missing:` (manifest lists a file that's gone), or
`extra:` (a file on disk with no manifest entry).

A MISSING manifest is NOT an error — every offline tmp-store test builds a `PITStore` directly
(never through `capture_window`) and pre-D6 captured windows have no `CHECKSUMS` at all — so it
prints a warning and returns `[]` in BOTH the fail-closed and warn postures. Verification is a
script-main concern (wired into the fail-closed producers `run_verdict`/`save_decisions`/
`refine_live` and the warn-only `save_evolution`/`scan_tradeable`), never inside `PITStore` or
`SnapshotSource` construction — those get built manifest-less throughout the offline suite.
"""
from __future__ import annotations

from pathlib import Path

from alpha.integrity import sha256_file

MANIFEST_NAME = "CHECKSUMS"


def write_checksums(root: Path) -> Path:
    """Walk `root`, hash every regular file except the manifest itself, and write the sorted
    `"{sha256}  {relpath}"` manifest. Returns the manifest path."""
    root = Path(root)
    manifest = root / MANIFEST_NAME
    entries = [(p.relative_to(root).as_posix(), sha256_file(p))
               for p in root.rglob("*") if p.is_file() and p != manifest]
    entries.sort(key=lambda e: e[0])
    lines = [f"{digest}  {rel}" for rel, digest in entries]
    manifest.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"CHECKSUMS written — commit it: git add -f {root}/CHECKSUMS")
    return manifest


def verify_checksums(root: Path, *, fail_closed: bool) -> list[str]:
    """Re-hash `root` against its CHECKSUMS manifest. No manifest -> warn + `[]` (both postures).
    Otherwise return typed problem strings (`mismatch:`/`missing:`/`extra:`); `fail_closed` raises
    `RuntimeError` joining them, else each is printed as a warning and the list is returned."""
    root = Path(root)
    manifest = root / MANIFEST_NAME
    if not manifest.exists():
        print(f"warning: no CHECKSUMS in {root} — pre-manifest window (re-capture to pin it)")
        return []

    recorded: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, rel = line.split(maxsplit=1)
        recorded[rel] = digest

    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*")
               if p.is_file() and p != manifest}

    problems: list[str] = []
    for rel in sorted(set(recorded) | on_disk):
        if rel in recorded and rel not in on_disk:
            problems.append(f"missing: {rel}")
        elif rel in on_disk and rel not in recorded:
            problems.append(f"extra: {rel}")
        elif sha256_file(root / rel) != recorded[rel]:
            problems.append(f"mismatch: {rel}")

    if fail_closed and problems:
        raise RuntimeError("\n".join(problems))
    for p in problems:
        print(f"warning: {p}")
    return problems
