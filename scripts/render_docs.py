#!/usr/bin/env python3
"""Render a repo's Markdown docs into styled, self-contained HTML siblings.

Why this exists
---------------
The high-level HTML front door links into the repo's Markdown docs. Opening a
``.md`` file in a browser shows raw, unstyled source — a jarring drop from the
polished entry page. This renderer turns every linked ``.md`` into a matching
``.html`` page so navigation stays seamless and on-brand:

* shared CSS shell (imported from ``generate_showcase``) so docs match the front door
* fenced ```mermaid``` blocks are pre-rendered to **inline SVG** via ``mmdc`` and
  cached by content hash (no external assets, works offline)
* code blocks are syntax-highlighted (Pygments, inlined styles)
* every ``href="…​.md"`` that points at a doc we render is rewritten to ``.html``
* each page gets a slim top bar linking back to the overview front door, and a
  footer noting the canonical Markdown source

The Markdown stays the source of truth (committed, diffed, maintained); the HTML
is a generated, drift-checkable artifact — same discipline as the test inventory.

Usage
-----
    python3 render_docs.py --repo . --slug webex-cli            # render
    python3 render_docs.py --repo . --slug webex-cli --check    # fail if stale
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_showcase as gs  # shared CSS + esc()

try:
    import markdown as md_lib
except ImportError:
    sys.stderr.write(
        "ERROR: the 'markdown' package is required.\n"
        "Install into the build venv:  pip install markdown pygments\n"
    )
    raise

MMDC = os.path.expanduser("~/.local/bin/mmdc")
MMD_CACHE = Path(os.path.expanduser("~/.cache/hl-doc-mmd"))
# Custom Mermaid theme mapping diagram colors to the high-level-doc palette
# (navy panels, blue edges, cyan/blue accents) so diagrams mesh with the page
# instead of shipping mmdc's stock dark palette (charcoal nodes, grey lines,
# washed-out near-white clusters, brick-red accents).
MMD_THEME = Path(__file__).resolve().parent / "mermaid-theme.json"

# Prose styles layered on top of the shared showcase CSS.
MD_CSS = """
.docbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:14px;padding:12px 20px;margin:-30px -22px 24px;background:rgba(8,15,28,.86);backdrop-filter:blur(10px);border-bottom:1px solid var(--line2)}
.docbar a.home{display:inline-flex;align-items:center;gap:8px;font-weight:700;color:var(--cyan);font-size:.9rem}
.docbar .crumb{color:var(--dim);font-size:.84rem}
.docbar .crumb b{color:var(--text)}
.md-body{max-width:none}
.md-body h1{font-size:2.1rem;margin:6px 0 14px;letter-spacing:-.02em}
.md-body h2{font-size:1.5rem;margin:30px 0 10px;padding-bottom:7px;border-bottom:1px solid var(--line);letter-spacing:-.02em}
.md-body h3{font-size:1.2rem;margin:22px 0 8px}
.md-body h4{font-size:1.02rem;margin:18px 0 6px;color:#cfe0f7}
.md-body p{color:#cdd9ee;margin:10px 0}
.md-body ul,.md-body ol{color:#cdd9ee;padding-left:24px}
.md-body li{margin:5px 0}
.md-body a{color:var(--cyan)}
.md-body strong{color:#fff}
.md-body blockquote{margin:14px 0;padding:10px 16px;border-left:3px solid var(--blue);background:rgba(10,20,38,.55);border-radius:0 10px 10px 0;color:#bcd0ec}
.md-body code{font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:#08152b;border:1px solid var(--line);border-radius:6px;padding:.1em .42em;color:#d6e6ff}
.md-body pre{background:#070f1f;border:1px solid var(--line);border-radius:12px;padding:16px 18px;overflow:auto;margin:14px 0}
.md-body pre code{background:none;border:0;padding:0;color:#d6e6ff;font-size:12.5px;line-height:1.6}
.md-body table{width:100%;border-collapse:collapse;margin:16px 0;font-size:.88rem}
.md-body th,.md-body td{text-align:left;padding:9px 12px;border:1px solid var(--line)}
.md-body th{background:rgba(35,60,105,.4);color:#dbe8ff;font-weight:700}
.md-body tr:nth-child(even) td{background:rgba(255,255,255,.018)}
.md-body hr{border:0;border-top:1px solid var(--line);margin:26px 0}
.md-body .mmd{margin:18px 0;padding:16px;border:1px solid var(--line);border-radius:16px;background:radial-gradient(700px 280px at 50% 0,rgba(35,60,105,.32),rgba(8,17,33,.55))}
.md-body .mmd-scroll{overflow-x:auto;overflow-y:hidden;text-align:center}
.md-body .mmd:not(.wide) .mmd-scroll{text-align:center}
.md-body .mmd.wide .mmd-scroll{text-align:left}
.md-body .mmd svg{height:auto;display:inline-block}
.md-body .mmd-hint{font:600 11px/1.4 ui-sans-serif,system-ui;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:0 0 10px;opacity:.8}
.md-body .mmd-scroll::-webkit-scrollbar{height:9px}
.md-body .mmd-scroll::-webkit-scrollbar-thumb{background:var(--line2);border-radius:6px}
.md-body .mmd-scroll::-webkit-scrollbar-track{background:transparent}
.md-body .codehilite{background:#070f1f;border:1px solid var(--line);border-radius:12px;margin:14px 0}
.md-body .codehilite pre{border:0;margin:0;background:none}
.md-footer{margin-top:42px;padding-top:18px;border-top:1px solid var(--line);color:var(--dim);font-size:.82rem}
.md-footer code{font-size:11.5px}
"""

_MERMAID_RE = re.compile(r"^```mermaid[ \t]*\n(.*?)\n```[ \t]*$", re.DOTALL | re.MULTILINE)


# ── Dark-theme remap for inline classDef colors ──────────────────────────────
# gpt-5.5-authored diagrams hardcode LIGHT-theme classDef fills (e.g. fill:#dbeafe
# pale blue, #d6f5e6 pale mint, #fdd9e1 pale pink) with dark text meant for light
# backgrounds. Inline classDefs OVERRIDE Mermaid themeVariables, so our dark theme
# never reaches them — they render as washed-out pastel stickers on the navy page.
# This remaps each LIGHT fill to a dark-theme equivalent, preserving the semantic
# hue family (blue/green/red/amber/purple/grey). Saturated, already-dark colors
# (the official C4 palette, #1168bd etc.) are left ALONE.
_DARK_FAMILY = {
    "blue":   ("#1d3358", "#6cb4ff", "#eaf2ff"),
    "green":  ("#103528", "#3fcf8e", "#d7ffe9"),
    "red":    ("#3a1622", "#ff6f9c", "#ffd9e2"),
    "amber":  ("#3a2a12", "#ffb454", "#ffe9cf"),
    "purple": ("#241f44", "#9b8cff", "#e7e3ff"),
    "grey":   ("#222e40", "#8aa0bd", "#dbe6f5"),
}


def _hex_rgb(c: str):
    h = c.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _color_family(c: str):
    """Return a dark-theme family for a LIGHT fill, or None to leave it alone."""
    try:
        r, g, b = _hex_rgb(c)
    except (ValueError, IndexError):
        return None
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if lum < 0.62:          # already dark / saturated (C4) → leave alone
        return None
    mx, mn = max(r, g, b), min(r, g, b)
    spread = mx - mn
    # Pale gpt-5.5 tints carry hue intent at low saturation (e.g. #e6f1fb≈blue,
    # #e1f5ee≈green, #fcebeb≈red). Use absolute channel SPREAD, not the saturation
    # ratio: a spread below ~12 is a genuinely neutral grey; at/above it the hue is
    # intentional and must be preserved so the diagram's color legend survives.
    if spread < 12:
        return "grey"
    d = mx - mn
    if mx == r:
        hue = ((g - b) / d) % 6
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    hue *= 60
    if hue >= 330 or hue < 20:
        return "red"
    if hue < 50:
        return "amber"
    if hue < 160:
        return "green"
    if hue < 250:
        return "blue"
    if hue < 330:
        return "purple"
    return "grey"


def _retheme_classdefs(code: str) -> str:
    """Rewrite light-theme classDef fill/stroke/color to dark-theme equivalents."""
    def repl(m):
        head, body = m.group(1), m.group(2)
        fill_m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6})", body)
        if not fill_m:
            return m.group(0)
        fam = _color_family(fill_m.group(1))
        if not fam:
            return m.group(0)  # saturated/dark (C4) — untouched
        fill, stroke, text = _DARK_FAMILY[fam]
        body = re.sub(r"fill:\s*#[0-9a-fA-F]{3,6}", f"fill:{fill}", body)
        body = re.sub(r"stroke:\s*#[0-9a-fA-F]{3,6}", f"stroke:{stroke}", body)
        if re.search(r"color:\s*#[0-9a-fA-F]{3,6}", body):
            body = re.sub(r"color:\s*#[0-9a-fA-F]{3,6}", f"color:{text}", body)
        else:
            body = body.rstrip(";") + f",color:{text}"
        return head + body
    # classDef <names> <style-decls>   (style decls run to end-of-line or ';')
    return re.sub(r"(classDef\s+[\w, ]+?\s+)([^\n;]+;?)", repl, code)


def _retheme_style_directives(code: str) -> str:
    """Rewrite light-theme Mermaid `style <node> ...` directives to dark theme.

    Structurizr Mermaid exports use per-node `style 1 fill:#dbeafe,...` directives
    rather than classDef blocks. Those inline styles emit SVG `!important` rules, so
    the global Mermaid theme cannot override them. Retheme them at source in the
    HTML renderer while leaving the committed `.mmd`/`.md` artifacts untouched.
    """
    def repl(m):
        head, body = m.group(1), m.group(2)
        fill_m = re.search(r"fill:\s*(#[0-9a-fA-F]{3,6})", body)
        if not fill_m:
            return m.group(0)
        fam = _color_family(fill_m.group(1))
        if not fam:
            return m.group(0)
        fill, stroke, text = _DARK_FAMILY[fam]
        body = re.sub(r"fill:\s*#[0-9a-fA-F]{3,6}", f"fill:{fill}", body)
        body = re.sub(r"stroke:\s*#[0-9a-fA-F]{3,6}", f"stroke:{stroke}", body)
        if re.search(r"color:\s*#[0-9a-fA-F]{3,6}", body):
            body = re.sub(r"color:\s*#[0-9a-fA-F]{3,6}", f"color:{text}", body)
        else:
            body = body.rstrip(";") + f",color:{text}"
        return head + body

    return re.sub(r"(?m)^(\s*style\s+\S+\s+)([^\n]+)$", repl, code)


def render_mermaid(code: str, retheme: bool = True) -> str:
    """Render a Mermaid block to inline SVG (cached by content + theme hash)."""
    if retheme:
        code = _retheme_style_directives(_retheme_classdefs(code))
    theme_sig = MMD_THEME.read_text() if MMD_THEME.exists() else "dark"
    h = hashlib.sha1((code + "\x00" + theme_sig).encode("utf-8")).hexdigest()[:16]
    svg_path = MMD_CACHE / f"{h}.svg"
    if not svg_path.exists():
        MMD_CACHE.mkdir(parents=True, exist_ok=True)
        mmd_path = MMD_CACHE / f"{h}.mmd"
        mmd_path.write_text(code)
        cmd = [MMDC, "-i", str(mmd_path), "-o", str(svg_path), "-b", "transparent", "-q"]
        if MMD_THEME.exists():
            cmd += ["-c", str(MMD_THEME)]
        else:
            cmd += ["-t", "dark"]
        env = os.environ.copy()
        if "PUPPETEER_EXECUTABLE_PATH" not in env:
            candidates = sorted(
                Path.home().glob(".cache/puppeteer/chrome-headless-shell/**/chrome-headless-shell"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                env["PUPPETEER_EXECUTABLE_PATH"] = str(candidates[0])
        subprocess.run(cmd, capture_output=True, text=True, env=env)
    if not svg_path.exists():
        return f'<pre class="mmd-fallback">{html.escape(code)}</pre>'
    svg = svg_path.read_text()
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg, flags=re.IGNORECASE)
    svg = svg.strip()
    # Structurizr Mermaid exports include `linkStyle default fill:#ffffff`; after
    # theming, Mermaid carries that into edge-path inline `fill:#ffffff` styles.
    # Edges should be stroked by the showcase theme, not white-filled.
    svg = svg.replace('style="fill:#ffffff;;;fill:#ffffff"', 'style="fill:none"')

    # Mermaid hardcodes a TRANSLUCENT label background in its own emitted <style>
    # (e.g. .edgeLabel rect{opacity:0.5}, .edgeLabel .label rect{fill:#16264a;opacity:0.5},
    # .classLabel .label{...opacity:0.5}, and .labelBkg{background:rgba(..,0.5)}).
    # On a dark page, overlapping 50%-opacity rects show the navy through as a faint
    # "checkerboard" of tiles behind connector/class labels. themeCSS can't reliably beat
    # Mermaid's own later-emitted rules, so neutralize it deterministically in the
    # rendered SVG: make those backgrounds fully opaque and on-theme.
    svg = svg.replace("opacity:0.5;background-color:#0a1426;fill:#0a1426;",
                      "opacity:1;background-color:#0e1a30;fill:#0e1a30;")
    # Force opaque on-theme fill for ANY label-background CSS rule that carries
    # opacity:0.5 — covers .edgeLabel / .classLabel / .nodeLabel / .label rect rules
    # regardless of whether opacity comes before or after fill (order-independent),
    # and whatever the translucent fill colour is (#0a1426, #16264a, …).
    def _opaque_label_rule(m: "re.Match") -> str:
        body = m.group(2)
        body = body.replace("opacity:0.5;", "opacity:1;")
        body = re.sub(r"fill:#[0-9a-fA-F]{3,6};", "fill:#0e1a30;", body)
        return m.group(1) + body + m.group(3)

    svg = re.sub(
        r"(\.(?:edgeLabel|classLabel|nodeLabel)[^{}]*(?:rect|\.label)?\s*\{)([^{}]*?opacity:0\.5;[^{}]*?)(\})",
        _opaque_label_rule, svg)
    # Belt-and-suspenders: any remaining label-context rect rule that still pairs a
    # hex fill with opacity:0.5 (either order).
    svg = re.sub(r"(\{[^{}]*?)fill:(#[0-9a-fA-F]{3,6});opacity:0\.5;",
                 r"\1fill:#0e1a30;opacity:1;", svg)
    svg = re.sub(r"(\{[^{}]*?)opacity:0\.5;(\s*[^{}]*?)fill:#[0-9a-fA-F]{3,6};",
                 r"\1opacity:1;\2fill:#0e1a30;", svg)
    svg = re.sub(r"\.labelBkg\{background-color:rgba\([^)]*\);\}",
                 ".labelBkg{background-color:#0e1a30;}", svg)
    # Mermaid emits an empty edge-label foreignObject for every unlabeled edge:
    # <span class="edgeLabel"></span>. On dark pages these render as tiny stray
    # label-background marks near the graph origin. Remove only genuinely empty
    # edge-label groups; real edge labels stay intact.
    svg = re.sub(
        r'<g class="edgeLabel">\s*<g class="label"[^>]*>\s*'
        r'<foreignObject[^>]*>\s*<div[^>]*class="labelBkg"[^>]*>\s*'
        r'<span class="edgeLabel">\s*</span>\s*</div>\s*</foreignObject>\s*</g>\s*</g>',
        '', svg)

    # Mermaid emits the ROOT <svg> with width="100%" + style="max-width:<native>px".
    # When dropped into a ~700px column the browser scales the ENTIRE drawing (text
    # and all) down to fit — a 2700px flowchart shrinks to ~26%, rendering 16px labels
    # at ~4px (illegible). Fix: pin the ROOT svg to its NATIVE pixel width so text
    # renders 1:1, and let the container scroll horizontally for wide diagrams.
    #
    # CAUTION: Mermaid output contains nested marker <svg> defs with viewBox="0 0 10 10".
    # We must edit ONLY the first (outermost/root) <svg> opening tag and read ITS OWN
    # viewBox — not the first viewBox in the document (that may be a marker).
    m_root = re.match(r"<svg\b[^>]*>", svg)
    native_w = native_h = 0.0
    if m_root:
        root_tag = m_root.group(0)
        m_vb = re.search(r'viewBox="(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)"', root_tag)
        if m_vb:
            native_w, native_h = float(m_vb.group(3)), float(m_vb.group(4))
        # rebuild the root tag: drop width="…", neutralize max-width clamp, pin native px
        new_tag = re.sub(r'\swidth="[^"]*"', "", root_tag, count=1)
        new_tag = re.sub(r'\sstyle="[^"]*"', ' style="background-color:transparent"',
                         new_tag, count=1)
        if native_w:
            new_tag = new_tag.replace(
                "<svg", f'<svg width="{native_w:.0f}" height="{native_h:.0f}"', 1)
        svg = new_tag + svg[m_root.end():]
    wide = native_w > 1180  # wider than a comfortable reading column
    cls = "mmd wide" if wide else "mmd"
    hint = ('<div class="mmd-hint">↔ wide diagram — scroll horizontally</div>'
            if wide else "")
    return f'<figure class="{cls}">{hint}<div class="mmd-scroll">{svg}</div></figure>'


def _extract_mermaid(text: str):
    blocks = []

    def repl(m):
        blocks.append(m.group(1))
        return f"\n\nXMERMAIDX{len(blocks) - 1}XENDX\n\n"

    return _MERMAID_RE.sub(repl, text), blocks


def _rewrite_links(html_text: str, doc_path: Path, rendered: set) -> str:
    """Rewrite href="….md[#frag]" → ".html" when the target is in `rendered`."""
    def repl(m):
        pre, href, post = m.group(1), m.group(2), m.group(3)
        frag = ""
        target = href
        if "#" in href:
            target, frag = href.split("#", 1)
            frag = "#" + frag
        if not target.endswith(".md"):
            return m.group(0)
        if target.startswith(("http://", "https://", "//")):
            return m.group(0)
        resolved = (doc_path.parent / target).resolve()
        if resolved in rendered:
            return f'{pre}{target[:-3]}.html{frag}{post}'
        return m.group(0)

    return re.sub(r'(href=")([^"]+)(")', repl, html_text)


def _relpath_to_root(doc_path: Path, repo: Path) -> str:
    rel = os.path.relpath(repo, doc_path.parent)
    return "" if rel == "." else rel + "/"


_C4_DOT_IMG_RE = re.compile(
    r'<p><img alt="[^"]+" src="[^"]*dot-rendered/structurizr-[^"]+\.svg" /></p>'
)


def _replace_c4_graphviz_with_showcase_mermaid(body_html: str, raw: str) -> str:
    """HTML-only C4 treatment: display themed Mermaid while keeping source MD intact.

    The generated C4 Markdown intentionally prefers committed Graphviz SVG artifacts for
    GitHub/Markdown readability and retains Mermaid source in a details block. For the
    polished HTML companions, the visible C4 diagrams use the same
    showcase Mermaid theme as the rest of the high-level docs. Do that at render time:
    replace the visible Graphviz image paragraphs with inline themed Mermaid figures, but
    leave the Markdown files, generated Graphviz artifacts, and collapsible source blocks
    unchanged.
    """
    mermaids = [m.group(1) for m in _MERMAID_RE.finditer(raw)]
    if not mermaids:
        return body_html
    rendered = iter(render_mermaid(code, retheme=True) for code in mermaids)

    def repl(_m):
        try:
            return next(rendered)
        except StopIteration:
            return _m.group(0)

    body_html = _C4_DOT_IMG_RE.sub(repl, body_html)
    body_html = body_html.replace(
        "Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review.",
        "HTML display: showcase-themed Mermaid render. Markdown keeps the Graphviz SVG, and Mermaid source is retained below for text review.",
    )
    return body_html


def render_doc(doc_path: Path, repo: Path, slug: str, rendered: set) -> str:
    raw = doc_path.read_text()

    # C4/Structurizr generated artifact pages get an HTML-only display swap below:
    # visible Graphviz images become themed Mermaid figures, while Mermaid source
    # fences remain code inside <details>. Other architecture docs (README, ADRs,
    # narrative docs) follow normal Markdown rendering so their intentional Mermaid
    # diagrams render as diagrams instead of code blocks.
    rel_doc = doc_path.relative_to(repo).as_posix()
    architecture_artifact_doc = (
        rel_doc == "docs/architecture/c4-diagrams.md"
        or rel_doc.startswith("docs/architecture/diagrams/markdown/")
    )
    if architecture_artifact_doc:
        body_md, mermaids = raw, []
    else:
        body_md, mermaids = _extract_mermaid(raw)

    # C4/architecture diagrams use a deliberate, cohesive C4 palette — leave their
    # inline classDef colors untouched. Only retheme the general doc diagrams whose
    # gpt-5.5 light-theme classDefs clash with the dark page.
    retheme = not architecture_artifact_doc

    converter = md_lib.Markdown(
        extensions=["extra", "sane_lists", "toc", "codehilite"],
        extension_configs={"codehilite": {"noclasses": True, "pygments_style": "monokai"}},
    )
    body_html = converter.convert(body_md)

    if architecture_artifact_doc:
        body_html = _replace_c4_graphviz_with_showcase_mermaid(body_html, raw)

    # reinsert rendered mermaid (markdown wraps the placeholder in <p>…</p>)
    for i, code in enumerate(mermaids):
        svg = render_mermaid(code, retheme=retheme)
        body_html = body_html.replace(f"<p>XMERMAIDX{i}XENDX</p>", svg)
        body_html = body_html.replace(f"XMERMAIDX{i}XENDX", svg)

    body_html = _rewrite_links(body_html, doc_path, rendered)

    to_root = _relpath_to_root(doc_path, repo)
    front = f"{to_root}{slug}-high-level-doc.html"
    rel_disp = os.path.relpath(doc_path, repo)
    title = doc_path.stem.replace("_", " ").title()

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{gs.esc(title)} — {gs.esc(slug)}</title>
<style>
{gs.CSS}
{MD_CSS}
</style>
</head>
<body>
<div class="wrap">
  <div class="docbar">
    <a class="home" href="{gs.esc(front)}">⌂ {gs.esc(slug)} overview</a>
    <span class="crumb">/ <b>{gs.esc(rel_disp)}</b></span>
  </div>
  <article class="md-body">
{body_html}
  </article>
  <div class="md-footer">
    Rendered from <code>{gs.esc(rel_disp)}</code> — the Markdown file is the canonical,
    version-controlled source. This HTML is generated (regenerate with
    <code>scripts/render_docs.py</code>); do not hand-edit.
  </div>
</div>
</body>
</html>
"""


def collect_docs(repo: Path) -> list:
    docs = []
    docs_dir = repo / "docs"
    if docs_dir.is_dir():
        docs += sorted(docs_dir.rglob("*.md"))
    for root_doc_name in ("README.md", "AGENTS.md", "SKILL.md"):
        root_doc = repo / root_doc_name
        if root_doc.exists():
            docs.append(root_doc)
    # exclude build/dep dirs AND internal work-log dirs (process receipts, not docs)
    excluded_parts = {".venv", "venv", "node_modules", ".git",
                      "plans", "review", "archive", "scratch", "drafts"}
    return [d for d in docs if not any(p in excluded_parts for p in d.parts)]


_MD_LINK_RE = re.compile(r"\]\(([^)]+?\.md)(?:#[^)]*)?\)")


def _closure_extra_docs(repo: Path, docs: list) -> list:
    """Transitive closure: pull in any .md the doc set LINKS to but that
    collect_docs excluded (work-log dirs, root AGENTS.md/SKILL.md, …). This
    guarantees no clickable link ever drops to RAW markdown, while still leaving
    UN-referenced work-logs unrendered. Bounded BFS over markdown links."""
    have = {d.resolve() for d in docs}
    extra: list = []
    frontier = list(docs)
    while frontier:
        nxt = []
        for d in frontier:
            try:
                txt = d.read_text(errors="ignore")
            except OSError:
                continue
            for m in _MD_LINK_RE.finditer(txt):
                href = m.group(1)
                if href.startswith(("http://", "https://", "//", "mailto:")):
                    continue
                target = (d.parent / href).resolve()
                # stay inside the repo, must exist, not already collected
                if (target.exists() and target.suffix == ".md"
                        and repo in target.parents and target not in have):
                    have.add(target)
                    extra.append(target)
                    nxt.append(target)  # follow links from pulled-in docs too
        frontier = nxt
    return extra


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    repo = Path(a.repo).resolve()
    docs = collect_docs(repo)
    docs += _closure_extra_docs(repo, docs)  # render anything the docs link to
    rendered_set = {d.resolve() for d in docs}

    stale = []
    wrote = 0
    for d in docs:
        out_html = render_doc(d, repo, a.slug, rendered_set)
        out_path = d.with_suffix(".html")
        if a.check:
            cur = out_path.read_text() if out_path.exists() else ""
            if cur.strip() != out_html.strip():
                stale.append(str(out_path.relative_to(repo)))
        else:
            out_path.write_text(out_html)
            wrote += 1

    if a.check:
        if stale:
            print(f"STALE ({len(stale)}): " + ", ".join(stale[:8]) + (" …" if len(stale) > 8 else ""))
            return 1
        print(f"ok: {len(docs)} rendered docs match source")
        return 0
    print(f"rendered {wrote} docs → HTML under {repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
