#!/usr/bin/env python3
"""Generate a self-contained HTML "ecosystem guide" showcase for a tool repo.

Why this exists
---------------
The outlook-mcp-server exemplar proved a premium, self-contained single-page
visual guide is the right "front door" for these repos. Hand-authoring one per
repo is slow and error-prone (a stray hand-typed SVG stroke like ``#2f4straee``
shipped a defect in the first pass). This generator renders the SAME proven
layout and CSS from a small, grounded per-repo spec (a Python dict / JSON),
computing all SVG geometry programmatically so there are zero hand-typed
coordinates to corrupt.

It is intentionally dependency-free (stdlib only) and writes a single file with
no external assets, so the output works offline and is trivially auditable.

Usage
-----
    python3 generate_showcase.py --spec spec.json --out docs/<name>-ecosystem-guide.html
    python3 generate_showcase.py --spec spec.json --check   # fail if out is stale

Spec schema (all strings unless noted); see SHOWCASE_SPEC.example.json:
    title, slug, version, tagline_plain, tagline_grad, lead, sub
    pills:   [{kind: live|local|priv|blue, label}]            (<=4 used)
    metrics: [{n, l}]                                         (exactly 6)
    hub:     {label, sub}                                     (center node)
    spokes:  [{label, sub, tone}]  tone: blue|live|local|priv|violet  (3..6)
    boundary: {inside_title, inside:[{title, sub, tone}], blocked:[{title, sub}]}
    audiences: [{tag, title, body, href, go}]                 (exactly 3)
    docmap:  [{doc, href, owns, altitude}]                    (rows)
    footer_provenance: str
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path


def _fit_font(text: str, box_w: float, base_px: float, pad: float = 16.0) -> float:
    """Shrink a font size so `text` fits within box_w (minus padding).

    Centered SVG titles have no wrapping, so a long label silently clips at the
    box edge (caught by eyes-on QA: a 23-char title overran a 170px box). This
    estimates rendered width at ~0.58em/char for the bold UI font and scales the
    font down (never up), floored so it stays legible. Deterministic; no I/O.
    """
    if not text:
        return base_px
    avail = max(box_w - pad, 1.0)
    est_w = len(text) * 0.58 * base_px
    if est_w <= avail:
        return base_px
    return max(base_px * avail / est_w, base_px * 0.72)

# ---- palette (mirrors the exemplar :root) ---------------------------------
TONES = {
    "blue": ("#5aa6ff", "#3b82f6", "#1f5fc0", "#04122a"),
    "live": ("#ffc46b", "#ffb454", "#e08a2a", "#3a2200"),
    "local": ("#6ff0ad", "#5be19c", "#22b074", "#053522"),
    "priv": ("#ff8fb0", "#ff6f9c", "#d34d77", "#3a0c1c"),
    "violet": ("#c9b3ff", "#b79bff", "#8a6df0", "#1c1140"),
    "cyan": ("#7fe0ff", "#52d4ff", "#2baede", "#042430"),
}


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _svg_defs() -> str:
    grads = []
    for name, (a, b, c, _ink) in TONES.items():
        grads.append(
            f'<linearGradient id="g_{name}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{c}"/></linearGradient>'
        )
    return (
        "<defs>" + "".join(grads) +
        '<filter id="sh" x="-40%" y="-40%" width="180%" height="180%">'
        '<feDropShadow dx="0" dy="7" stdDeviation="12" flood-color="#000" flood-opacity="0.42"/></filter>'
        '<marker id="ah" markerWidth="11" markerHeight="11" refX="8" refY="4" orient="auto">'
        '<path d="M0,0 L9,4 L0,8 Z" fill="#7fa6d6"/></marker>'
        "</defs>"
    )


def hub_svg(hub: dict, spokes: list) -> str:
    """Hub-and-spokes: center node + N value spokes. All geometry computed."""
    W, H = 1000, 430
    cx, cy = 250, H / 2
    hub_w, hub_h = 188, 96
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(hub["label"])}: what it is in one picture">', _svg_defs()]
    # spoke nodes on the right, evenly distributed
    n = len(spokes)
    sx = 690
    sw, sh = 270, 64
    gap = 16
    total_h = n * sh + (n - 1) * gap
    top = cy - total_h / 2
    hub_right = cx + hub_w / 2
    for i, sp in enumerate(spokes):
        y = top + i * (sh + gap)
        tone = sp.get("tone", "blue")
        a, b, c, ink = TONES.get(tone, TONES["blue"])
        midy = y + sh / 2
        # connector from hub to spoke
        parts.append(
            f'<path d="M{hub_right},{cy} C{(hub_right+sx)/2},{cy} {(hub_right+sx)/2},{midy:.0f} {sx-6},{midy:.0f}" '
            f'fill="none" stroke="{b}" stroke-width="2.4" opacity="0.55" marker-end="url(#ah)"/>'
        )
        parts.append(f'<g filter="url(#sh)"><rect x="{sx}" y="{y:.0f}" width="{sw}" height="{sh}" rx="13" fill="#11203a" stroke="{b}" stroke-opacity="0.55"/></g>')
        parts.append(f'<text x="{sx+18}" y="{y+27:.0f}" font-size="14.5" font-weight="700" fill="{a}">{esc(sp["label"])}</text>')
        parts.append(f'<text x="{sx+18}" y="{y+47:.0f}" font-size="11.5" fill="#9fb1cc">{esc(sp.get("sub",""))}</text>')
    # hub on top so it overlaps connectors cleanly
    parts.append(f'<g filter="url(#sh)"><rect x="{cx-hub_w/2:.0f}" y="{cy-hub_h/2:.0f}" width="{hub_w}" height="{hub_h}" rx="18" fill="url(#g_blue)"/></g>')
    parts.append(f'<text x="{cx}" y="{cy-6:.0f}" text-anchor="middle" font-size="19" font-weight="800" fill="#fff">{esc(hub["label"])}</text>')
    parts.append(f'<text x="{cx}" y="{cy+16:.0f}" text-anchor="middle" font-size="12" fill="#dbe8ff">{esc(hub.get("sub",""))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def boundary_svg(b: dict) -> str:
    """Privacy/safety boundary: inside-the-Mac nodes + blocked destinations."""
    W, H = 1000, 300
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Safety boundary">', _svg_defs(),
             '<rect x="34" y="40" width="620" height="220" rx="22" fill="#0e1b33" stroke="#33507a" stroke-width="2"/>',
             f'<text x="60" y="72" font-size="14" font-weight="700" fill="#9fd9bd">{esc(b.get("inside_title","🔒 STAYS ON YOUR MAC"))}</text>']
    inside = b.get("inside", [])[:3]
    x0, w, h, y = 64, 170, 120, 96
    for i, node in enumerate(inside):
        x = x0 + i * (w + 16)
        tone = node.get("tone", "local")
        a, _b, c, ink = TONES.get(tone, TONES["local"])
        # Keep all inside nodes on the dark card surface. The old first-node
        # gradient used dark ink/subtitle colors that passed geometry checks but
        # rendered low-contrast in rsvg/browser QA on some palettes.
        fill = "#12243f"
        txt = a
        sub = "#9fb1cc"
        parts.append(f'<g filter="url(#sh)"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{_b}" stroke-opacity="0.5"/></g>')
        parts.append(f'<text x="{x+w/2:.0f}" y="{y+46}" text-anchor="middle" font-size="{_fit_font(node["title"], w, 15):.1f}" font-weight="800" fill="{txt}">{esc(node["title"])}</text>')
        for j, line in enumerate(node.get("sub", "").split("\n")[:2]):
            parts.append(f'<text x="{x+w/2:.0f}" y="{y+68+j*18}" text-anchor="middle" font-size="11.5" fill="{sub}">{esc(line)}</text>')
    blocked = b.get("blocked", [])[:2]
    for i, node in enumerate(blocked):
        by = 70 + i * 90
        parts.append(f'<g filter="url(#sh)"><rect x="740" y="{by}" width="210" height="76" rx="14" fill="#1a1020" stroke="#ff6f9c" stroke-opacity="0.45"/></g>')
        parts.append(f'<text x="845" y="{by+34}" text-anchor="middle" font-size="{_fit_font(node["title"], 210, 14):.1f}" font-weight="700" fill="#ffb3c9">{esc(node["title"])}</text>')
        parts.append(f'<text x="845" y="{by+55}" text-anchor="middle" font-size="{_fit_font(node.get("sub",""), 210, 12):.1f}" fill="#ff8fac">{esc(node.get("sub",""))}</text>')
        parts.append(f'<path d="M656,{by+38} L736,{by+38}" fill="none" stroke="#ff6f9c" stroke-width="2.2" stroke-dasharray="2 6"/>')
        parts.append(f'<path d="M726,{by+33} L736,{by+38} L726,{by+43}" fill="none" stroke="#ff6f9c" stroke-width="2.2"/>')
    parts.append("</svg>")
    return "".join(parts)


CSS = """:root{--bg:#060d18;--bg2:#0a1426;--panel:#0e1a30;--card:#111f38;--line:#21324f;--line2:#2c4060;--text:#eaf2ff;--muted:#9fb1cc;--dim:#8da0bd;--blue:#5aa6ff;--blue2:#3b82f6;--cyan:#52d4ff;--green:#5be19c;--amber:#ffb454;--rose:#ff6f9c;--violet:#b79bff;--ink:#04122a}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;color:var(--text);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,ui-sans-serif,system-ui,sans-serif;background:radial-gradient(1100px 520px at 78% -8%,rgba(59,130,246,.22),transparent 60%),radial-gradient(820px 480px at 6% 4%,rgba(82,212,255,.12),transparent 55%),radial-gradient(700px 700px at 92% 96%,rgba(91,225,156,.08),transparent 55%),var(--bg);-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:30px 22px 70px}
a{color:var(--cyan);text-decoration:none}a:hover{text-decoration:underline}
code{font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:#08152b;border:1px solid var(--line);border-radius:6px;padding:.1em .42em;color:#d6e6ff}
h1,h2,h3{letter-spacing:-.02em;margin:0}
.eyebrow{display:inline-flex;align-items:center;gap:9px;color:var(--cyan);font-weight:700;letter-spacing:.16em;text-transform:uppercase;font-size:.72rem}
.dot{width:9px;height:9px;border-radius:50%;background:var(--cyan);box-shadow:0 0 16px 2px rgba(82,212,255,.85);animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.7)}}
.hero{position:relative;border:1px solid var(--line2);border-radius:26px;padding:38px 36px 30px;margin-bottom:18px;background:linear-gradient(165deg,rgba(31,52,92,.55),rgba(10,20,38,.7));box-shadow:0 30px 90px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.05);overflow:hidden}
.hero h1{font-size:clamp(2.3rem,5.2vw,3.9rem);line-height:1.02;margin:14px 0 12px}
.hero h1 .g{background:linear-gradient(92deg,var(--cyan),var(--blue) 55%,var(--violet));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p.lead{color:#cfe0f7;font-size:1.12rem;max-width:62ch;margin:0 0 8px}
.hero .sub{color:var(--muted);max-width:64ch}
.pillbar{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:.82rem;color:#dce8fb;background:rgba(11,22,42,.7);border:1px solid var(--line2);border-radius:999px;padding:7px 13px}
.pill b{color:#fff}.pill .k{width:7px;height:7px;border-radius:50%}
.k.live{background:var(--amber)}.k.local{background:var(--green)}.k.priv{background:var(--rose)}.k.blue{background:var(--blue)}
.metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:18px 0 6px}
.metric{background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.015));border:1px solid var(--line);border-radius:16px;padding:15px 14px;text-align:center}
.metric .n{font-size:1.85rem;font-weight:800;letter-spacing:-.03em;background:linear-gradient(180deg,#fff,#bcd2f2);-webkit-background-clip:text;background-clip:text;color:transparent}
.metric .l{display:block;color:var(--dim);font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;margin-top:3px}
@media(max-width:880px){.metrics{grid-template-columns:repeat(3,1fr)}}
@media(max-width:520px){.metrics{grid-template-columns:repeat(2,1fr)}}
.toc{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 26px}
.toc a{font-size:.84rem;color:#cfe0f7;border:1px solid var(--line2);background:rgba(10,20,38,.6);border-radius:999px;padding:8px 14px}
.toc a:hover{border-color:var(--cyan);text-decoration:none;color:#fff}
section.block{margin:30px 0}
.block>h2{font-size:1.5rem;margin-bottom:6px;display:flex;align-items:center;gap:11px}
.block>h2 .num{font-size:.8rem;color:var(--ink);background:linear-gradient(180deg,var(--cyan),var(--blue));width:26px;height:26px;border-radius:8px;display:inline-grid;place-items:center;font-weight:800}
.block>p.intro{color:var(--muted);max-width:74ch;margin:6px 0 16px}
.card{background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.012));border:1px solid var(--line);border-radius:20px;padding:22px;box-shadow:0 18px 50px rgba(0,0,0,.3)}
.figure{border:1px solid var(--line);border-radius:20px;background:radial-gradient(700px 300px at 50% 0,rgba(35,60,105,.4),rgba(8,17,33,.6));padding:24px;overflow:hidden}
.figure svg{display:block;width:100%;height:auto}
.cap{color:var(--dim);font-size:.82rem;text-align:center;margin-top:12px}
.lanes{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:820px){.lanes{grid-template-columns:1fr}}
.lane{position:relative;border:1px solid var(--line2);border-radius:18px;padding:20px;background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,.01));transition:transform .15s ease,border-color .15s ease}
.lane:hover{transform:translateY(-3px);border-color:var(--cyan)}
.lane .tag{font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;font-weight:700}
.lane.exec .tag{color:var(--violet)}.lane.user .tag{color:var(--green)}.lane.maint .tag{color:var(--amber)}
.lane h3{font-size:1.16rem;margin:8px 0 6px}.lane p{color:var(--muted);font-size:.9rem;margin:0 0 14px}
.lane .go{font-size:.86rem;font-weight:600}
.lane .ic{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;margin-bottom:6px;border:1px solid var(--line2);font-size:1.2rem}
.lane.exec .ic{background:rgba(183,155,255,.13)}.lane.user .ic{background:rgba(91,225,156,.13)}.lane.maint .ic{background:rgba(255,180,84,.13)}
table{width:100%;border-collapse:collapse;margin-top:6px;font-size:.9rem}
th,td{text-align:left;padding:11px 13px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;font-weight:700}
tr:last-child td{border-bottom:0}td b{color:#fff}
.note{display:flex;gap:12px;align-items:flex-start;border:1px solid var(--line2);border-left:3px solid var(--cyan);border-radius:12px;padding:14px 16px;background:rgba(10,20,38,.5);color:#cfe0f7;font-size:.9rem;margin-top:14px}
.note .i{font-size:1.1rem;line-height:1.2}
footer{margin-top:40px;padding-top:20px;border-top:1px solid var(--line);color:var(--dim);font-size:.82rem}
.prov{margin-top:8px;color:#8aa0bd}.prov code{font-size:11.5px}
.featgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:6px}
.feat{background:linear-gradient(180deg,rgba(20,32,54,.7),rgba(12,21,38,.6));border:1px solid var(--line);border-radius:16px;padding:18px}
.feat .fic{font-size:1.4rem;margin-bottom:8px}
.feat h3{font-size:1.02rem;margin:0 0 6px;color:#eaf2ff}
.feat p{margin:0;color:#b8c8e4;font-size:.9rem;line-height:1.55}
ol.flow{list-style:none;margin:0;padding:0}
ol.flow li{display:flex;gap:14px;align-items:flex-start;padding:11px 0;border-bottom:1px solid var(--line)}
ol.flow li:last-child{border-bottom:0}
ol.flow .fstep{flex:0 0 auto;width:30px;height:30px;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:.92rem;color:#06101f;background:linear-gradient(135deg,var(--cyan),var(--blue))}
ol.flow .fwrap{display:flex;flex-direction:column;gap:2px}
ol.flow .fwrap b{color:#eaf2ff;font-size:.98rem}
ol.flow .fwrap span{color:#aebfdc;font-size:.88rem;line-height:1.5}
table.cmdtable{width:100%;border-collapse:collapse;font-size:.86rem}
table.cmdtable th,table.cmdtable td{text-align:left;padding:9px 12px;border:1px solid var(--line);vertical-align:top}
table.cmdtable th{background:rgba(35,60,105,.4);color:#dbe8ff;font-weight:700}
table.cmdtable tr:nth-child(even) td{background:rgba(255,255,255,.018)}
table.cmdtable code{font:11.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:#08152b;border:1px solid var(--line);border-radius:5px;padding:.08em .38em;color:#d6e6ff;white-space:nowrap}
@media(max-width:760px){.featgrid{grid-template-columns:1fr}}"""


def _features_html(spec: dict) -> str:
    """'What it does' — grounded feature cards (3-9)."""
    feats = spec.get("features", [])
    if not feats:
        return ""
    cards = "".join(
        f'<div class="feat"><div class="fic">{esc(f.get("icon","◆"))}</div>'
        f'<h3>{esc(f["title"])}</h3><p>{esc(f["body"])}</p></div>'
        for f in feats[:9]
    )
    return f"""
  <section class="block" id="features">
    <h2><span class="num">{spec["_n_features"]}</span> What it does</h2>
    <p class="intro">{esc(spec.get("features_intro",""))}</p>
    <div class="featgrid">{cards}</div>
  </section>"""


def _flow_html(spec: dict) -> str:
    """'How it works' — a numbered program-logic flow (3-7 steps)."""
    steps = spec.get("flow", [])
    if not steps:
        return ""
    items = "".join(
        f'<li><div class="fstep">{i+1}</div><div class="fwrap"><b>{esc(s["title"])}</b>'
        f'<span>{esc(s["body"])}</span></div></li>'
        for i, s in enumerate(steps[:7])
    )
    return f"""
  <section class="block" id="how">
    <h2><span class="num">{spec["_n_flow"]}</span> How it works</h2>
    <p class="intro">{esc(spec.get("flow_intro",""))}</p>
    <div class="card"><ol class="flow">{items}</ol></div>
  </section>"""


def _commands_html(spec: dict) -> str:
    """'Commands at a glance' — grounded command-group table."""
    groups = spec.get("commands", [])
    if not groups:
        return ""
    rows = "".join(
        f'<tr><td><b>{esc(g["group"])}</b></td><td>{g.get("cmds","")}</td>'
        f'<td>{esc(g.get("touches",""))}</td></tr>'
        for g in groups
    )
    return f"""
  <section class="block" id="commands">
    <h2><span class="num">{spec["_n_commands"]}</span> Commands at a glance</h2>
    <p class="intro">{esc(spec.get("commands_intro",""))}</p>
    <div class="card"><table class="cmdtable">
      <thead><tr><th>Group</th><th>Commands</th><th>{esc(spec.get("commands_col3","Reaches"))}</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
  </section>"""


def render(spec: dict) -> str:
    # Fail loudly on unknown tones instead of silently defaulting to blue
    # (a silent default produced two same-coloured spokes before this guard).
    _bad = []
    for _sp in spec.get("spokes", []):
        if "tone" in _sp and _sp["tone"] not in TONES:
            _bad.append(("spoke", _sp.get("label", "?"), _sp["tone"]))
    for _nd in spec.get("boundary", {}).get("inside", []):
        if "tone" in _nd and _nd["tone"] not in TONES:
            _bad.append(("boundary.inside", _nd.get("title", "?"), _nd["tone"]))
    if _bad:
        _valid = ", ".join(sorted(TONES))
        _msg = "; ".join(f"{w} {esc_label!r} has unknown tone {t!r}" for w, esc_label, t in _bad)
        raise SystemExit(f"showcase spec error: {_msg}. Valid tones: {_valid}")
    # Pills: 'label' is trusted inline markup (may contain <b>); 'text' is escaped.
    def _pill(p):
        body = p["label"] if "label" in p else esc(p.get("text", ""))
        return f'<span class="pill"><span class="k {esc(p.get("kind","blue"))}"></span> {body}</span>'
    pills = "".join(_pill(p) for p in spec.get("pills", [])[:4])
    metrics = "".join(
        f'<div class="metric"><span class="n">{esc(m["n"])}</span><span class="l">{esc(m["l"])}</span></div>'
        for m in spec.get("metrics", [])[:6]
    )
    lanes = "".join(
        f'<a class="lane {esc(a.get("cls","exec"))}" href="{esc(a["href"])}">'
        f'<div class="ic">{esc(a.get("icon","📄"))}</div>'
        f'<div class="tag">{esc(a["tag"])}</div><h3>{esc(a["title"])}</h3>'
        f'<p>{esc(a["body"])}</p><div class="go">{esc(a["go"])} →</div></a>'
        for a in spec.get("audiences", [])[:3]
    )
    docrows = "".join(
        f'<tr><td><a href="{esc(d["href"])}">{esc(d["doc"])}</a></td><td>{esc(d["owns"])}</td><td>{esc(d["altitude"])}</td></tr>'
        for d in spec.get("docmap", [])
    )
    # numbered section counts for headers
    spec["_n_features"] = "1"
    spec["_n_flow"] = "2"
    spec["_n_commands"] = "4"
    toc_items = [("features", "What it does"), ("how", "How it works"),
                 ("model", "Mental model"), ("commands", "Commands"),
                 ("audiences", "Pick your path"), ("boundary", "Safety boundary"),
                 ("docs", "Documentation map")]
    toc = "".join(f'<a href="#{esc(t[0])}">{esc(t[1])}</a>' for t in toc_items)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(spec["title"])} — High-Level Doc</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="wrap">
  <section class="hero">
    <div class="eyebrow"><span class="dot"></span> {esc(spec["title"])} · {esc(spec.get("slug",""))} · {esc(spec.get("version",""))}</div>
    <h1>{esc(spec["tagline_plain"])}<br/><span class="g">{esc(spec["tagline_grad"])}</span></h1>
    <p class="lead">{esc(spec["lead"])}</p>
    <p class="sub">{esc(spec["sub"])}</p>
    <div class="pillbar">{pills}</div>
    <div class="metrics">{metrics}</div>
  </section>
  <nav class="toc">{toc}</nav>
{_features_html(spec)}
{_flow_html(spec)}

  <section class="block" id="model">
    <h2><span class="num">3</span> The mental model</h2>
    <p class="intro">{esc(spec.get("model_intro",""))}</p>
    <div class="figure">{hub_svg(spec["hub"], spec["spokes"])}
      <div class="cap">{esc(spec.get("model_cap",""))}</div>
    </div>
  </section>
{_commands_html(spec)}

  <section class="block" id="audiences">
    <h2><span class="num">5</span> Pick your path</h2>
    <p class="intro">{esc(spec.get("audiences_intro","Three doors in, by what you need right now."))}</p>
    <div class="lanes">{lanes}</div>
  </section>

  <section class="block" id="boundary">
    <h2><span class="num">6</span> {esc(spec.get("boundary_title","The safety boundary"))}</h2>
    <p class="intro">{esc(spec.get("boundary_intro",""))}</p>
    <div class="figure">{boundary_svg(spec["boundary"])}
      <div class="cap">{esc(spec.get("boundary_cap",""))}</div>
    </div>
    {('<div class="note"><span class="i">🛡️</span><div>' + spec["boundary_note"] + '</div></div>') if spec.get("boundary_note") else ""}
  </section>

  <section class="block" id="docs">
    <h2><span class="num">7</span> Documentation map</h2>
    <p class="intro">{esc(spec.get("docmap_intro", "This page is the visual front door. Every claim here is grounded in these canonical, version-controlled docs — and each link opens a styled, rendered view (no raw Markdown)."))}</p>
    <div class="card"><table>
      <thead><tr><th>Doc</th><th>What it owns</th><th>Altitude</th></tr></thead>
      <tbody>{docrows}</tbody>
    </table></div>
  </section>

  <footer>
    <div>{esc(spec["title"])} · <code>{esc(spec.get("slug",""))}</code> {esc(spec.get("version",""))} · standalone high-level doc. Detailed relationship, architecture, and C4 visuals remain canonical in the Markdown/Mermaid atlas.</div>
    <div class="prov">{esc(spec.get("footer_provenance",""))}</div>
  </footer>
</div>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text())
    out_html = render(spec)
    out_path = Path(a.out) if a.out else Path(spec.get("out", "showcase.html"))
    if a.check:
        cur = out_path.read_text() if out_path.exists() else ""
        if cur.strip() != out_html.strip():
            print(f"STALE: {out_path} differs from spec — run without --check to regenerate")
            return 1
        print(f"{out_path} ok: matches spec")
        return 0
    out_path.write_text(out_html)
    print(f"wrote {out_path} ({len(out_html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
