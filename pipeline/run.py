"""Run the whole pipeline (or a subset of stages) in order.

    python -m pipeline.run                      # everything
    python -m pipeline.run keyframes shots      # just these stages
    python -m pipeline.run --shots s03 --force  # re-roll one shot's per-shot artifacts
"""
from __future__ import annotations

import importlib
import time

from . import STAGES
from .common.cli import ctx_from_args, parser
from .common.media import check_ffmpeg


def main() -> None:
    p = parser("Run The Heritage Short pipeline")
    p.add_argument("stages", nargs="*", metavar="STAGE", help=f"stages to run (default: all): {' '.join(STAGES)}")
    args = p.parse_args()
    bad = [s for s in args.stages if s not in STAGES]
    if bad:
        p.error(f"unknown stage(s) {bad}; choose from {STAGES}")
    stages = args.stages or STAGES
    ctx = ctx_from_args(args)
    check_ffmpeg()
    print(f"run_id={ctx.run_id}  storyboard={ctx.storyboard_path.name}  stages={','.join(stages)}")
    t_all = time.monotonic()
    for name in STAGES:
        if name in stages:
            t0 = time.monotonic()
            print(f"▶ {name}")
            importlib.import_module(f"pipeline.{name}").run(ctx)
            print(f"  ({time.monotonic() - t0:.1f}s)")
    print(f"✓ done in {time.monotonic() - t_all:.1f}s — telemetry appended to {ctx.runs_log.name}")


if __name__ == "__main__":
    main()
