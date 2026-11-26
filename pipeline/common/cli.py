"""Shared CLI flags so every stage can run standalone: python -m pipeline.<stage>."""
from __future__ import annotations

import argparse
import sys
from typing import Callable

from .context import Ctx, make_ctx
from .storyboard import StoryboardError


def parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--storyboard", help="path to storyboard.json (default: repo root)")
    p.add_argument("--shots", help="comma-separated shot ids to limit per-shot stages, e.g. s03,s07")
    p.add_argument("--force", action="store_true", help="ignore cache and regenerate selected artifacts")
    p.add_argument("--offline", action="store_true", help="use the stub provider for every model (no keys/network)")
    return p


def ctx_from_args(args: argparse.Namespace) -> Ctx:
    only = {s.strip() for s in args.shots.split(",") if s.strip()} if args.shots else None
    try:
        ctx = make_ctx(force=args.force, only_shots=only, storyboard=args.storyboard, offline=args.offline)
    except StoryboardError as e:
        print(f"✗ {e}", file=sys.stderr)
        raise SystemExit(2) from None
    for w in ctx.warnings:
        print(f"  ⚠ {w}", file=sys.stderr)
    return ctx


def stage_main(name: str, run: Callable[[Ctx], None]) -> None:
    args = parser(f"Run the '{name}' stage").parse_args()
    ctx = ctx_from_args(args)
    print(f"▶ {name}")
    run(ctx)
