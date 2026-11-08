# -*- coding: utf-8 -*-
"""30초 키네틱 타이포그래피 — 피자 프랜차이즈 EDA 시사점
코드만으로 프레임을 그리고(Pillow), macOS 'say'(Yuna) 내레이션 + 합성 효과음을 붙여 MP4로 만든다.
사용: python3 kinetic.py            -> kinetic_insights.mp4
      python3 kinetic.py preview t1 t2 ...  -> 해당 시각 프레임 PNG
"""
import math, os, subprocess, sys, wave, json
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, TOTAL = 1920, 1080, 30, 30.0
CX = W // 2

# ── 색: 커니(Kearney) 퍼플을 강조색으로 ──────────────────────────
P = (120, 35, 220)        # #7823DC Kearney Purple
P2 = (170, 120, 245)      # 밝은 퍼플(보조)
PD = (62, 40, 100)        # 어두운 퍼플(비교용 막대)
BG = (13, 11, 19)
INK = (246, 244, 250)
GREY = (128, 122, 145)

FONT = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
WEIGHT = {'heavy': 16, 'xb': 14, 'bold': 6, 'semi': 4, 'med': 2, 'reg': 0}

# ── 이징 ─────────────────────────────────────────────────────────
def clamp(x): return 0.0 if x < 0 else 1.0 if x > 1 else x
def prog(t, a, b): return clamp((t - a) / (b - a))
def eo3(x): x = clamp(x); return 1 - (1 - x) ** 3
def eio(x): x = clamp(x); return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def eback(x, s=1.9):
    x = clamp(x); return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2
def ebounce(x):
    x = clamp(x); n, d = 7.5625, 2.75
    if x < 1 / d: return n * x * x
    if x < 2 / d: x -= 1.5 / d; return n * x * x + .75
    if x < 2.5 / d: x -= 2.25 / d; return n * x * x + .9375
    x -= 2.625 / d; return n * x * x + .984375

# ── 글자 스프라이트 ───────────────────────────────────────────────
@lru_cache(maxsize=None)
def font(size, w): return ImageFont.truetype(FONT, size, index=WEIGHT[w])

class Spr:
    __slots__ = ('im', 'ox', 'base', 'mid', 'w')

@lru_cache(maxsize=6000)
def sprite(s, size, w, color):
    f = font(size, w)
    l, t, r, b = f.getbbox(s) if s.strip() else (0, 0, 1, 1)
    asc, desc = f.getmetrics()
    im = Image.new('RGBA', (max(1, r - l) + 4, asc + desc + 4), (0, 0, 0, 0))
    if s.strip():
        ImageDraw.Draw(im).text((2 - l, 2), s, font=f, fill=color)
    sp = Spr(); sp.im = im; sp.ox = 2 - l; sp.base = 2 + asc
    gl, gt, gr, gb = f.getbbox('가', anchor='ls'); sp.mid = sp.base + (gt + gb) / 2
    sp.w = f.getlength(s)
    return sp

CTX = {'ex': 0.0, 'sx': 0.0, 'sy': 0.0}

def with_alpha(im, a):
    if a >= 0.999: return im
    r, g, b, al = im.split()
    return Image.merge('RGBA', (r, g, b, al.point(lambda v: int(v * a))))

def paste(fr, im, x, y, clip=None):
    x, y = int(round(x)), int(round(y))
    if clip:
        X0, Y0, X1, Y1 = [int(v) for v in clip]
        sx0, sy0 = max(0, X0 - x), max(0, Y0 - y)
        sx1, sy1 = min(im.width, X1 - x), min(im.height, Y1 - y)
        if sx1 <= sx0 or sy1 <= sy0: return
        im = im.crop((sx0, sy0, sx1, sy1)); x += sx0; y += sy0
    fr.paste(im, (x, y), im)

