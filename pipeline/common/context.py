"""Run context shared by every stage: paths, the validated storyboard, flags."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .env import load_dotenv
from .storyboard import load_storyboard

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Ctx:
    root: Path
    storyboard_path: Path
    sb: dict[str, Any]
    outputs: Path
    runs_log: Path
    run_id: str
    force: bool = False
    only_shots: set[str] | None = None
    warnings: list[str] = field(default_factory=list)

    def stage_dir(self, *parts: str) -> Path:
        d = self.outputs.joinpath(*parts)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def selected(self, shot_id: str) -> bool:
        return self.only_shots is None or shot_id in self.only_shots

    @property
    def shots(self) -> list[dict[str, Any]]:
        return self.sb["shots"]


def make_ctx(*, force: bool = False, only_shots: set[str] | None = None,
             storyboard: str | None = None) -> Ctx:
    """Build a context. Env overrides (used by tests): HERITAGE_STORYBOARD,
    HERITAGE_OUTPUTS, HERITAGE_RUNS_LOG."""
    load_dotenv(REPO_ROOT / ".env")
    sb_path = Path(storyboard or os.environ.get("HERITAGE_STORYBOARD", REPO_ROOT / "storyboard.json")).resolve()
    outputs = Path(os.environ.get("HERITAGE_OUTPUTS", REPO_ROOT / "outputs")).resolve()
    runs_log = Path(os.environ.get("HERITAGE_RUNS_LOG", REPO_ROOT / "runs.jsonl")).resolve()
    sb, warnings = load_storyboard(sb_path, REPO_ROOT)
    if only_shots:
        unknown = only_shots - {s["id"] for s in sb["shots"]}
        if unknown:
            raise SystemExit(f"Unknown shot id(s): {', '.join(sorted(unknown))}")
    run_id = os.environ.get("HERITAGE_RUN_ID") or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    outputs.mkdir(parents=True, exist_ok=True)
    return Ctx(root=REPO_ROOT, storyboard_path=sb_path, sb=sb, outputs=outputs,
               runs_log=runs_log, run_id=run_id, force=force,
               only_shots=only_shots or None, warnings=warnings)
