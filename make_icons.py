#!/usr/bin/env python3
"""Generates the app's bundled symbolic icon set (icons/hicolor/scalable/actions/*.svg).

GTK recolours symbolic SVGs by overriding `fill`, and (before GTK 4.20)
ignores `stroke`, so every glyph here is flattened to filled geometry:
strokes become unions of quads + round joins, drawn into a single
non-zero-winding <path>. Run:  python3 tools/make_icons.py [--preview out.png]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "icons", "hicolor", "scalable", "actions")
W = 1.5  # default stroke width on the 16x16 grid


def _area(pts):
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts))) / 2


class B:
    """Collects shapes: ('poly', pts) | ('disc', x, y, r) | ('ann', x, y, r_out, r_in)."""

    def __init__(self):
        self.shapes = []

    # --- filled primitives
    def poly(self, pts):
        pts = list(pts)
        if _area(pts) < 0:
            pts.reverse()
        self.shapes.append(("poly", pts))

    def disc(self, x, y, r):
        self.shapes.append(("disc", x, y, r))

    def rrect(self, x, y, w, h, r):
        self.poly(rrect_pts(x, y, w, h, r))

    def fillstroke(self, pts, w=1.0):
        self.poly(pts)
        self.line(list(pts), w, closed=True)

    # --- strokes
    def line(self, pts, w=W, closed=False, caps=True):
        n = len(pts)
        segs = n if closed else n - 1
        for i in range(segs):
            p, q = pts[i], pts[(i + 1) % n]
            dx, dy = q[0] - p[0], q[1] - p[1]
            d = math.hypot(dx, dy)
            if d < 1e-6:
                continue
            nx, ny = -dy / d * w / 2, dx / d * w / 2
            self.poly([(p[0] + nx, p[1] + ny), (q[0] + nx, q[1] + ny),
                       (q[0] - nx, q[1] - ny), (p[0] - nx, p[1] - ny)])
        # round joins where the path actually turns
        for i in range(n):
            if not closed and (i == 0 or i == n - 1):
                if caps:
                    self.disc(pts[i][0], pts[i][1], w / 2)
                continue
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            v1 = (b[0] - a[0], b[1] - a[1])
            v2 = (c[0] - b[0], c[1] - b[1])
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            if l1 < 1e-6 or l2 < 1e-6:
                continue
            cosang = max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))
            if math.degrees(math.acos(cosang)) > 9:
                self.disc(b[0], b[1], w / 2)

    def arc(self, cx, cy, r, a0, a1, w=W, caps=True):
        self.line(arc_pts(cx, cy, r, a0, a1), w, caps=caps)

    def ring(self, cx, cy, r, w=W):
        self.shapes.append(("ann", cx, cy, r + w / 2, r - w / 2))

    def rrect_stroke(self, x, y, w, h, r, sw=W):
        self.line(rrect_pts(x, y, w, h, r), sw, closed=True)

    def ellipse_stroke(self, cx, cy, rx, ry, sw=W):
        pts = [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
               for a in range(0, 360, 10)]
        self.line(pts, sw, closed=True)

    def dashed(self, p, q, dash=2.2, gap=1.7, w=W):
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        ux, uy = (q[0] - p[0]) / d, (q[1] - p[1]) / d
        t = 0
        while t < d - 0.01:
            e = min(t + dash, d)
            self.line([(p[0] + ux * t, p[1] + uy * t), (p[0] + ux * e, p[1] + uy * e)], w)
            t = e + gap

    def head(self, tip, ang, size=3.2):
        a = math.radians(ang)
        dx, dy = math.cos(a), math.sin(a)
        nx, ny = -dy, dx
        base = (tip[0] - dx * size, tip[1] - dy * size)
        self.fillstroke([tip, (base[0] + nx * size * 0.8, base[1] + ny * size * 0.8),
                         (base[0] - nx * size * 0.8, base[1] - ny * size * 0.8)], 0.8)

    # --- path output
    def path_d(self):
        out = []
        f = lambda v: ("%.2f" % v).rstrip("0").rstrip(".")
        for s in self.shapes:
            if s[0] == "poly":
                pts = s[1]
                out.append("M" + "L".join(f"{f(x)} {f(y)}" for x, y in pts) + "Z")
            elif s[0] == "disc":
                _, x, y, r = s
                out.append(f"M{f(x + r)} {f(y)}A{f(r)} {f(r)} 0 1 1 {f(x - r)} {f(y)}"
                           f"A{f(r)} {f(r)} 0 1 1 {f(x + r)} {f(y)}Z")
            else:
                _, x, y, ro, ri = s
                out.append(f"M{f(x + ro)} {f(y)}A{f(ro)} {f(ro)} 0 1 1 {f(x - ro)} {f(y)}"
                           f"A{f(ro)} {f(ro)} 0 1 1 {f(x + ro)} {f(y)}Z")
                # inner circle wound the opposite way = hole under non-zero fill
                out.append(f"M{f(x + ri)} {f(y)}A{f(ri)} {f(ri)} 0 1 0 {f(x - ri)} {f(y)}"
                           f"A{f(ri)} {f(ri)} 0 1 0 {f(x + ri)} {f(y)}Z")
        return "".join(out)

    def svg(self):
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
                f'<path fill="#2e3436" fill-rule="nonzero" d="{self.path_d()}"/></svg>\n')


def arc_pts(cx, cy, r, a0, a1):
    n = max(4, int(abs(a1 - a0) / 9) + 1)
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def rrect_pts(x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0),
                       (x + r, y + h - r, 90), (x + r, y + r, 180)):
        pts += arc_pts(cx, cy, r, a0, a0 + 90)
    return pts


def bez(p0, p1, p2, n=10):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / n for i in range(n + 1))]


def crescent(b, cx, cy, R, kx, ky, kr):
    """Outer disc (cx,cy,R) minus a bite (kx,ky,kr), as one polygon."""
    outer = [(cx + R * math.cos(math.radians(a)), cy + R * math.sin(math.radians(a)))
             for a in range(0, 360, 4)]
    inside = [math.hypot(x - kx, y - ky) < kr for x, y in outer]
    n = len(outer)
    start = next(i for i in range(n) if not inside[i] and inside[i - 1])
    run = []
    i = start
    while not inside[i % n]:
        run.append(outer[i % n])
        i += 1
    bite = [(kx + kr * math.cos(math.radians(a)), ky + kr * math.sin(math.radians(a)))
            for a in range(0, 360, 4)]
    bite = [p for p in bite if math.hypot(p[0] - cx, p[1] - cy) < R]
    bite.sort(key=lambda p: math.atan2(p[1] - ky, p[0] - kx))
    # rotate so the chain starts nearest the end of the outer run
    def d(p, q): return math.hypot(p[0] - q[0], p[1] - q[1])
    k = min(range(len(bite)), key=lambda j: d(bite[j], run[-1]))
    bite = bite[k:] + bite[:k]
    if d(bite[-1], run[-1]) < d(bite[0], run[-1]):
        pass
    # bite points are angularly ordered; choose the direction that ends near run[0]
    fwd, rev = bite, bite[::-1]
    # gaps wrap around: find contiguous chain starting at the point nearest run[-1]
    chain = sorted(bite, key=lambda p: math.atan2(p[1] - ky, p[0] - kx))
    # use the longest angular gap to find the break in the chain
    angs = [math.atan2(p[1] - ky, p[0] - kx) for p in chain]
    gaps = [((angs[(j + 1) % len(angs)] - angs[j]) % (2 * math.pi), j) for j in range(len(angs))]
    j = max(gaps)[1]
    chain = chain[j + 1:] + chain[:j + 1]
    if d(chain[0], run[-1]) > d(chain[-1], run[-1]):
        chain.reverse()
    b.fillstroke(run + chain, 0.9)


def sparkle(b, cx, cy, s):
    k = 0.3
    b.poly([(cx, cy - s), (cx + s * k, cy - s * k), (cx + s, cy), (cx + s * k, cy + s * k),
            (cx, cy + s), (cx - s * k, cy + s * k), (cx - s, cy), (cx - s * k, cy - s * k)])


# ---------------------------------------------------------------- building blocks
def plus(b, cx, cy, s=1.6, w=1.4):
    b.line([(cx - s, cy), (cx + s, cy)], w)
    b.line([(cx, cy - s), (cx, cy + s)], w)


def minus(b, cx, cy, s=1.6, w=1.4):
    b.line([(cx - s, cy), (cx + s, cy)], w)


def check(b, x=0, y=0, s=1.0, w=1.5):
    b.line([(x + 3.6 * s, y + 8.6 * s), (x + 6.4 * s, y + 11.4 * s), (x + 12.4 * s, y + 4.8 * s)], w)


def slash(b):
    b.line([(2.6, 2.6), (13.4, 13.4)], 1.5)


def xmark(b, cx, cy, s=2.0, w=1.5):
    b.line([(cx - s, cy - s), (cx + s, cy + s)], w)
    b.line([(cx - s, cy + s), (cx + s, cy - s)], w)


def speaker(b, x0=1.6):
    b.fillstroke([(x0, 6), (x0 + 2.4, 6), (x0 + 5.4, 3.3), (x0 + 5.4, 12.7), (x0 + 2.4, 10), (x0, 10)], 1.0)
    return x0 + 5.2  # x where waves are centred


def waves(b, cx, rs):
    for r in rs:
        b.arc(cx, 8, r, -46, 46)


def mic(b, cx=8.0):
    b.rrect_stroke(cx - 1.9, 1.9, 3.8, 7.4, 1.9)
    b.arc(cx, 7.4, 4.6, 0, 180)
    b.line([(cx, 12), (cx, 14.2)])
    b.line([(cx - 2.2, 14.4), (cx + 2.2, 14.4)])


def sun(b, cx, cy, core, r0, r1, filled=True, skip=(), w=1.4):
    if filled:
        b.disc(cx, cy, core)
    else:
        b.ring(cx, cy, core, w)
    for k in range(8):
        a = k * 45
        if a in skip:
            continue
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        b.line([(cx + c * r0, cy + s * r0), (cx + c * r1, cy + s * r1)], w)


def arc_arrow(b, cx, cy, r, a0, a1, w=W, size=3.0, lead=1.2):
    """Arc from a0 to a1 (clockwise on screen) ending in an arrowhead."""
    b.arc(cx, cy, r, a0, a1, w)
    a = math.radians(a1)
    ex, ey = cx + r * math.cos(a), cy + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)  # tangent for increasing angle
    b.head((ex + tx * lead, ey + ty * lead), a1 + 90, size)


def refresh(b, cx=8, cy=8, r=5.2, a0=45, a1=330, w=W):
    arc_arrow(b, cx, cy, r, a0, a1, w, 3.4, 1.8)


def monitor(b, filled):
    b.rrect_stroke(1.6, 2.4, 12.8, 9, 1.8)
    if filled:
        b.rrect(3.6, 4.4, 8.8, 5, 0.6)
    b.line([(8, 11.4), (8, 13.6)])
    b.line([(5, 13.8), (11, 13.8)])


def wifi(b):
    for r in (3.2, 6.0, 8.8):
        b.arc(8, 12.6, r, 225, 315)
    b.disc(8, 12.6, 1.2)


def plane(b):
    b.rrect(7, 1.4, 2, 13.2, 1)
    b.poly([(7.2, 6), (1.4, 10.4), (1.4, 12), (7.2, 10)])
    b.poly([(8.8, 6), (14.6, 10.4), (14.6, 12), (8.8, 10)])
    b.poly([(7.3, 12.2), (4.8, 14.2), (4.8, 15.2), (7.3, 14.2)])
    b.poly([(8.7, 12.2), (11.2, 14.2), (11.2, 15.2), (8.7, 14.2)])


def bluetooth(b):
    b.line([(4.4, 5.2), (11.4, 11), (8, 14.3), (8, 1.7), (11.4, 5), (4.4, 10.8)], 1.4)


def bell(b):
    pts = [(3, 11.6), (4.3, 10.4), (4.3, 7.2)] + arc_pts(8, 7.2, 3.7, 180, 360) + [(11.7, 10.4), (13, 11.6)]
    b.line(pts, closed=True)
    b.line([(8, 2), (8, 3.4)])
    b.disc(8, 13.3, 1.2)


def clipboard(b):
    b.rrect_stroke(3, 3, 10, 11.5, 1.6)
    b.rrect(5.6, 1.5, 4.8, 3, 1.1)


def globe(b):
    b.ring(8, 8, 6)
    b.ellipse_stroke(8, 8, 2.6, 6, 1.3)
    b.line([(2, 8), (14, 8)], 1.3)


def bolt_pts():
    return [(9.2, 1.5), (3.5, 9.2), (7.4, 9.2), (6.6, 14.5), (12.5, 6.6), (8.4, 6.6)]


def terminal(b):
    b.rrect_stroke(1.6, 2.6, 12.8, 10.8, 2)
    b.line([(4.6, 6), (7, 8.2), (4.6, 10.4)])
    b.line([(8.4, 10.6), (11.4, 10.6)])


def bubble(b):
    b.rrect_stroke(1.8, 1.8, 12.4, 9.6, 2.2)
    b.poly([(4, 11), (4, 14.6), (8, 11)])


def alarm(b):
    b.ring(8, 8.8, 5)
    b.line([(8, 6), (8, 8.8), (10, 10)])
    b.line([(1.9, 4.2), (4.1, 2)])
    b.line([(14.1, 4.2), (11.9, 2)])


def zzz(b):
    b.line([(3, 3), (9, 3), (3, 10.2), (9, 10.2)], 1.5)
    b.line([(10.6, 8.2), (14, 8.2), (10.6, 13.2), (14, 13.2)], 1.3)


def gear(b):
    b.ring(8, 8, 4.2)
    for k in range(8):
        a = math.radians(k * 45)
        b.line([(8 + math.cos(a) * 4.9, 8 + math.sin(a) * 4.9),
                (8 + math.cos(a) * 6.6, 8 + math.sin(a) * 6.6)], 2.2, caps=False)
    b.disc(8, 8, 1.6)


def play_tri(b, ox=0, oy=0, s=1.0):
    b.poly([(ox + 6.4 * s, oy + 5.2 * s), (ox + 6.4 * s, oy + 10.8 * s), (ox + 11 * s, oy + 8 * s)])


# ---------------------------------------------------------------- the set
ICONS = {}


def icon(name):
    def deco(fn):
        ICONS[name] = fn
        return fn
    return deco


@icon("volume-high")
def _(b):
    waves(b, speaker(b), (3.0, 5.6))


@icon("volume-low")
def _(b):
    waves(b, speaker(b), (3.0,))


@icon("volume-mute")
def _(b):
    speaker(b)
    xmark(b, 12, 8, 1.9)


@icon("volume-unmute")
def _(b):
    speaker(b)
    b.line([(9.8, 8.4), (11.5, 10.2), (14.6, 6)], 1.5)


@icon("volume-up")
def _(b):
    speaker(b)
    plus(b, 12.2, 8, 2.0)


@icon("volume-down")
def _(b):
    speaker(b)
    minus(b, 12.2, 8, 2.0)


@icon("volume-set")
def _(b):
    speaker(b)
    b.line([(12.6, 3.2), (12.6, 12.8)], 1.3)
    b.disc(12.6, 9, 1.7)


@icon("volume-adjust")
def _(b):
    speaker(b)
    plus(b, 12.4, 5, 1.7)
    minus(b, 12.4, 11.2, 1.7)


@icon("audio-restart")
def _(b):
    b.fillstroke([(1.6, 6.2), (3.6, 6.2), (6.2, 3.8), (6.2, 12.2), (3.6, 9.8), (1.6, 9.8)], 1.0)
    arc_arrow(b, 10.6, 8, 3.3, 50, 320, W, 2.8, 1.4)


@icon("mic")
def _(b):
    mic(b)


@icon("mic-mute")
def _(b):
    mic(b)
    slash(b)


@icon("mic-toggle")
def _(b):
    mic(b)
    b.dashed((2.6, 2.6), (13.4, 13.4), 2.2, 1.6, 1.5)


@icon("mic-set")
def _(b):
    mic(b, 5.4)
    b.line([(12.8, 3.2), (12.8, 12.8)], 1.3)
    b.disc(12.8, 9, 1.7)


@icon("mic-adjust")
def _(b):
    mic(b, 5.4)
    plus(b, 12.6, 5, 1.7)
    minus(b, 12.6, 11.2, 1.7)


@icon("play")
def _(b):
    b.fillstroke([(3.4, 2.8), (3.4, 13.2), (13, 8)], 1.2)


@icon("play-pause")
def _(b):
    b.fillstroke([(1.8, 3.2), (1.8, 12.8), (7.8, 8)], 1.1)
    b.rrect(9.8, 3, 1.8, 10, 0.7)
    b.rrect(12.6, 3, 1.8, 10, 0.7)


@icon("next")
def _(b):
    b.fillstroke([(2, 3.4), (2, 12.6), (10, 8)], 1.1)
    b.rrect(11.8, 3.2, 2, 9.6, 0.8)


@icon("previous")
def _(b):
    b.fillstroke([(14, 3.4), (14, 12.6), (6, 8)], 1.1)
    b.rrect(2.2, 3.2, 2, 9.6, 0.8)


@icon("stop")
def _(b):
    b.rrect(3, 3, 10, 10, 2.2)


@icon("brightness-up")
def _(b):
    sun(b, 7, 9, 1.9, 3.5, 4.9, skip=(315,))
    plus(b, 12.8, 3.2, 1.6)


@icon("brightness-down")
def _(b):
    sun(b, 7, 9, 1.9, 3.5, 4.9, skip=(315,))
    minus(b, 12.8, 3.2, 1.6)


@icon("brightness-set")
def _(b):
    sun(b, 8, 6.3, 1.8, 3.2, 4.5)
    b.line([(2.2, 13.4), (13.8, 13.4)], 1.3)
    b.disc(9.6, 13.4, 1.6)


@icon("brightness-adjust")
def _(b):
    sun(b, 5.6, 8, 1.7, 3.1, 4.3)
    plus(b, 12.8, 5, 1.7)
    minus(b, 12.8, 11.2, 1.7)


@icon("screen-on")
def _(b):
    monitor(b, True)


@icon("screen-off")
def _(b):
    monitor(b, False)


@icon("lock")
def _(b):
    b.rrect(3.2, 7.2, 9.6, 7, 1.6)
    b.line([(5.4, 7.4), (5.4, 5.2)] + arc_pts(8, 5.2, 2.6, 180, 360) + [(10.6, 7.4)])


@icon("sleep")
def _(b):
    zzz(b)


@icon("hibernate")
def _(b):
    for a in (90, 30, 150):
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        b.line([(8 - c * 6.2, 8 - s * 6.2), (8 + c * 6.2, 8 + s * 6.2)], 1.4)
        for sgn in (1, -1):
            ex, ey = 8 + sgn * c * 4.4, 8 + sgn * s * 4.4
            for da in (-40, 40):
                aa = math.radians(a + (180 if sgn < 0 else 0) + 180 + da)
                b.line([(ex, ey), (ex + math.cos(aa) * 1.5, ey + math.sin(aa) * 1.5)], 1.2)


@icon("hybrid-sleep")
def _(b):
    crescent(b, 6.8, 9.2, 5.4, 9.8, 7.0, 4.6)
    sparkle(b, 12, 4, 2.6)


@icon("moon")
def _(b):
    crescent(b, 8, 8, 6.2, 11.2, 5.4, 5.4)


@icon("sun")
def _(b):
    sun(b, 8, 8, 2.6, 4.7, 6.3)


@icon("log-out")
def _(b):
    b.line([(6.6, 2.2), (2.6, 2.2), (2.6, 13.8), (6.6, 13.8)])
    b.line([(6, 8), (13.2, 8)])
    b.line([(10.6, 5.4), (13.2, 8), (10.6, 10.6)])


@icon("restart")
def _(b):
    refresh(b)


@icon("refresh")
def _(b):
    refresh(b)


@icon("power")
def _(b):
    b.arc(8, 8.6, 5.2, 310, 590)
    b.line([(8, 2), (8, 8)])


@icon("screenshot-full")
def _(b):
    for pts in ([(2, 5.6), (2, 2), (5.6, 2)], [(10.4, 2), (14, 2), (14, 5.6)],
                [(2, 10.4), (2, 14), (5.6, 14)], [(10.4, 14), (14, 14), (14, 10.4)]):
        b.line(pts)
    b.disc(8, 8, 2.1)


@icon("screenshot-window")
def _(b):
    b.rrect_stroke(1.8, 2.6, 12.4, 10.8, 2)
    b.line([(1.8, 6.2), (14.2, 6.2)], 1.3)
    b.disc(4.2, 4.4, 0.7)
    b.disc(6.4, 4.4, 0.7)


@icon("screenshot-area")
def _(b):
    a, c = 2.2, 13.8
    b.dashed((a, a), (c, a))
    b.dashed((c, a), (c, c))
    b.dashed((c, c), (a, c))
    b.dashed((a, c), (a, a))


@icon("screenshot-clipboard")
def _(b):
    clipboard(b)
    b.ring(8, 9.4, 2, 1.3)


@icon("clipboard")
def _(b):
    clipboard(b)
    b.line([(5.8, 8), (10.2, 8)], 1.2)
    b.line([(5.8, 10.8), (9, 10.8)], 1.2)


@icon("clipboard-clear")
def _(b):
    clipboard(b)
    xmark(b, 8, 9.2, 1.7, 1.3)


@icon("trash")
def _(b):
    b.line([(2.4, 4), (13.6, 4)])
    b.line([(5.8, 4), (5.8, 2.4), (10.2, 2.4), (10.2, 4)], 1.3)
    b.line([(3.8, 4.6), (4.6, 14), (11.4, 14), (12.2, 4.6)], 1.4)
    b.line([(6.6, 6.8), (6.6, 11.6)], 1.2)
    b.line([(9.4, 6.8), (9.4, 11.6)], 1.2)


@icon("server")
def _(b):
    b.rrect_stroke(1.8, 2.2, 12.4, 5, 1.6)
    b.rrect_stroke(1.8, 8.8, 12.4, 5, 1.6)
    b.disc(4.8, 4.7, 0.8)
    b.disc(4.8, 11.3, 0.8)
    b.line([(8, 4.7), (11.4, 4.7)], 1.2)
    b.line([(8, 11.3), (11.4, 11.3)], 1.2)


@icon("bell")
def _(b):
    bell(b)


@icon("dnd")
def _(b):
    b.ring(8, 8, 5.8)
    b.line([(5, 8), (11, 8)], 1.8)


@icon("wifi")
def _(b):
    wifi(b)


@icon("wifi-off")
def _(b):
    wifi(b)
    slash(b)


@icon("airplane")
def _(b):
    plane(b)


@icon("airplane-off")
def _(b):
    plane(b)
    slash(b)


@icon("bluetooth")
def _(b):
    bluetooth(b)


@icon("bluetooth-off")
def _(b):
    bluetooth(b)
    slash(b)


@icon("terminal")
def _(b):
    terminal(b)


@icon("hourglass")
def _(b):
    b.line([(3.6, 1.9), (12.4, 1.9)])
    b.line([(3.6, 14.1), (12.4, 14.1)])
    b.line([(4.8, 2), (4.8, 4.4), (8, 8), (4.8, 11.6), (4.8, 14)], 1.4)
    b.line([(11.2, 2), (11.2, 4.4), (8, 8), (11.2, 11.6), (11.2, 14)], 1.4)


@icon("apps")
def _(b):
    for x, y in ((2, 2), (8.8, 2), (2, 8.8), (8.8, 8.8)):
        b.rrect(x, y, 5.2, 5.2, 1.4)


@icon("grid")
def _(b):
    for x, y in ((2.2, 2.2), (9, 2.2), (2.2, 9), (9, 9)):
        b.rrect_stroke(x, y, 4.8, 4.8, 1.3, 1.4)


@icon("globe")
def _(b):
    globe(b)


@icon("notify")
def _(b):
    b.rrect_stroke(1.5, 3.4, 13, 9.2, 2.4)
    b.disc(5, 8, 1.5)
    b.line([(8, 6.6), (12, 6.6)], 1.2)
    b.line([(8, 9.4), (10.8, 9.4)], 1.2)


@icon("run")
def _(b):
    b.rrect_stroke(2, 2, 12, 12, 3.2)
    play_tri(b)


@icon("startup")
def _(b):
    b.ring(8, 8, 5.9)
    play_tri(b)


@icon("comment")
def _(b):
    bubble(b)
    b.line([(4.8, 5), (11.2, 5)], 1.2)
    b.line([(4.8, 8), (9, 8)], 1.2)


@icon("text")
def _(b):
    b.line([(3, 3.8), (13, 3.8)], 1.7)
    b.line([(3, 3.8), (3, 5.6)], 1.5)
    b.line([(13, 3.8), (13, 5.6)], 1.5)
    b.line([(8, 3.8), (8, 13)], 1.7)
    b.line([(6, 13.2), (10, 13.2)], 1.5)


@icon("variable")
def _(b):
    b.line([(5.4, 2.4), (2.8, 2.4), (2.8, 13.6), (5.4, 13.6)])
    b.line([(10.6, 2.4), (13.2, 2.4), (13.2, 13.6), (10.6, 13.6)])
    xmark(b, 8, 8, 1.9, 1.5)


@icon("ask")
def _(b):
    bubble(b)
    b.line(arc_pts(8, 5.5, 1.8, 195, 405) + [(8, 8)], 1.3)
    b.disc(8, 9.4, 0.75)


@icon("branch")
def _(b):
    b.ring(4, 3.4, 1.7, 1.3)
    b.ring(4, 12.6, 1.7, 1.3)
    b.ring(12, 4.6, 1.7, 1.3)
    b.line([(4, 5.1), (4, 10.9)], 1.4)
    b.line(bez((12, 6.3), (12, 9.4), (4, 9.4)), 1.4)


@icon("repeat")
def _(b):
    b.line([(2.4, 8.4), (2.4, 6.2), (4.6, 4), (11.4, 4)])
    b.head((14.2, 4), 0, 3.0)
    b.line([(13.6, 7.6), (13.6, 9.8), (11.4, 12), (4.6, 12)])
    b.head((1.8, 12), 180, 3.0)


@icon("gear")
def _(b):
    gear(b)


@icon("puzzle")
def _(b):
    b.rrect(2.2, 5.6, 9.6, 8.4, 1.6)
    b.disc(6.6, 4.5, 1.9)
    b.disc(12.4, 10, 1.7)


@icon("alarm")
def _(b):
    alarm(b)


@icon("battery")
def _(b):
    b.rrect_stroke(1.4, 4.2, 11.4, 7.6, 1.9)
    b.rrect(13.5, 6.6, 1.3, 2.8, 0.6)
    for x in (3.4, 6.5, 9.6):
        b.rrect(x, 6.1, 2, 3.8, 0.5)


@icon("sleep-wake")
def _(b):
    zzz(b)


@icon("folder")
def _(b):
    b.line([(1.9, 3.9), (6, 3.9), (7.6, 5.7), (14.1, 5.7), (14.1, 13), (1.9, 13)], 1.5, closed=True)


@icon("automation")
def _(b):
    arc_arrow(b, 8, 8, 5, 200, 320, 1.5, 3.0, 1.6)
    arc_arrow(b, 8, 8, 5, 20, 140, 1.5, 3.0, 1.6)


@icon("more")
def _(b):
    for x in (3.4, 8, 12.6):
        b.disc(x, 8, 1.3)


@icon("grip")
def _(b):
    for x in (5.6, 10.4):
        for y in (3.6, 8, 12.4):
            b.disc(x, y, 1.1)


@icon("go-up")
def _(b):
    b.line([(3.6, 10.2), (8, 5.8), (12.4, 10.2)], 1.7)


@icon("go-down")
def _(b):
    b.line([(3.6, 5.8), (8, 10.2), (12.4, 5.8)], 1.7)


@icon("bolt")
def _(b):
    b.fillstroke(bolt_pts(), 1.0)


# ---------------------------------------------------------------- output / preview
def write_all():
    os.makedirs(OUT_DIR, exist_ok=True)
    for f in os.listdir(OUT_DIR):
        if f.startswith("sc-") and f.endswith(".svg"):
            os.remove(os.path.join(OUT_DIR, f))
    for name, fn in ICONS.items():
        b = B()
        fn(b)
        with open(os.path.join(OUT_DIR, f"sc-{name}-symbolic.svg"), "w", encoding="utf-8") as fh:
            fh.write(b.svg())
    print(f"wrote {len(ICONS)} icons to {os.path.normpath(OUT_DIR)}")


def preview(path, cell=84, cols=9, scale=8):
    from PIL import Image, ImageDraw
    names = list(ICONS)
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 16)), (47, 109, 240))
    d = ImageDraw.Draw(sheet)
    S = 8  # supersample
    px = 16 * scale
    for idx, name in enumerate(names):
        b = B()
        ICONS[name](b)
        mask = Image.new("L", (16 * S * 4, 16 * S * 4), 0)
        k = S * 4
        md = ImageDraw.Draw(mask)
        for s in b.shapes:
            if s[0] == "poly":
                md.polygon([(x * k, y * k) for x, y in s[1]], fill=255)
            elif s[0] == "disc":
                _, x, y, r = s
                md.ellipse([(x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k], fill=255)
        # annuli drawn last as masks so they don't punch other shapes
        for s in b.shapes:
            if s[0] == "ann":
                _, x, y, ro, ri = s
                layer = Image.new("L", mask.size, 0)
                ld = ImageDraw.Draw(layer)
                ld.ellipse([(x - ro) * k, (y - ro) * k, (x + ro) * k, (y + ro) * k], fill=255)
                ld.ellipse([(x - ri) * k, (y - ri) * k, (x + ri) * k, (y + ri) * k], fill=0)
                mask.paste(255, mask=layer)
        big = mask.resize((px, px), Image.LANCZOS)
        cx, cy = (idx % cols) * cell, (idx // cols) * (cell + 16)
        sheet.paste((255, 255, 255), (cx + (cell - px) // 2 if px < cell else cx, cy + 2), big if px <= cell else big.resize((cell, cell)))
        small = mask.resize((16, 16), Image.LANCZOS)
        sheet.paste((255, 255, 255), (cx + 2, cy + 2), small)
        d.text((cx + 2, cy + cell + 2), name[:14], fill=(255, 255, 255))
    sheet.save(path)


if __name__ == "__main__":
    write_all()
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
