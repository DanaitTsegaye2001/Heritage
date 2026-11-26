"""Tests: schema/semantic validation and selective regeneration (stub providers, low-res)."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.common.storyboard import StoryboardError, load_storyboard  # noqa: E402

BASE = json.loads((ROOT / "storyboard.json").read_text())


def write(sb: dict, d: Path) -> Path:
    p = d / "storyboard.json"
    p.write_text(json.dumps(sb, indent=2))
    return p


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def check(self, sb):
        return load_storyboard(write(sb, self.tmp), ROOT)

    def test_sample_storyboard_is_valid(self):
        self.check(BASE)

    def test_rejects_too_few_shots(self):
        sb = copy.deepcopy(BASE)
        sb["shots"] = sb["shots"][:7]
        with self.assertRaisesRegex(StoryboardError, "schema"):
            self.check(sb)

    def test_rejects_unknown_field(self):
        sb = copy.deepcopy(BASE)
        sb["shots"][0]["colour"] = "blue"
        with self.assertRaisesRegex(StoryboardError, "colour"):
            self.check(sb)

    def test_rejects_runtime_out_of_range(self):
        sb = copy.deepcopy(BASE)
        for s in sb["shots"]:
            s["duration_sec"] = 10
        with self.assertRaisesRegex(StoryboardError, "total runtime"):
            self.check(sb)

    def test_rejects_word_count_out_of_range(self):
        sb = copy.deepcopy(BASE)
        for s in sb["shots"][2:]:
            s["narration"] = ""
        with self.assertRaisesRegex(StoryboardError, "words"):
            self.check(sb)

    def test_rejects_undefined_and_noncontiguous_cues(self):
        sb = copy.deepcopy(BASE)
        sb["shots"][0]["music_cue"] = "cue_nope"
        with self.assertRaisesRegex(StoryboardError, "cue_nope"):
            self.check(sb)
        sb = copy.deepcopy(BASE)
        sb["shots"][9]["music_cue"] = "cue_memory"
        with self.assertRaisesRegex(StoryboardError, "contiguous"):
            self.check(sb)

    def test_rejects_missing_reference_image(self):
        sb = copy.deepcopy(BASE)
        sb["shots"][0]["reference"]["image"] = "refs/does_not_exist.png"
        with self.assertRaisesRegex(StoryboardError, "reference image not found"):
            self.check(sb)


class SelectiveRegenerationTest(unittest.TestCase):
    """End-to-end: full run, then edit one narration line and one image prompt;
    only the affected artifacts (and the final mux) may be regenerated."""

    def run_pipeline(self, run_id: str):
        env = {**os.environ, "HERITAGE_STORYBOARD": str(self.sb_path), "HERITAGE_OUTPUTS": str(self.out),
               "HERITAGE_RUNS_LOG": str(self.log), "HERITAGE_RUN_ID": run_id,
               "HERITAGE_OFFLINE": "1"}  # stub providers: free, deterministic, no network
        proc = subprocess.run([sys.executable, "-m", "pipeline.run"], cwd=ROOT, env=env,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return [r for r in map(json.loads, self.log.read_text().splitlines()) if r["run_id"] == run_id]

    def mtimes(self) -> dict[str, int]:
        return {str(p.relative_to(self.out)): p.stat().st_mtime_ns
                for p in self.out.rglob("*") if p.is_file() and not p.name.endswith(".meta.json")
                and "overlays" not in p.parts}

    def test_edit_one_shot_regenerates_only_that_shot(self):
        d = Path(tempfile.mkdtemp())
        self.out, self.log = d / "outputs", d / "runs.jsonl"
        sb = copy.deepcopy(BASE)
        sb["render"].update(keyframe_resolution=[640, 360], master_resolution=[640, 360],
                            exports=[{"aspect": "16:9", "resolution": [640, 360]},
                                     {"aspect": "9:16", "resolution": [360, 640]}])
        self.sb_path = write(sb, d)

        first = self.run_pipeline("run1")
        self.assertTrue(first and not any(r["cache_hit"] for r in first))
        self.assertTrue((self.out / "final" / "heritage_16x9.mp4").is_file())
        self.assertTrue((self.out / "final" / "heritage_9x16.mp4").is_file())

        # No-op re-run: everything cached, nothing rewritten.
        before = self.mtimes()
        second = self.run_pipeline("run2")
        self.assertTrue(all(r["cache_hit"] for r in second))
        self.assertEqual(before, self.mtimes())

        # Edit s03's narration and s05's image prompt.
        sb["shots"][2]["narration"] = "Every pattern was a word. A zigzag for the river they crossed. A star for each child."
        sb["shots"][4]["image_prompt"] += ", snow visible through the window"
        write(sb, d)
        third = self.run_pipeline("run3")
        regenerated = {(r["stage"], r["shot_id"]) for r in third if not r["cache_hit"]}
        self.assertEqual(regenerated, {("narration", "s03"), ("keyframes", "s05"), ("shots", "s05")})

        after = self.mtimes()
        changed = {k for k in after if after[k] != before.get(k)}
        expected = {"keyframes/s05.png", "shots/s05.mp4", "narration/s03.wav",
                    "assemble/clips/16x9/s05.mp4", "assemble/clips/9x16/s05.mp4", "assemble/mix.wav",
                    "final/heritage_16x9.mp4", "final/heritage_9x16.mp4",
                    "final/heritage.srt", "final/report.json", "final/storyboard.snapshot.json",
                    "script/script.md", "script/narration.txt", "script/timeline.json"}
        self.assertEqual(changed - expected, set(), f"unexpectedly rebuilt: {changed - expected}")
        self.assertIn("assemble/clips/16x9/s05.mp4", changed)

        report = json.loads((self.out / "final" / "report.json").read_text())
        for name, r in report["exports"].items():
            self.assertAlmostEqual(r["measured_lufs"], -14, delta=1.0, msg=name)
            self.assertLessEqual(r["measured_true_peak_db"], -0.5, msg=name)


if __name__ == "__main__":
    unittest.main()
