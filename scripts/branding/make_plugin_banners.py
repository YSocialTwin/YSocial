#!/usr/bin/env python3
"""Generate the per-plugin README banners (2400x600) of the YSocial repositories.

    python scripts/branding/make_plugin_banners.py docs/Ysocial.png OUT_DIR [PLUGIN ...]

Writes one SVG per plugin; render each at 2400x600 with Chromium/Playwright (a screenshot of the
SVG file) to get the PNG that goes to <repo>/docs/banner.png. Use a logo downscaled to ~700 px wide.
"""
import base64, math, os, random, sys

W, H = 2400, 600
FONT_MONO = "DejaVu Sans Mono, Menlo, Consolas, monospace"
FONT = "DejaVu Sans, Helvetica, Arial, sans-serif"
INK = "#18323b"


def mix(c, t, k):
    c = c.lstrip("#"); r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    tr, tg, tb = (255, 255, 255) if t == "w" else (0, 0, 0)
    return "#%02x%02x%02x" % (round(r + (tr - r) * k), round(g + (tg - g) * k), round(b + (tb - b) * k))


def hexpath(cx, cy, r, rot=30):
    pts = [(cx + r * math.cos(math.radians(rot + 60 * i)), cy + r * math.sin(math.radians(rot + 60 * i))) for i in range(6)]
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"


