"""Summarise runs.jsonl: calls, cache hits, latency, GPU minutes, list-price cost.

    python -m pipeline.costs              # all runs
    python -m pipeline.costs --last       # most recent run_id only
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from .common.context import REPO_ROOT


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=os.environ.get("HERITAGE_RUNS_LOG", REPO_ROOT / "runs.jsonl"))
    ap.add_argument("--last", action="store_true", help="only the most recent run_id")
    ap.add_argument("--markdown", action="store_true", help="print a table to paste into COSTS.md")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.log).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        print("runs.jsonl is empty — run `make film` first.")
        return
    if args.last:
        last = rows[-1]["run_id"]
        rows = [r for r in rows if r["run_id"] == last]

    agg: dict[tuple[str, str], dict] = defaultdict(lambda: {"calls": 0, "hits": 0, "errors": 0, "latency": 0.0,
                                                            "gpu": 0.0, "gpu_unknown": 0, "usd": 0.0, "usd_unknown": 0})
    for r in rows:
        a = agg[(r["stage"], r["model"])]
        a["calls"] += 1
        a["hits"] += r["cache_hit"]
        a["errors"] += r["status"] not in ("ok", "cached")
        a["latency"] += r["latency_sec"] or 0
        if r["gpu_minutes"] is None:
            a["gpu_unknown"] += 1
        else:
            a["gpu"] += r["gpu_minutes"]
        if r["list_price_equivalent_usd"] is None:
            a["usd_unknown"] += 1
        else:
            a["usd"] += r["list_price_equivalent_usd"]

    def fmt_unknown(v: float, unknown: int, spec: str) -> str:
        return f"{v:{spec}}" + (f" (+{unknown} unknown)" if unknown else "")

    header = ["stage", "model", "calls", "cache hits", "errors", "latency s", "GPU min", "list USD"]
    table = [[s, m, str(a["calls"]), str(a["hits"]), str(a["errors"]), f"{a['latency']:.1f}",
              fmt_unknown(a["gpu"], a["gpu_unknown"], ".3f"), fmt_unknown(a["usd"], a["usd_unknown"], ".4f")]
             for (s, m), a in sorted(agg.items())]
    runs = len({r["run_id"] for r in rows})
    if args.markdown:
        print("| " + " | ".join(header) + " |\n|" + "---|" * len(header))
        for t in table:
            print("| " + " | ".join(t) + " |")
    else:
        widths = [max(len(x) for x in col) for col in zip(header, *table)]
        for line in [header, *table]:
            print("  ".join(x.ljust(w) for x, w in zip(line, widths)))
    print(f"\n{len(rows)} logged calls across {runs} run(s). 'unknown' = provider/pricing not reported; never estimated.")


if __name__ == "__main__":
    main()
