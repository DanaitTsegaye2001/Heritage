"""Pillow-rendered overlays (subtitles, AI badge, end card, placeholder frames).

Rendering text ourselves instead of relying on ffmpeg's drawtext/subtitles
filters keeps output identical across ffmpeg builds — many builds (including
Homebrew's default) ship without libfreetype/libass. See FAILURES.md F-001.
"""
from __future__ import annotations

import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)  # Pillow >= 10.1


def _wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=fnt) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def subtitle_png(text: str, out: Path, *, frame_w: int, frame_h: int) -> tuple[int, int]:
    """Render a subtitle box; returns its (x, y) position inside the frame's safe area.

    Safe areas: 16:9 keeps text above the bottom 8% (title-safe); 9:16 keeps it
    above the bottom 22% so platform UI (captions, buttons) doesn't cover it.
    """
    vertical = frame_h > frame_w
    size = int((frame_w * 0.052) if vertical else (frame_h * 0.045))
    max_w = int(frame_w * (0.84 if vertical else 0.78))
    bottom_margin = int(frame_h * (0.22 if vertical else 0.08))
    fnt = font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = _wrap(probe, text, fnt, max_w)
    line_h = int(size * 1.3)
    widths = [int(probe.textlength(l, font=fnt)) for l in lines]
    pad = int(size * 0.45)
    box_w, box_h = max(widths) + 2 * pad, line_h * len(lines) + 2 * pad - int(size * 0.3)
    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, box_w - 1, box_h - 1], radius=int(size * 0.3), fill=(0, 0, 0, 150))
    for i, (line, w) in enumerate(zip(lines, widths)):
        d.text(((box_w - w) // 2, pad + i * line_h), line, font=fnt, fill=(255, 255, 255, 255))
    img.save(out)
    return (frame_w - box_w) // 2, frame_h - bottom_margin - box_h


def badge_png(text: str, out: Path, *, frame_w: int, frame_h: int) -> tuple[int, int]:
    size = int(min(frame_w, frame_h) * 0.026)
    fnt = font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    pad = int(size * 0.5)
    w = int(probe.textlength(text, font=fnt)) + 2 * pad
    h = int(size * 1.2) + 2 * pad
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=(0, 0, 0, 120))
    d.text((pad, pad), text, font=fnt, fill=(255, 255, 255, 230))
    img.save(out)
    margin_x = int(frame_w * 0.05)
    margin_y = int(frame_h * (0.08 if frame_h > frame_w else 0.05))
    return frame_w - margin_x - w, margin_y


def end_card_png(out: Path, *, w: int, h: int, title: str, statement: str, credits: list[str]) -> None:
    img = Image.new("RGB", (w, h), (14, 12, 10))
    d = ImageDraw.Draw(img)
    unit = min(w, h)
    title_f, body_f, small_f = font(int(unit * 0.075)), font(int(unit * 0.034)), font(int(unit * 0.026))
    max_w = int(w * 0.8)
    y = int(h * (0.30 if h > w else 0.22))
    for line in _wrap(d, title, title_f, max_w):
        d.text(((w - d.textlength(line, font=title_f)) // 2, y), line, font=title_f, fill=(240, 228, 205))
        y += int(unit * 0.095)
    y += int(unit * 0.04)
    for line in _wrap(d, statement, body_f, max_w):
        d.text(((w - d.textlength(line, font=body_f)) // 2, y), line, font=body_f, fill=(230, 230, 230))
        y += int(unit * 0.05)
    y += int(unit * 0.05)
    for c in credits:
        d.text(((w - d.textlength(c, font=small_f)) // 2, y), c, font=small_f, fill=(170, 170, 170))
        y += int(unit * 0.04)
    img.save(out)


def placeholder_keyframe(out: Path, *, w: int, h: int, prompt: str, seed: int) -> None:
    """Deterministic stand-in image: seeded gradient + shapes + the prompt text."""
    rng = random.Random(seed)
    c1 = tuple(rng.randint(30, 140) for _ in range(3))
    c2 = tuple(rng.randint(120, 230) for _ in range(3))
    grad = Image.linear_gradient("L").resize((w, h)).rotate(rng.choice([0, 90, 180, 270]), expand=False).resize((w, h))
    img = Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), grad)
    d = ImageDraw.Draw(img, "RGBA")
    for _ in range(14):  # shapes give Ken Burns moves something visible to travel across
        r = rng.randint(h // 20, h // 5)
        x, y = rng.randint(0, w), rng.randint(0, h)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*[rng.randint(0, 255) for _ in range(3)], 70))
    f_big, f_small = font(int(h * 0.05)), font(int(h * 0.028))
    d.text((int(w * 0.05), int(h * 0.06)), "PLACEHOLDER KEYFRAME (stub provider)", font=f_big, fill=(255, 255, 255, 230))
    y = int(h * 0.16)
    for line in textwrap.wrap(prompt, 70)[:8]:
        d.text((int(w * 0.05), y), line, font=f_small, fill=(255, 255, 255, 210))
        y += int(h * 0.04)
    img.save(out, format="PNG")
