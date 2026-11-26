"""Stage 2 — keyframes: one still image per shot from its image prompt."""
from __future__ import annotations

from .common.cache import run_model_cached
from .common.cli import stage_main
from .common.context import Ctx
from .common.hashing import file_hash
from .common.storyboard import model_key
from .providers import get_provider

VERSION = "keyframes/v1"  # bump to invalidate every keyframe after a code change


def compose_prompt(shot: dict, sb: dict) -> str:
    """shot prompt + fixed character descriptions + global style block."""
    chars = {c["id"]: c["description"].strip() for c in sb.get("characters", [])}
    parts = [shot["image_prompt"].strip()]
    parts += [chars[c] for c in shot.get("characters", [])]
    if sb["style"]["image_prompt_suffix"].strip():
        parts.append(sb["style"]["image_prompt_suffix"].strip())
    return ", ".join(parts)


def run(ctx: Ctx) -> None:
    sb = ctx.sb
    cfg = sb["models"]["image"]
    provider = get_provider(cfg["provider"])
    w, h = sb["render"]["keyframe_resolution"]
    out_dir = ctx.stage_dir("keyframes")

    for shot in ctx.shots:
        if not ctx.selected(shot["id"]):
            continue
        prompt = compose_prompt(shot, sb)
        ref_rel = shot["reference"].get("image")
        ref = (ctx.root / ref_rel) if ref_rel else None
        inputs = {
            "v": VERSION, "model": model_key(cfg), "prompt": prompt,
            "negative_prompt": sb["style"]["negative_prompt"], "seed": shot["seed"],
            "resolution": [w, h], "reference_image_sha256": file_hash(ref) if ref else None,
        }
        run_model_cached(
            ctx, stage="keyframes", shot_id=shot["id"], cfg=cfg, inputs=inputs,
            out=out_dir / f"{shot['id']}.png", seed=shot["seed"],
            call=lambda tmp, shot=shot, prompt=prompt, ref=ref: provider.image(
                cfg=cfg, prompt=prompt, negative_prompt=sb["style"]["negative_prompt"], seed=shot["seed"],
                width=w, height=h, reference_image=ref, out=tmp),
        )


if __name__ == "__main__":
    stage_main("keyframes", run)