class S:
    def __init__(self, main, logo_b64):
        self.m = main; self.l = mix(main, "w", .78); self.d = mix(main, "k", .35); self.o = []
        self.logo = logo_b64
    def add(self, s): self.o.append(s)

    # primitives -------------------------------------------------------
    def person(self, x, y, s, fg):
        return (f'<circle cx="{x:.1f}" cy="{y - s * .16:.1f}" r="{s * .26:.1f}" fill="{fg}"/>'
                f'<path d="M{x - s * .5:.1f},{y + s * .52:.1f} C{x - s * .5:.1f},{y + s * .12:.1f} {x + s * .5:.1f},{y + s * .12:.1f} {x + s * .5:.1f},{y + s * .52:.1f}Z" fill="{fg}"/>')

    def bot(self, x, y, s, fg):
        return (f'<rect x="{x - s * .42:.1f}" y="{y - s * .3:.1f}" width="{s * .84:.1f}" height="{s * .62:.1f}" rx="{s * .16:.1f}" fill="{fg}"/>'
                f'<circle cx="{x - s * .17:.1f}" cy="{y:.1f}" r="{s * .09:.1f}" fill="#fff"/><circle cx="{x + s * .17:.1f}" cy="{y:.1f}" r="{s * .09:.1f}" fill="#fff"/>'
                f'<line x1="{x:.1f}" y1="{y - s * .3:.1f}" x2="{x:.1f}" y2="{y - s * .5:.1f}" stroke="{fg}" stroke-width="{s * .07:.1f}"/><circle cx="{x:.1f}" cy="{y - s * .54:.1f}" r="{s * .07:.1f}" fill="{fg}"/>')

    def node(self, x, y, r, main=None, bot=False, fill=None, glyph=True):
        main = main or self.m; light = fill or mix(main, "w", .78)
        self.add(f'<g filter="url(#sh)"><path d="{hexpath(x, y, r)}" fill="#fff" stroke="{main}" stroke-width="{max(3, r * .09):.1f}" stroke-linejoin="round"/></g>')
        self.add(f'<path d="{hexpath(x, y, r - r * .16)}" fill="{light}"/>')
        if glyph:
            self.add((self.bot if bot else self.person)(x, y + 2, r * .95, main))

    def card(self, x, y, w, h, accent=None, lines=(1, .7), heart=False, avatar=False, rx=20, tail=None):
        accent = accent or self.m
        self.add(f'<g filter="url(#sh)"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="#fff"/>')
        if tail:
            tx = x + 34 if tail == "l" else x + w - 34
            self.add(f'<path d="M{tx - 14},{y + h - 1} L{tx},{y + h + 22} L{tx + 16},{y + h - 1}Z" fill="#fff"/>')
        self.add('</g>')
        off = 0
        if avatar:
            self.add(f'<circle cx="{x + 34}" cy="{y + 34}" r="18" fill="{mix(accent, "w", .7)}"/>' + self.person(x + 34, y + 36, 30, accent))
            off = 44
        self.add(f'<rect x="{x + 22 + off}" y="{y + 22}" width="{w * .26}" height="11" rx="5.5" fill="{accent}"/>')
        for k, f in enumerate(lines):
            self.add(f'<rect x="{x + 22 + off}" y="{y + 46 + k * 20}" width="{(w - 44 - off) * f}" height="9" rx="4.5" fill="#cfdde1"/>')
        if heart:
            hx, hy = x + w - 40, y + 28
            self.add(f'<path d="M{hx},{hy + 11} C{hx - 16},{hy - 2} {hx - 7},{hy - 13} {hx},{hy - 4} C{hx + 7},{hy - 13} {hx + 16},{hy - 2} {hx},{hy + 11}Z" fill="#f59e5b"/>')

    def line(self, x1, y1, x2, y2, col=None, w=4, dash=None, op=.6):
        col = col or self.m
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-opacity="{op}" stroke-width="{w}" stroke-linecap="round"' + (f' stroke-dasharray="{dash}"' if dash else '') + '/>')

    def arrow(self, x1, y1, x2, y2, col=None, w=5, dash="2 12"):
        col = col or self.m
        self.line(x1, y1, x2, y2, col, w, dash, .8)
        a = math.atan2(y2 - y1, x2 - x1)
        p = [(x2, y2), (x2 - 18 * math.cos(a - .45), y2 - 18 * math.sin(a - .45)), (x2 - 18 * math.cos(a + .45), y2 - 18 * math.sin(a + .45))]
        self.add(f'<path d="M{p[0][0]:.1f},{p[0][1]:.1f} L{p[1][0]:.1f},{p[1][1]:.1f} L{p[2][0]:.1f},{p[2][1]:.1f}Z" fill="{col}" fill-opacity=".85"/>')

    def server(self, x, y, w=210, h=70, n=3, main=None):
        main = main or self.d
        for i in range(n):
            yy = y + i * (h + 16)
            self.add(f'<g filter="url(#sh)"><rect x="{x}" y="{yy}" width="{w}" height="{h}" rx="16" fill="#fff" stroke="{main}" stroke-width="5"/></g>')
            for k in range(3):
                self.add(f'<circle cx="{x + 34 + k * 26}" cy="{yy + h / 2}" r="8" fill="{[main, mix(main, "w", .5), "#f59e5b"][k]}"/>')
            self.add(f'<rect x="{x + w - 92}" y="{yy + h / 2 - 5}" width="64" height="10" rx="5" fill="#cfdde1"/>')

    def vote(self, x, y, up=True):
        pts = f"{x},{y + 20} {x + 26},{y + 20} {x + 13},{y}" if up else f"{x},{y} {x + 26},{y} {x + 13},{y + 20}"
        self.add(f'<polygon points="{pts}" fill="{self.m if up else "#b9c9ce"}"/>')

    def badge(self, x, y, r, main, icon):
        self.node(x, y, r, main, fill=mix(main, "w", .8), glyph=False)
        self.add(icon(x, y, r * .5, main))

    # themed scene --------------------------------------------------------
    def svg(self, name, role, scene):
        o = self.o; self.o = []
        self.add(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
        self.add(f'''<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fbfefe"/><stop offset="1" stop-color="{mix(self.m, "w", .88)}"/></linearGradient>
<radialGradient id="glow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<filter id="sh" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="7" stdDeviation="9" flood-color="{self.d}" flood-opacity=".2"/></filter></defs>''')
        self.add(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
        for r in range(-1, 8):
            for c in range(-1, 24):
                self.add(f'<path d="{hexpath(c * 104 + (52 if r % 2 else 0), r * 90, 60)}" fill="none" stroke="{self.m}" stroke-opacity=".12" stroke-width="2"/>')
        self.add(f'<ellipse cx="1800" cy="300" rx="640" ry="330" fill="url(#glow)"/>')
        scene(self)
        # text block
        self.add(f'<image x="120" y="62" width="330" height="63" href="data:image/png;base64,{self.logo}"/>')
        size = 118 if len(name) <= 14 else (96 if len(name) <= 18 else 80)
        self.add(f'<text x="116" y="{300 + (0 if size > 90 else 10)}" font-family="{FONT_MONO}" font-weight="700" font-size="{size}" fill="{self.m}" letter-spacing="-3">{name}</text>')
        self.add(f'<text x="122" y="378" font-family="{FONT}" font-weight="600" font-size="44" fill="{INK}">{role}</text>')
        self.add(f'<rect x="122" y="430" width="{len("A plugin for YSocial") * 17 + 60}" height="52" rx="26" fill="{self.l}"/><circle cx="152" cy="456" r="10" fill="{self.m}"/>'
                 f'<text x="174" y="466" font-family="{FONT}" font-weight="600" font-size="26" fill="{INK}">A plugin for YSocial</text>')
        self.add('</svg>')
        out = "\n".join(self.o); self.o = o
        return out


# icons -----------------------------------------------------------------
def i_shield(x, y, s, c): return f'<path d="M{x},{y - s} L{x + s * .9},{y - s * .55} L{x + s * .75},{y + s * .35} Q{x},{y + s * 1.05} {x},{y + s * 1.05} Q{x},{y + s * 1.05} {x - s * .75},{y + s * .35} L{x - s * .9},{y - s * .55}Z" fill="{c}"/><path d="M{x - s * .35},{y} L{x - s * .08},{y + s * .3} L{x + s * .4},{y - s * .25}" stroke="#fff" stroke-width="{s * .18}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
def i_mega(x, y, s, c): return f'<path d="M{x - s * .8},{y - s * .25} L{x - s * .1},{y - s * .25} L{x + s * .75},{y - s * .8} L{x + s * .75},{y + s * .8} L{x - s * .1},{y + s * .25} L{x - s * .8},{y + s * .25}Z" fill="{c}"/><rect x="{x - s * .6}" y="{y + s * .25}" width="{s * .32}" height="{s * .6}" rx="{s * .1}" fill="{c}"/>'
def i_mask(x, y, s, c): return f'<circle cx="{x}" cy="{y}" r="{s * .9}" fill="{c}"/><circle cx="{x - s * .35}" cy="{y - s * .2}" r="{s * .16}" fill="#fff"/><circle cx="{x + s * .35}" cy="{y - s * .2}" r="{s * .16}" fill="#fff"/><path d="M{x - s * .45},{y + s * .25} Q{x},{y + s * .7} {x + s * .45},{y + s * .25}" stroke="#fff" stroke-width="{s * .15}" fill="none" stroke-linecap="round"/>'
def i_bolt(x, y, s, c): return f'<path d="M{x + s * .2},{y - s} L{x - s * .6},{y + s * .15} L{x - s * .05},{y + s * .15} L{x - s * .25},{y + s} L{x + s * .6},{y - s * .2} L{x + s * .05},{y - s * .2}Z" fill="{c}"/>'
def i_bell(x, y, s, c): return f'<path d="M{x - s * .75},{y + s * .5} Q{x - s * .6},{y + s * .4} {x - s * .6},{y - s * .1} Q{x - s * .6},{y - s * .85} {x},{y - s * .85} Q{x + s * .6},{y - s * .85} {x + s * .6},{y - s * .1} Q{x + s * .6},{y + s * .4} {x + s * .75},{y + s * .5}Z" fill="{c}"/><circle cx="{x}" cy="{y + s * .78}" r="{s * .2}" fill="{c}"/>'
def i_check(x, y, s, c): return f'<path d="M{x - s * .6},{y} L{x - s * .15},{y + s * .5} L{x + s * .65},{y - s * .45}" stroke="{c}" stroke-width="{s * .3}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
def i_book(x, y, s, c): return f'<path d="M{x},{y - s * .6} Q{x - s * .5},{y - s * .85} {x - s},{y - s * .6} L{x - s},{y + s * .6} Q{x - s * .5},{y + s * .35} {x},{y + s * .6}Z" fill="{c}"/><path d="M{x},{y - s * .6} Q{x + s * .5},{y - s * .85} {x + s},{y - s * .6} L{x + s},{y + s * .6} Q{x + s * .5},{y + s * .35} {x},{y + s * .6}Z" fill="{mix(c, "w", .3)}"/>'
def i_q(x, y, s, c): return f'<text x="{x}" y="{y + s * .55}" text-anchor="middle" font-family="{FONT}" font-weight="700" font-size="{s * 1.8}" fill="{c}">?</text>'
def i_cap(x, y, s, c): return f'<path d="M{x},{y - s * .7} L{x + s},{y - s * .2} L{x},{y + s * .3} L{x - s},{y - s * .2}Z" fill="{c}"/><path d="M{x - s * .55},{y + s * .05} L{x - s * .55},{y + s * .55} Q{x},{y + s * .95} {x + s * .55},{y + s * .55} L{x + s * .55},{y + s * .05} L{x},{y + s * .3}Z" fill="{mix(c, "k", .15)}"/>'
def i_clock(x, y, s, c): return f'<circle cx="{x}" cy="{y}" r="{s * .9}" fill="none" stroke="{c}" stroke-width="{s * .22}"/><path d="M{x},{y - s * .5} L{x},{y} L{x + s * .4},{y + s * .25}" stroke="{c}" stroke-width="{s * .2}" fill="none" stroke-linecap="round"/>'
def i_plus(x, y, s, c): return f'<path d="M{x - s * .7},{y} L{x + s * .7},{y} M{x},{y - s * .7} L{x},{y + s * .7}" stroke="{c}" stroke-width="{s * .3}" stroke-linecap="round"/>'
def i_at(x, y, s, c): return f'<text x="{x}" y="{y + s * .55}" text-anchor="middle" font-family="{FONT}" font-weight="700" font-size="{s * 1.7}" fill="{c}">@</text>'
def i_img(x, y, s, c): return f'<rect x="{x - s}" y="{y - s * .75}" width="{s * 2}" height="{s * 1.5}" rx="{s * .2}" fill="{c}"/><circle cx="{x - s * .4}" cy="{y - s * .25}" r="{s * .2}" fill="#fff"/><path d="M{x - s},{y + s * .75} L{x - s * .2},{y} L{x + s * .3},{y + s * .5} L{x + s * .6},{y + s * .15} L{x + s},{y + s * .75}Z" fill="#fff" fill-opacity=".9"/>'


# scenes ---------------------------------------------------------------------
def sc_client(s):
    for i, (x, y) in enumerate([(1420, 150), (1360, 300), (1440, 450), (1560, 230), (1580, 390)]):
        s.node(x, y, 54, bot=i in (1, 4))
        s.arrow(x + 62, y, 1700 if i < 3 else 1760, y - 10 if i % 2 else y + 8)
    s.card(1690, 80, 250, 112, s.m, (1, .6), heart=True, tail="l")
    s.card(1760, 250, 250, 112, "#7c6ff0", (1, .75), tail="l")
    s.card(1690, 420, 250, 112, "#f59e5b", (1, .5), heart=True, tail="l")
    s.arrow(1950, 180, 2090, 240); s.arrow(2020, 305, 2090, 305); s.arrow(1950, 470, 2090, 370)
    s.server(2090, 190, 200, 70, 3)

def sc_server(s):
    s.server(1330, 175, 240, 80, 3)
    for i, (y, a) in enumerate([(95, s.m), (255, "#7c6ff0"), (415, "#f59e5b")]):
        s.card(1760, y, 460, 128, a, (1, .8, .45), heart=i != 1, avatar=True)
        s.arrow(1580, 300 + (i - 1) * 40, 1745, y + 64, col=s.m)
    s.line(1450, 520, 1450, 560, op=0)

def sc_client_forum(s):
    s.card(1380, 70, 520, 116, s.m, (1, .7), avatar=True)
    s.vote(1346, 100); s.vote(1346, 140, False)
    for i, (x, y) in enumerate([(1470, 232), (1560, 394)]):
        s.line(1420, 190, 1420, y + 50, w=5); s.line(1420, y + 50, x - 6, y + 50, w=5)
        s.card(x, y, 520, 116, ["#7c6ff0", "#f59e5b"][i], (1, .6), avatar=True)
    s.line(1500, 350, 1500, 440, w=5, op=0)
    s.line(1510, 348, 1510, 454, w=5); s.line(1510, 454, 1554, 454, w=5)
    for x, y, b in [(2150, 190, False), (2230, 120, True), (2200, 330, True), (2120, 450, False), (2270, 440, False)]:
        s.node(x, y, 46, bot=b)

def sc_server_forum(s):
    s.server(1330, 175, 240, 80, 3)
    for i, (y, a, n) in enumerate([(70, s.m, .45), (230, "#7c6ff0", .3), (390, "#f59e5b", .2)]):
        s.vote(1700, y + 34); s.add(f'<rect x="1700" y="{y + 62}" width="26" height="9" rx="4" fill="#cfdde1"/>'); s.vote(1700, y + 82, False)
        s.card(1760, y, 470, 130, a, (1, .8, n * 2), avatar=True)
        s.arrow(1585, 300, 1690, y + 64, col=s.m)

def sc_hpc(s):
    cx, cy = 1800, 300
    s.add(f'<circle cx="{cx}" cy="{cy}" r="230" fill="none" stroke="{s.m}" stroke-opacity=".3" stroke-width="3" stroke-dasharray="4 14" stroke-linecap="round"/>')
    for i in range(10):
        a = math.radians(i * 36 - 90); x, y = cx + 270 * math.cos(a) * 1.5, cy + 230 * math.sin(a)
        s.line(cx, cy, x, y, w=3, op=.35)
    for i in range(10):
        a = math.radians(i * 36 - 90); x, y = cx + 270 * math.cos(a) * 1.5, cy + 230 * math.sin(a)
        s.node(x, y, 44, main=[s.m, "#7c6ff0", "#f59e5b"][i % 3], bot=i % 2 == 0)
    s.node(cx, cy, 86, main=s.d)
    s.add(f'<text x="{cx}" y="{cy + 116}" text-anchor="middle" font-family="{FONT}" font-weight="700" font-size="22" fill="{s.d}" fill-opacity=".8">orchestrator</text>')

def sc_photo(s):
    cols = [("#f59e5b", "#fde1cb"), ("#7c6ff0", "#d9d5fb"), ("#e0566f", "#fadadf"), ("#2f8fa3", "#cbe7ec"), ("#3aa675", "#cfeadf"), ("#f2a93b", "#fbe8c3")]
    k = 0
    for r in range(2):
        for c in range(3):
            x, y = 1400 + c * 250, 110 + r * 235 + (28 if c == 1 else 0)
            m, l = cols[k]; k += 1
            s.add(f'<g filter="url(#sh)"><rect x="{x}" y="{y}" width="215" height="205" rx="24" fill="#fff"/></g>')
            s.add(f'<rect x="{x + 11}" y="{y + 11}" width="193" height="140" rx="16" fill="{l}"/>')
            s.add(i_img(x + 107, y + 81, 54, m))
            s.add(f'<rect x="{x + 16}" y="{y + 167}" width="84" height="10" rx="5" fill="{m}"/><rect x="{x + 16}" y="{y + 184}" width="130" height="8" rx="4" fill="#cfdde1"/>')
    for i, (x, m) in enumerate([(1470, "#f59e5b"), (1700, "#7c6ff0"), (1930, "#e0566f")]):
        s.add(f'<circle cx="{x + 60}" cy="60" r="36" fill="#fff" stroke="{m}" stroke-width="6"/>' + s.person(x + 60, 62, 40, m))

def sc_agents(s):
    items = [(1430, 230, "#2f8fa3", i_shield, "moderator"), (1650, 360, "#e0566f", i_mega, "propaganda"), (1870, 230, "#f2a93b", i_mask, "comic relief"), (2090, 360, "#7c6ff0", i_bolt, "stress test")]
    for a, b in zip(items, items[1:]):
        s.line(a[0], a[1], b[0], b[1], w=5, op=.35)
    for x, y, c, ic, lab in items:
        s.badge(x, y, 88, c, ic)
        s.add(f'<text x="{x}" y="{y + 130}" text-anchor="middle" font-family="{FONT}" font-weight="700" font-size="26" fill="{INK}" fill-opacity=".75">{lab}</text>')
    s.node(1560, 90, 40, bot=True); s.node(2250, 90, 40, bot=True); s.node(1380, 470, 40, bot=True)

def sc_memory(s):
    pts = [(1360, 440), (1520, 360), (1680, 450), (1840, 340), (1990, 430)]
    for i in range(len(pts) - 1): s.line(*pts[i], *pts[i + 1], w=4, op=.3)
    ops = [.35, .5, .7, .85, 1]
    for (x, y), o in zip(pts, ops):
        s.add(f'<g opacity="{o}">')
        s.card(x - 85, y - 100, 170, 80, s.m, (1, .6), tail="l")
        s.add('</g>')
        s.add(f'<circle cx="{x}" cy="{y + 10}" r="10" fill="{s.m}" fill-opacity="{o}"/>')
    s.node(2150, 190, 100, main=s.d)
    for (x, y), o in zip(pts, ops):
        s.add(f'<path d="M{x},{y + 10} C{x + 40},{y - 200} {2050},{300} 2118,{232}" fill="none" stroke="{s.m}" stroke-opacity="{o * .7}" stroke-width="4" stroke-dasharray="3 12" stroke-linecap="round"/>')
    s.card(1700, 70, 280, 108, "#f59e5b", (1, .7), heart=True, tail="r")
    s.add(f'<text x="2150" y="345" text-anchor="middle" font-family="{FONT}" font-weight="700" font-size="24" fill="{s.d}" fill-opacity=".8">remembers</text>')

def sc_reactive(s):
    s.card(1370, 120, 420, 150, "#7c6ff0", (1, .8), avatar=True)
    s.add(f'<rect x="1442" y="160" width="76" height="26" rx="13" fill="{s.l}"/>' + i_at(1480, 173, 11, s.d))
    s.node(1500, 440, 62)
    s.arrow(1580, 250, 1760, 330, col=s.m)
    s.node(1840, 340, 92, main=s.d, bot=True)
    s.add(i_bolt(1930, 270, 34, "#f59e5b"))
    s.card(1980, 400, 300, 120, s.m, (1, .75), heart=True, tail="l")
    s.arrow(1900, 420, 1970, 440, col=s.m)
    s.add(f'<circle cx="2160" cy="160" r="64" fill="#fff" stroke="{s.m}" stroke-width="6"/>' + i_bell(2160, 160, 36, s.m))
    s.add('<circle cx="2205" cy="112" r="20" fill="#e0566f"/><text x="2205" y="120" text-anchor="middle" font-family="DejaVu Sans" font-weight="700" font-size="24" fill="#fff">3</text>')

def sc_frontend(s):
    x, y, w, h = 1360, 80, 640, 440
    s.add(f'<g filter="url(#sh)"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="26" fill="#fff" stroke="{s.m}" stroke-width="5"/></g>')
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="62" rx="26" fill="{s.l}"/><rect x="{x}" y="{y + 36}" width="{w}" height="26" fill="{s.l}"/>')
    for k, c in enumerate(["#e0566f", "#f2a93b", "#3aa675"]): s.add(f'<circle cx="{x + 36 + k * 30}" cy="{y + 31}" r="9" fill="{c}"/>')
    for i, yy in enumerate([y + 94, y + 218, y + 342]):
        s.add(f'<circle cx="{x + 52}" cy="{yy + 36}" r="22" fill="{mix(s.m, "w", .6)}"/>' + s.person(x + 52, yy + 38, 36, s.m))
        s.add(f'<rect x="{x + 92}" y="{yy + 12}" width="150" height="12" rx="6" fill="{s.m}"/><rect x="{x + 92}" y="{yy + 38}" width="{w - 150}" height="10" rx="5" fill="#cfdde1"/><rect x="{x + 92}" y="{yy + 60}" width="{(w - 150) * .6}" height="10" rx="5" fill="#cfdde1"/>')
    for i, (px, py, c, ic) in enumerate([(2040, 110, "#7c6ff0", i_plus), (2150, 240, "#f59e5b", i_check), (2030, 380, "#e0566f", i_plus)]):
        s.add(f'<g filter="url(#sh)"><rect x="{px}" y="{py}" width="150" height="130" rx="26" fill="#fff" stroke="{c}" stroke-width="5"/></g>')
        s.add(ic(px + 75, py + 52, 28, c))
        s.add(f'<rect x="{px + 28}" y="{py + 96}" width="94" height="14" rx="7" fill="{mix(c, "w", .7)}"/><circle cx="{px + 100}" cy="{py + 103}" r="10" fill="{c}"/>')
        s.arrow(px - 6, py + 60, 2005, py + 60 - (20 if i == 1 else 0) , col=c) if i != 1 else s.arrow(px - 6, py + 60, 2010, py + 70, col=c)

def sc_scenario(s):
    xs = [1400 + i * 200 for i in range(5)]
    s.line(xs[0] - 60, 300, xs[-1] + 80, 300, w=8, op=.35)
    for i, x in enumerate(xs):
        s.add(f'<circle cx="{x}" cy="300" r="34" fill="#fff" stroke="{s.m}" stroke-width="6"/><text x="{x}" y="310" text-anchor="middle" font-family="{FONT}" font-weight="700" font-size="28" fill="{s.d}">R{i + 1}</text>')
    items = [(0, 90, s.m, True), (1, 450, "#7c6ff0", False), (2, 90, "#f59e5b", True), (2, 450, s.m, False), (3, 90, "#7c6ff0", False), (4, 450, "#f59e5b", True)]
    for i, y, c, hh in items:
        x = xs[i]
        s.line(x, 300 + (34 if y > 300 else -34), x, y + (112 if y < 300 else 0), w=4, dash="2 10", op=.5)
        s.card(x - 88, y, 176, 112, c, (1, .65), heart=hh, avatar=False)
    s.add(f'<circle cx="2330" cy="90" r="48" fill="#fff" stroke="{s.m}" stroke-width="6"/>' + i_clock(2330, 90, 26, s.m))

def sc_training(s):
    pts = [(1390, 400), (1600, 300), (1810, 400), (2020, 300), (2230, 400)]
    for a, b in zip(pts, pts[1:]): s.line(*a, *b, w=8, op=.3, dash="2 16")
    icons = [(i_book, s.m), (i_q, "#7c6ff0"), (i_book, "#f59e5b"), (i_check, "#3aa675"), (i_cap, s.d)]
    for k, ((x, y), (ic, c)) in enumerate(zip(pts, icons)):
        s.add(f'<g filter="url(#sh)"><circle cx="{x}" cy="{y}" r="76" fill="#fff" stroke="{c}" stroke-width="7"/></g>')
        s.add(ic(x, y, 36, c))
        if k < 3:
            s.add(f'<circle cx="{x + 56}" cy="{y - 56}" r="22" fill="#3aa675"/>' + i_check(x + 56, y - 56, 11, "#fff"))
        s.add(f'<text x="{x}" y="{y + 118}" text-anchor="middle" font-family="{FONT}" font-weight="700" font-size="24" fill="{INK}" fill-opacity=".7">step {k + 1}</text>')
    s.add(f'<rect x="1390" y="120" width="840" height="22" rx="11" fill="{s.l}"/><rect x="1390" y="120" width="560" height="22" rx="11" fill="{s.m}"/>')


PLUGINS = {
    "YClient": ("#2f8fa3", "Microblogging · client side", sc_client),
    "YServer": ("#2f8fa3", "Microblogging · server side", sc_server),
    "YClientReddit": ("#7c6ff0", "Forum · client side", sc_client_forum),
    "YServerReddit": ("#7c6ff0", "Forum · server side", sc_server_forum),
    "YSimulator": ("#3b6fd0", "Large-scale runs on HPC", sc_hpc),
    "YPhotoSharing": ("#f08a3c", "Photo-sharing runtime", sc_photo),
    "y_agents_plugins": ("#e0566f", "Special-purpose agents", sc_agents),
    "y_memory_subsystem": ("#3aa675", "Agent memory", sc_memory),
    "reactive_agents": ("#e8a02a", "Agents that react to humans", sc_reactive),
    "frontend_adds-on": ("#2b9be0", "Add-ons for the interface", sc_frontend),
    "ScenarioDesign": ("#5b4fd1", "Design scenarios before a run", sc_scenario),
    "TrainingModules": ("#2e9e6a", "Training courses on YSocial", sc_training),
}

if __name__ == "__main__":
    logo = base64.b64encode(open(sys.argv[1], "rb").read()).decode()
    out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    only = sys.argv[3:] or list(PLUGINS)
    for name in only:
        main, role, scene = PLUGINS[name]
        open(os.path.join(out, name + ".svg"), "w").write(S(main, logo).svg(name, role, scene))
    print("ok", len(only))
