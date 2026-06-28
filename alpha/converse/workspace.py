"""Per-project git-backed artifact directory (subprocess git, no new dep)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from alpha.eval.decision import DecisionPackage


class Workspace:
    """A per-project directory whose contents are tracked by an isolated git repo."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    @property
    def root(self) -> Path:
        """The resolved workspace directory (e.g. the LocalEnv cwd for arena tools)."""
        return self._root

    def init(self) -> None:
        """Idempotent git init + local identity config; no-op if .git already exists."""
        self._root.mkdir(parents=True, exist_ok=True)
        if (self._root / ".git").exists():
            return
        self._run(["git", "init", "-q"])
        self._run(["git", "config", "user.name", "alpha"])
        self._run(["git", "config", "user.email", "alpha@local"])

    def commit_artifact(self, relpath: str, data: str, message: str) -> str:
        """Write *data* to *relpath* under root, stage and commit; return HEAD SHA."""
        target = (self._root / relpath).resolve()
        if not target.is_relative_to(self._root):
            raise ValueError(
                f"relpath {relpath!r} escapes workspace root {self._root}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding="utf-8")
        self._run(["git", "add", "--", relpath])
        self._run(["git", "commit", "-q", "-m", message])
        return self._run(["git", "rev-parse", "HEAD"]).stdout.strip()

    def put_decision(self, pkg: DecisionPackage) -> str:
        """Persist *pkg* as ``<date>.json`` and commit it; return HEAD SHA."""
        filename = f"{pkg.date}.json"
        return self.commit_artifact(filename, pkg.model_dump_json(), f"decision: {pkg.date}")

    def artifacts(self) -> list[str]:
        """Committed artifact paths in this workspace (git ls-files), or [] if not a repo."""
        try:
            out = self._run(["git", "ls-files"])
            return [line for line in out.stdout.splitlines() if line.strip()]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _env(self) -> dict[str, str]:
        """Isolated git env: deterministic author identity, HOME → root so no global config leaks."""
        return {
            **os.environ,
            "GIT_AUTHOR_NAME": "alpha",
            "GIT_AUTHOR_EMAIL": "alpha@local",
            "GIT_COMMITTER_NAME": "alpha",
            "GIT_COMMITTER_EMAIL": "alpha@local",
            "HOME": str(self._root),
        }

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            check=True,
            cwd=self._root,
            capture_output=True,
            text=True,
            env=self._env(),
        )