def text(fr, s, size, w, color, X, Y, ax='m', vy='base', alpha=1.0, clip=None, raw=False):
    """X,Y = 앵커점. ax: l(글자 원점)/m(가운데)/r(오른쪽 끝). vy: base(기준선)/mid(글자 중심)."""
    if not raw:
        alpha *= 1 - CTX['ex']; Y -= 50 * eio(CTX['ex']); X += CTX['sx']; Y += CTX['sy']
    if alpha <= 0.003 or size < 2: return
    sp = sprite(s, int(size), w, color)
    axp = {'l': sp.ox, 'm': sp.im.width / 2, 'r': sp.im.width - 2}[ax]
    ayp = sp.base if vy == 'base' else sp.mid
    paste(fr, with_alpha(sp.im, alpha), X - axp, Y - ayp, clip)

def tw(s, size, w): return font(int(size), w).getlength(s)

def parts_line(fr, parts, size, w, X, Y, ax='m', alpha=1.0, **kw):
    full = ''.join(p for p, _ in parts); total = tw(full, size, w)
    x = {'l': X, 'm': X - total / 2, 'r': X - total}[ax]
    for s, c in parts:
        text(fr, s, size, w, c, x, Y, ax='l', alpha=alpha, **kw); x += tw(s, size, w)

def rect(d, x0, y0, x1, y1, color, alpha=1.0, raw=False):
    if not raw:
        alpha *= 1 - CTX['ex']; dy = -50 * eio(CTX['ex']) + CTX['sy']; dx = CTX['sx']
        x0 += dx; x1 += dx; y0 += dy; y1 += dy
    if alpha <= 0.003 or x1 - x0 < 0.5: return
    d.rectangle((x0, y0, x1, y1), fill=color + (int(255 * alpha),))

# ── 배경 ─────────────────────────────────────────────────────────
def make_base():
    im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im)
    for y in range(36, H, 64):
        for x in range(32, W, 64):
            d.ellipse((x - 1.5, y - 1.5, x + 1.5, y + 1.5), fill=(34, 30, 46))
    return im
BASE = make_base()

# ── 장면들 (t: 장면 내 시각, D: 장면 길이) ──────────────────────
def scene_intro(fr, d, t, D):
    lab = '피자 프랜차이즈'; size = 50
    x0 = CX - tw(lab, size, 'bold') / 2
    for i, ch in enumerate(lab):
        a = 0.35 + i * 0.05; p = eo3(prog(t, a, a + 0.35))
        text(fr, ch, size, 'bold', P2, x0 + tw(lab[:i], size, 'bold'), 330 + (1 - p) * 28, ax='l', alpha=p)
    big = '9개 매장'; bs = 250
    x0 = CX - tw(big, bs, 'heavy') / 2
    for i, ch in enumerate(big):
        a = 1.25 + i * 0.08; p = eback(prog(t, a, a + 0.55))
        text(fr, ch, bs, 'heavy', P if ch == '9' else INK, x0 + tw(big[:i], bs, 'heavy'),
             610 - (1 - p) * 160, ax='l', alpha=prog(t, a, a + 0.15))
    bw = 820 * eio(prog(t, 1.9, 2.5))
    rect(d, CX - bw / 2, 660, CX + bw / 2, 672, P)
    pr = eo3(prog(t, 2.35, 2.95))
    parts_line(fr, [('6년', P), ('의 데이터', INK)], 108, 'bold', CX, 815 + (1 - pr) * 140,
               clip=(0, 660, W, 836))
    text(fr, '2020.01 — 2026.08 · 월별 실적 720건', 34, 'med', GREY, CX, 900, alpha=prog(t, 3.0, 3.5))

