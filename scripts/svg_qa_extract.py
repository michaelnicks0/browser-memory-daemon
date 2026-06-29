#!/usr/bin/env python3
"""Extract centerpiece <svg> diagrams from a rendered high-level-doc and rasterize
them to PNGs for fast eyes-on QA (via vision_analyze) WITHOUT driving a browser.

Why this exists
---------------
Driving the browser for every diagram is slow, and full-page ``browser_vision``
glitches on tall rendered docs (blank/black captures, >8000px vision cap). This
probe pulls each top-level inline ``<svg>`` out of the front door, wraps it on the
page background, and shells out to ``rsvg-convert`` to produce a clean PNG.

CRITICAL fidelity caveat (codified in SKILL.md):
  * rsvg is FAITHFUL for geometry — box fills, gradients, connectors, and
    text-width/overflow. Trust its overflow/clip/translucent-fill/missing-node verdicts.
  * rsvg is a LIAR for emoji spacing — it uses a different emoji font with a wider
    glyph advance, so emoji-prefixed titles look like the emoji OVERLAPS the first
    letter. That is a rasterizer artifact, NOT a real defect. Confirm emoji spacing
    in the actual browser (it renders with normal spacing there). When you hand the
    PNG to vision_analyze, say: "IGNORE emoji-to-text spacing (known rasterizer
    artifact) and ignore intentional glassy/gradient box translucency; report only
    geometry defects (overflow, clipping, missing nodes, non-solid fills)."

Usage
-----
  python3 svg_qa_extract.py <front-door.html> [out_dir] [--width 1100] [--bg '#0a1220']

Prints one line per extracted PNG: ``<index> <title-slug> <png-path>``.
Requires ``rsvg-convert`` (librsvg) on PATH. Falls back to writing the wrapped .svg
files (still loadable by vision_analyze on most stacks) if rsvg-convert is absent.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Match each TOP-LEVEL <svg>…</svg>. Non-greedy, DOTALL. Mermaid nests marker <svg>
# defs, but those live INSIDE a top-level svg, so a non-overlapping finditer over the
# whole document still yields one match per centerpiece figure.
SVG_RE = re.compile(r"<svg\b[^>]*>.*?</svg>", re.DOTALL | re.IGNORECASE)
# A nearby heading/caption to name the crop (best-effort; falls back to the index).
TITLE_HINT_RE = re.compile(r"<(h[1-3]|figcaption)\b[^>]*>(.*?)</\1>", re.DOTALL | re.IGNORECASE)


def slugify(text: str, fallback: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "").strip()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)[:48].strip("_")
    return text or fallback


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("html", type=Path, help="rendered *-high-level-doc.html")
    ap.add_argument("out_dir", nargs="?", default="/tmp/svgqa", type=Path)
    ap.add_argument("--width", type=int, default=1100)
    ap.add_argument("--bg", default="#0a1220", help="page background behind the svg")
    args = ap.parse_args()

    html = args.html.read_text(encoding="utf-8", errors="replace")
    svgs = SVG_RE.findall(html)
    if not svgs:
        print("no <svg> found", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.html.stem
    headings = [m.group(2) for m in TITLE_HINT_RE.finditer(html)]
    have_rsvg = shutil.which("rsvg-convert") is not None

    for i, svg in enumerate(svgs):
        title = slugify(headings[i] if i < len(headings) else "", f"svg{i}")
        # Give the wrapper and extracted child an explicit viewport. Without a
        # height, librsvg can render a mostly blank square with only a stray line,
        # even though the browser lays the SVG out correctly from its viewBox.
        out_h = args.width
        viewbox = re.search(r'viewBox="([^"]+)"', svg, re.IGNORECASE)
        if viewbox:
            try:
                vb = [float(part) for part in viewbox.group(1).replace(',', ' ').split()]
                if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
                    out_h = max(1, round(args.width * vb[3] / vb[2]))
                    svg = re.sub(
                        r'<svg\b[^>]*>',
                        f'<svg xmlns="http://www.w3.org/2000/svg" width="{args.width}" height="{out_h}" viewBox="{vb[0]:g} {vb[1]:g} {vb[2]:g} {vb[3]:g}">',
                        svg,
                        count=1,
                        flags=re.IGNORECASE,
                    )
            except ValueError:
                pass
        wrapped = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{args.width}" height="{out_h}">'
            f'<rect width="100%" height="100%" fill="{args.bg}"/>{svg}</svg>'
        )
        base = args.out_dir / f"{stem}__{i}__{title}"
        svg_path = base.with_suffix(".svg")
        svg_path.write_text(wrapped, encoding="utf-8")
        if have_rsvg:
            png_path = base.with_suffix(".png")
            subprocess.run(
                ["rsvg-convert", "-w", str(args.width), str(svg_path), "-o", str(png_path)],
                check=False,
            )
            print(f"{i} {title} {png_path}")
        else:
            print(f"{i} {title} {svg_path}  (rsvg-convert absent; load the .svg)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