def scene_sales(fr, d, t, D):
    text(fr, '매출 성장률 2022 → 2025', 36, 'med', GREY, 1720, 300, ax='r', alpha=prog(t, 0.1, 0.4))
    p = eo3(prog(t, 0.0, 0.45))
    text(fr, '매출', 140, 'bold', INK, 200 - (1 - p) * 140, 480, ax='l', alpha=p)
    n = 17 * eo3(prog(t, 0.25, 1.25))
    sc = 1 + 0.08 * math.sin(math.pi * prog(t, 1.2, 1.5))
    text(fr, f'+{n:.0f}%', 340 * sc, 'heavy', P, 1720, 650, ax='r', alpha=prog(t, 0.2, 0.4))
    vals = [70.1, 83.0, 93.5, 99.9, 105.3, 109.5]
    for i, v in enumerate(vals):
        a = 0.3 + i * 0.08; g = eo3(prog(t, a, a + 0.55)); x = 200 + i * 84
        rect(d, x, 900 - 250 * v / 109.5 * g, x + 58, 900, P if i >= 2 else PD)
        text(fr, f"'{20 + i}", 24, 'med', GREY, x + 29, 940, alpha=g)

def scene_orders(fr, d, t, D):
    text(fr, '총주문건수 2022 → 2025', 36, 'med', GREY, 1720, 300, ax='r', alpha=prog(t, 0.1, 0.4))
    text(fr, '그런데', 60, 'med', GREY, 200, 330, ax='l', alpha=prog(t, 0.05, 0.35))
    p = eo3(prog(t, 0.35, 0.8))
    text(fr, '주문은', 140, 'bold', INK, 200 - (1 - p) * 140, 520, ax='l', alpha=p)
    f = ebounce(prog(t, 0.6, 1.4))
    text(fr, '-1%', 340, 'heavy', INK, 1720, 650 - (1 - f) * 520, ax='r', alpha=prog(t, 0.6, 0.7))
    x = 200
    p1 = eo3(prog(t, 1.15, 1.5))
    text(fr, '오히려', 104, 'bold', INK, x, 800 - (1 - p1) * 30, ax='l', alpha=p1)
    x += tw('오히려 ', 104, 'bold')
    p2 = eback(prog(t, 1.45, 1.9))
    text(fr, '줄었다', 104, 'bold', P, x, 800 - (1 - p2) * 90, ax='l', alpha=prog(t, 1.45, 1.6))

def scene_price(fr, d, t, D):
    if t > 2.3:
        amp = 16 * (1 - prog(t, 2.3, 2.75))
        CTX['sx'] = amp * math.sin(t * 93); CTX['sy'] = amp * math.cos(t * 71)
    p = eo3(prog(t, 0.05, 0.45))
    text(fr, '성장을 만든 건', 66, 'med', GREY, CX, 300 + (1 - p) * 30, alpha=p)
    pg = eback(prog(t, 0.9, 1.35))
    ga = (1 - 0.62 * prog(t, 1.75, 2.1)) * prog(t, 0.9, 1.05)
    text(fr, '고객', 230, 'heavy', INK, 600, 560 + (1 - pg) * 90, vy='mid', alpha=ga)
    gw = tw('고객', 230, 'heavy')
    sp = eio(prog(t, 1.45, 1.8))
    rect(d, 600 - gw / 2 - 30, 552, 600 - gw / 2 - 30 + (gw + 60) * sp, 572, P)
    text(fr, '아니라', 44, 'med', GREY, 600, 760, alpha=prog(t, 1.5, 1.8) * (1 - 0.5 * prog(t, 1.9, 2.1)))
    if t >= 2.0:
        k = eo3(prog(t, 2.0, 2.3))
        text(fr, '가격', 270 * (1 + 1.7 * (1 - k)), 'heavy', P, 1320, 560, vy='mid', alpha=prog(t, 2.0, 2.1))
    p = eo3(prog(t, 2.5, 2.9))
    parts_line(fr, [('객단가 ', INK), ('+19%', P2)], 64, 'semi', 1320, 790 + (1 - p) * 30, alpha=p)

@lru_cache(maxsize=1)
def stamp_img():
    sp = sprite('주범', 96, 'heavy', INK)
    pw, ph = sp.im.width + 70, 150
    im = Image.new('RGBA', (pw + 80, ph + 80), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((40, 40, 40 + pw, 40 + ph), 14, fill=P + (255,))
    im.paste(sp.im, (40 + 35, int(40 + ph / 2 - (sp.mid - 0))), sp.im)
    return im.rotate(8, resample=Image.BICUBIC, expand=True)

def scene_profit(fr, d, t, D):
    rows = [('매출', 17, PD, INK, 0.1), ('이익', 9, P, P2, 0.45)]
    for i, (lab, v, bc, vc, a) in enumerate(rows):
        y = 360 + i * 140; g = eo3(prog(t, a, a + 0.8))
        text(fr, lab, 64, 'bold', INK, 200, y, ax='l', alpha=prog(t, a, a + 0.2))
        L = 52 * v * g
        rect(d, 400, y - 52, 400 + L, y + 8, bc, alpha=prog(t, a, a + 0.1))
        text(fr, f'+{v * g:.0f}%', 64, 'heavy', vc, 400 + L + 28, y, ax='l', alpha=prog(t, a, a + 0.2))
    t0 = 2.35
    if t >= t0:
        k = eback(prog(t, t0, t0 + 0.35), 2.4)
        st = stamp_img(); s = 0.4 + 0.6 * k if k < 1 else k
        s = max(0.05, 1 + 0.9 * (1 - eo3(prog(t, t0, t0 + 0.3))))
        im = st.resize((int(st.width * s), int(st.height * s)), Image.BICUBIC)
        im = with_alpha(im, prog(t, t0, t0 + 0.1) * (1 - CTX['ex']))
        paste(fr, im, 360 - im.width / 2, 780 - im.height / 2)
    word = '인건비'; x0 = 580
    for i, ch in enumerate(word):
        a = 2.75 + i * 0.08; k = eo3(prog(t, a, a + 0.28))
        cx = x0 + tw(word[:i], 210, 'heavy') + tw(ch, 210, 'heavy') / 2
        text(fr, ch, 210 * (1 + 0.8 * (1 - k)), 'heavy', INK, cx, 790, vy='mid', alpha=prog(t, a, a + 0.08))
    v = 24.5 + 4.5 * eo3(prog(t, 3.2, 3.9))
    parts_line(fr, [('인건비율 24.5% → ', GREY), (f'{v:.1f}%', P2)], 52, 'semi', 1720, 860, ax='r',
               alpha=prog(t, 3.1, 3.3))

def scene_gap(fr, d, t, D):
    p = eo3(prog(t, 0.05, 0.45))
    parts_line(fr, [('두 매장이 ', INK), ('뒤처지고 있다', P)], 78, 'bold', CX, 250 + (1 - p) * 30, alpha=p)
    lw = eio(prog(t, 0.25, 0.8))
    x = 200
    while x < 200 + 1520 * lw:
        rect(d, x, 398, min(x + 22, 200 + 1520 * lw), 402, GREY); x += 36
    text(fr, '7개 매장 평균 이익률 18.3%', 34, 'med', GREY, 1720, 380, ax='r', alpha=prog(t, 0.5, 0.8))
    cards = [('광주 충장로점', '13.2%', '평균 대비 -5.1%p', 640), ('제주 연동점', '14.2%', '평균 대비 -4.1%p', 1280)]
    for i, (nm, v, dl, X) in enumerate(cards):
        a = 0.6 + i * 0.18
        off = -280 * (1 - eo3(prog(t, a, a + 0.9))) + 14 * prog(t, a + 0.9, D)
        al = prog(t, a, a + 0.2)
        text(fr, v, 180, 'heavy', P, X, 690 + off, alpha=al)
        text(fr, nm, 60, 'bold', INK, X, 790 + off, alpha=al)
        text(fr, dl, 38, 'med', GREY, X, 860 + off, alpha=al * prog(t, a + 0.6, a + 0.9))

def scene_action(fr, d, t, D):
    lines = [('고객', '을 늘리고'), ('사람', '을 지키고'), ('격차', '를 좁혀라')]
    starts = [0.1, 1.3, 2.5]; size = 124
    for i, (k, rest) in enumerate(lines):
        a = starts[i]
        if t < a: continue
        Y = 420 + i * 175
        dim = 1 - 0.55 * prog(t, starts[i + 1], starts[i + 1] + 0.3) if i < 2 else 1
        x0 = CX - tw(k + rest, size, 'heavy') / 2; kw = tw(k, size, 'heavy')
        pb = eio(prog(t, a, a + 0.35))
        rect(d, x0 - 20, Y - 112, x0 - 20 + (kw + 40) * pb, Y + 22, P, alpha=dim)
        r = eo3(prog(t, a + 0.05, a + 0.5)); clip = (0, Y - 140, W, Y + 34)
        text(fr, k, size, 'heavy', INK, x0, Y + (1 - r) * 150, ax='l', alpha=dim, clip=clip)
        text(fr, rest, size, 'heavy', INK, x0 + kw, Y + (1 - r) * 150, ax='l', alpha=dim, clip=clip)

def scene_end(fr, d, t, D):
    r = eio(prog(t, 0, 0.65)) * 1150
    d.ellipse((CX - r, 540 - r, CX + r, 540 + r), fill=P)
    p = eo3(prog(t, 0.45, 0.95))
    text(fr, '데이터가 말하는', 74, 'med', INK, CX, 470 + (1 - p) * 90, clip=(0, 380, W, 490))
    s = '다음 성장의 조건'; sz = 150; x0 = CX - tw(s, sz, 'heavy') / 2
    for i, ch in enumerate(s):
        a = 0.75 + i * 0.05; q = eo3(prog(t, a, a + 0.45))
        text(fr, ch, sz, 'heavy', INK, x0 + tw(s[:i], sz, 'heavy'), 660 + (1 - q) * 170, ax='l', clip=(0, 480, W, 700))
    lw = 360 * eio(prog(t, 1.5, 2.0))
    rect(d, CX - lw / 2, 712, CX + lw / 2, 718, INK)
    text(fr, '피자 프랜차이즈 9개 매장 · 2020–2026 실적 데이터 분석', 34, 'med', (225, 210, 250), CX, 800,
         alpha=prog(t, 1.8, 2.4))

SCENES = [scene_intro, scene_sales, scene_orders, scene_price, scene_profit, scene_gap, scene_action, scene_end]
TAGS = [None, ('01', '성장의 질'), ('01', '성장의 질'), ('01', '성장의 질'), ('02', '수익성'),
        ('03', '매장 격차'), ('→', '실행 과제'), None]
WIPE_AFTER = {0, 2, 3, 4, 5}   # 이 장면이 끝날 때 퍼플 와이프

# ── 타임라인: 내레이션 길이에서 계산 ─────────────────────────────
META = json.load(open(os.path.join(HERE, 'vo', 'meta.json')))
DUR = META['dur']; LEAD, GAP = 0.4, 0.4
VO_START = []
s = LEAD
for dd in DUR: VO_START.append(s); s += dd + GAP
VIS = [0.0] + [v - 0.15 for v in VO_START[1:]] + [TOTAL]
WIPES = [VIS[k + 1] for k in WIPE_AFTER]

def render(tg):
    k = max(i for i in range(len(SCENES)) if VIS[i] <= tg)
    t, D = tg - VIS[k], VIS[k + 1] - VIS[k]
    fr = BASE.copy(); d = ImageDraw.Draw(fr, 'RGBA')
    CTX.update(ex=prog(t, D - 0.22, D) if k < len(SCENES) - 1 else 0.0, sx=0.0, sy=0.0)
    SCENES[k](fr, d, t, D)
    CTX.update(ex=0.0, sx=0.0, sy=0.0)
    # 헤더
    if TAGS[k]:
        text(fr, 'PIZZA FRANCHISE  ·  EDA 2020–2026', 24, 'semi', GREY, 80, 92, ax='l')
        fresh = TAGS[k - 1] != TAGS[k]
        a = prog(t, 0.05, 0.4) if fresh else 1.0
        parts_line(fr, [(TAGS[k][0] + '   ', P2), (TAGS[k][1], INK)], 28, 'bold', 1840, 92, ax='r', alpha=a)
    # 진행 바
    d.rectangle((0, H - 8, W * tg / TOTAL, H), fill=(INK + (150,)) if k == len(SCENES) - 1 else P + (255,))
    # 퍼플 와이프 전환
    for b in WIPES:
        p = prog(tg, b - 0.25, b + 0.25)
        if 0 < p < 1:
            if p < .5: lead, tail = eio(p * 2) * (W + 320), -320
            else: lead, tail = W + 320, eio((p - .5) * 2) * (W + 320) - 320
            d.polygon([(tail, 0), (lead, 0), (lead - 220, H), (tail - 220, H)], fill=P)
            d.polygon([(lead, 0), (lead + 36, 0), (lead - 184, H), (lead - 220, H)], fill=P2)
    # 마지막 페이드아웃
    if tg > TOTAL - 0.6:
        fr = Image.blend(fr, Image.new('RGB', (W, H), BG), prog(tg, TOTAL - 0.6, TOTAL))
    return fr

# ── 오디오: 내레이션 + 합성 패드/효과음 ─────────────────────────
SR = 48000
def build_audio(path):
    n = int(TOTAL * SR); mix = np.zeros(n)
    tt = np.arange(n) / SR
    pad = sum(np.sin(2 * np.pi * f * tt) * a for f, a in [(55, .5), (110, .35), (164.8, .22), (220, .12), (329.6, .06)])
    pad *= (0.6 + 0.4 * np.sin(2 * np.pi * 0.25 * tt)) * np.minimum(1, tt / 2) * np.minimum(1, (TOTAL - tt) / 1.5)
    mix += pad * 0.035
    rng = np.random.default_rng(7)
    def add(x, at):
        i = int(at * SR); j = min(n, i + len(x)); mix[i:j] += x[: j - i]
    def whoosh(dur=0.5):
        m = int(dur * SR); w = rng.standard_normal(m)
        w = np.convolve(w, np.ones(24) / 24, mode='same')
        env = np.sin(np.pi * np.linspace(0, 1, m)) ** 2
        return w * env * 0.35
    def thump(f0=70, dur=0.35, g=0.6):
        m = int(dur * SR); x = np.arange(m) / SR
        fr = f0 * (1 + 1.5 * np.exp(-x * 30))
        return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-x * 11) * g
    for b in WIPES: add(whoosh(), b - 0.25)
    add(thump(), VIS[2] + 1.0)            # -1% 착지
    add(thump(60, .45, .8), VIS[3] + 2.0)  # 가격 쾅
    add(thump(80, .3, .6), VIS[4] + 2.35)  # 주범 도장
    add(thump(50, .6, .6), VIS[7])          # 엔딩
    for i in range(len(DUR)):
        w = wave.open(os.path.join(HERE, 'vo', f'{i}.wav'))
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32768.0
        add(x * 1.0, VO_START[i])
    mix = mix / max(1e-6, np.abs(mix).max()) * 0.92
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())

def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'preview':
        os.makedirs(os.path.join(HERE, 'preview'), exist_ok=True)
        for a in sys.argv[2:]:
            render(float(a)).save(os.path.join(HERE, 'preview', f'f_{float(a):05.2f}.png'))
        return
    wav = os.path.join(HERE, 'vo', 'mix.wav'); build_audio(wav)
    out = os.path.join(HERE, 'kinetic_insights.mp4')
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    p = subprocess.Popen([ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                          '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wav,
                          '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
                          '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', out],
                         stdin=subprocess.PIPE)
    for fi in range(int(TOTAL * FPS)):
        p.stdin.write(render(fi / FPS).tobytes())
        if fi % 150 == 0: print(f'frame {fi}', flush=True)
    p.stdin.close(); p.wait(); print('done', out)

if __name__ == '__main__':
    main()
