"""animate_still.py — ทำภาพนิ่งให้ "มีชีวิต" แบบ 2.5D บนเครื่องตัวเอง ฟรี ไม่ใช้ AI/เครดิต/อินเทอร์เน็ต

ทางเลือกเสริมของสกิล cinematic-image-to-video (ไม่เชื่อม Higgsfield) ใช้แค่ Python + numpy + Pillow + ffmpeg
(มี OpenCV จะเร็วขึ้นเอง) ได้ตามมาตรฐาน CINEMATIC 3D ANIMATION ในส่วนที่ทำได้โดยไม่ต้องวาดภาพใหม่:
  กล้อง     dolly-in / ถอย / แพน / เงย / ก้ม / นิ่ง + ส่ายเบา ๆ แบบถือกล้อง (ease นุ่ม ไม่กระตุก)
  สภาพแวดล้อม  ไฟเมือง/โคมไฟกะพริบระยิบ (twinkle) · ฝุ่นละอองลอยในแสง (particles) · ไอน้ำลอยจากอาหาร (steam)
              · เงาสะท้อนบนพื้นเปียกพลิ้ว (ripple) · แสงจอ/โคมเต้นเบา ๆ (glow)
  ตัวละคร   หายใจ (breath) · กะพริบตา (blink) · ปากขยับตามเสียงพากย์ (talk + --audio) · ศีรษะเอียงเบา ๆ (head)
  ฉาก      รถไฟแล่นออกตามราง (train) · ฝน (rain) · โทนสีตามอารมณ์ไล่ทั้งฉาก (grade → gradeEnd: temp sat contrast lift vignette)
ทำไม่ได้ (ต้องใช้ AI image-to-video): มือ/ท่าทางเปลี่ยน สีหน้าเปลี่ยนรูป น้ำตาไหล — ใช้ Higgsfield หรือ ComfyUI (comfy_i2v.py)

ใช้:
  python3 animate_still.py shot.png out.mp4 --seconds 8 --camera push-in --size 1080x1920 --fps 24 \
      --fx '{"twinkle": 1, "particles": 40, "steam": [[0.83, 0.47]], "breath": [[0.5, 0.45, 0.2]]}'
  พิกัดทุกตัวเป็นสัดส่วนของภาพ (0–1) จากมุมซ้ายบน · breath/glow = [x, y, รัศมีเทียบความกว้าง]
  ripple = [[x0, y0, x1, y1]] กรอบพื้นที่สะท้อน (อย่าครอบตัวละคร) · focus = [x, y] จุดที่กล้องดันเข้าไปหา
  blink = [[cx, cy, rx, ry]] ตาแต่ละข้าง · talk = [x, y, w] รอยปิดปาก · head = [[คอx, คอy, รัศมี, องศา]]
  train = {"poly": [[x,y],...], "start": 0.8, "dur": 4.5, "shift": [0.2, -0.01], "shrink": 0.6}
  rain = {"drops": 140, "angle": 12, "region": [0,0,1,0.5]} · grade/gradeEnd = {"temp": -0.12, "sat": 0.85, "vignette": 0.35}
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

try:
    import cv2  # ไม่บังคับ: มีแล้วเร็วขึ้นราว 3–4 เท่า
except ImportError:  # pragma: no cover
    cv2 = None

CAMERAS = ("push-in", "pull-out", "pan-left", "pan-right", "tilt-up", "tilt-down", "static")


def smoothstep(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def drift(n, fps, seed, freq=0.33):
    """ค่าสุ่มที่เปลี่ยนช้า ๆ ต่อเนื่อง (ผลรวมไซน์) ช่วง ~[-1, 1] ใช้ทำกล้องส่ายแบบถือมือ"""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fps
    out = np.zeros(n)
    for k in range(3):
        f = freq * (1 + 0.7 * k) * rng.uniform(0.8, 1.25)
        out += np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) / (k + 1)
    return out / 1.83


def remap(src, mx, my):
    """สุ่มตัวอย่างแบบ bilinear: src[H,W,C] float32 ที่พิกัด (mx, my)"""
    if cv2 is not None:  # OpenCV รับเฉพาะแผนที่ float32
        return cv2.remap(src, mx.astype(np.float32, copy=False), my.astype(np.float32, copy=False),
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    h, w = src.shape[:2]
    mx = np.clip(mx, 0, w - 1.001)
    my = np.clip(my, 0, h - 1.001)
    x0 = mx.astype(np.int32)
    y0 = my.astype(np.int32)
    fx = (mx - x0)[..., None]
    fy = (my - y0)[..., None]
    a, b = src[y0, x0], src[y0, x0 + 1]
    c, d = src[y0 + 1, x0], src[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def cover(img, w, h):
    """ย่อ/ขยายให้เต็มกรอบแล้วตัดกลาง (เหมือน object-fit: cover)"""
    s = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def gauss_sprite(r):
    k = int(max(2, math.ceil(r * 3)))
    ax = np.arange(-k, k + 1, dtype=np.float32)
    g = np.exp(-(ax[None, :] ** 2 + ax[:, None] ** 2) / (2 * r * r))
    return g


def stamp(acc, sprite, cx, cy, gain):
    """บวก sprite (เกาส์) ลงภาพสะสม acc[H,W] ที่ (cx, cy)"""
    h, w = acc.shape
    k = sprite.shape[0] // 2
    x0, y0 = int(round(cx)) - k, int(round(cy)) - k
    x1, y1 = x0 + sprite.shape[1], y0 + sprite.shape[0]
    if x1 <= 0 or y1 <= 0 or x0 >= w or y0 >= h:
        return
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = sprite.shape[1] - max(0, x1 - w), sprite.shape[0] - max(0, y1 - h)
    acc[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] += gain * sprite[sy0:sy1, sx0:sx1]


def camera_path(kind, n, fps, w, h, focus=None, seed=7):
    """คืน (zoom, cx, cy) ต่อเฟรม เป็นพิกัดในภาพต้นทาง (ขนาดเท่าภาพผลลัพธ์)"""
    dz, dx, dy = drift(n, fps, seed), drift(n, fps, seed + 1), drift(n, fps, seed + 2)
    zs, cxs, cys = [], [], []
    fx, fy = (focus[0] * w, focus[1] * h) if focus else (w / 2, h / 2)
    for i in range(n):
        p = smoothstep(i / max(1, n - 1))
        z, cx, cy = 1.04, w / 2, h / 2
        if kind == "push-in":
            z = 1.03 + 0.09 * p
            cx, cy = w / 2 + (fx - w / 2) * 0.6 * p, h / 2 + (fy - h / 2) * 0.6 * p
        elif kind == "pull-out":
            z = 1.12 - 0.09 * p
            cx, cy = fx + (w / 2 - fx) * p, fy + (h / 2 - fy) * p
        elif kind in ("pan-left", "pan-right"):
            z = 1.10
            span = (w - w / z) / 2 * 0.85
            cx = w / 2 + (span if kind == "pan-left" else -span) * (1 - 2 * p)
        elif kind in ("tilt-up", "tilt-down"):
            z = 1.10
            span = (h - h / z) / 2 * 0.85
            cy = h / 2 + (span if kind == "tilt-up" else -span) * (1 - 2 * p)
        z *= 1 + 0.004 * dz[i]
        cx += 0.0022 * w * dx[i]
        cy += 0.0018 * h * dy[i]
        hw, hh = w / (2 * z), h / (2 * z)  # ไม่ให้มองเลยขอบภาพ
        zs.append(float(z))  # float ธรรมดา: ไม่ให้ numpy float64 ลากทั้งภาพเป็น float64
        cxs.append(float(min(max(cx, hw), w - hw)))
        cys.append(float(min(max(cy, hh), h - hh)))
    return zs, cxs, cys


class Steam:
    """ไอน้ำ: กลุ่มควันนุ่ม ๆ ลอยขึ้น ขยายตัว แกว่งเบา ๆ แล้วจางหาย (กำหนดผลล่วงหน้า เล่นซ้ำได้เหมือนเดิม)"""

    def __init__(self, anchors, w, h, seconds, seed=11):
        rng = np.random.default_rng(seed)
        self.puffs = []
        s = w / 1080
        for ax, ay in anchors:
            t = -3.0
            while t < seconds:
                self.puffs.append({"t0": t, "life": rng.uniform(2.6, 3.8), "x": ax * w + rng.normal(0, 14 * s),
                                   "y": ay * h + rng.normal(0, 5 * s), "rise": rng.uniform(170, 280) * s,
                                   "sway": rng.uniform(10, 24) * s, "ph": rng.uniform(0, 6.28),
                                   "r0": rng.uniform(12, 18) * s, "r1": rng.uniform(50, 80) * s,
                                   "a": rng.uniform(0.06, 0.11)})
                t += rng.uniform(0.05, 0.09)
        self.sprites = {}

    def draw(self, acc, t, to_out):
        for p in self.puffs:
            u = (t - p["t0"]) / p["life"]
            if not 0 <= u <= 1:
                continue
            x = p["x"] + p["sway"] * math.sin(p["ph"] + 2.2 * u * math.pi) * u
            y = p["y"] - p["rise"] * u
            r = p["r0"] + (p["r1"] - p["r0"]) * u
            ox, oy, z = to_out(x, y)
            key = int(r * z / 2)
            sp = self.sprites.get(key)
            if sp is None:
                sp = self.sprites[key] = gauss_sprite(max(2, key * 2) / 2.2)
            stamp(acc, sp, ox, oy, p["a"] * math.sin(math.pi * u) ** 1.2)


class Particles:
    """ฝุ่นละอองในแสง: จุดนุ่ม ๆ ลอยขึ้นช้า ๆ แกว่งเบา ๆ ความสว่างเต้นช้า (screen-space)"""

    def __init__(self, n, w, h, seed=5):
        rng = np.random.default_rng(seed)
        s = w / 1080
        self.w, self.h = w, h
        self.x = rng.uniform(0, w, n)
        self.y = rng.uniform(0, h, n)
        self.vx = rng.uniform(-6, 6, n) * s
        self.vy = -rng.uniform(4, 14, n) * s
        self.ph = rng.uniform(0, 6.28, n)
        self.a = rng.uniform(0.25, 0.6, n)
        self.r = rng.choice([1.6, 2.2, 3.0, 4.2], n) * s
        self.sprites = {r: gauss_sprite(r) for r in set(self.r.tolist())}

    def draw(self, acc, t):
        for i in range(len(self.x)):
            x = (self.x[i] + self.vx[i] * t + 10 * math.sin(self.ph[i] + 0.6 * t)) % self.w
            y = (self.y[i] + self.vy[i] * t) % self.h
            g = self.a[i] * (0.6 + 0.4 * math.sin(self.ph[i] * 3 + 1.3 * t))
            stamp(acc, self.sprites[self.r[i]], x, y, g)


def feather(h, w, f):
    """มาสก์สี่เหลี่ยมขอบนุ่ม: 0 ที่ขอบ → 1 ด้านใน ภายในระยะ f พิกเซล"""
    yy = np.minimum(np.arange(h), np.arange(h)[::-1]).astype(np.float32)[:, None]
    xx = np.minimum(np.arange(w), np.arange(w)[::-1]).astype(np.float32)[None, :]
    return np.clip(np.minimum(yy, xx) / max(1.0, f), 0, 1)


def soft(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


class Train:
    """รถไฟแล่นออกตามราง: ลบตัวรถออกจากฉาก (เติมด้วยแสงเมืองจากแถบด้านบน) แล้ววาดตัวรถเลื่อนไปทางปลายราง หดเล็ก แล้วจางหาย
    spec: {"poly": [[x, y], ...] รูปตัวรถ, "start": วินาทีที่เริ่มแล่น, "dur": วินาที, "shift": [dx, dy] ระยะรวม (สัดส่วนภาพ),
           "shrink": ขนาดสุดท้าย (เทียบเดิม)} · ก่อน start = จอดนิ่ง · หลังจบ = ไปแล้ว"""

    def __init__(self, src, spec, w, h):
        from PIL import ImageDraw
        pts = [(x * w, y * h) for x, y in spec["poly"]]
        self.x0 = max(0, int(min(p[0] for p in pts)) - 4)
        self.y0 = max(0, int(min(p[1] for p in pts)) - 4)
        self.x1 = min(w, int(max(p[0] for p in pts)) + 5)
        self.y1 = min(h, int(max(p[1] for p in pts)) + 5)
        bw, bh = self.x1 - self.x0, self.y1 - self.y0
        m = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(m).polygon([(x - self.x0, y - self.y0) for x, y in pts], fill=255)
        self.mask = np.asarray(m.filter(ImageFilter.GaussianBlur(2.5 * w / 1080)), np.float32) / 255.0
        self.layer = src[self.y0:self.y1, self.x0:self.x1].copy()
        donor = src[max(0, self.y0 - bh):self.y0, self.x0:self.x1]
        if donor.shape[0] != bh:
            donor = np.asarray(Image.fromarray((donor * 255).astype(np.uint8)).resize((bw, bh), Image.BICUBIC), np.float32) / 255
        fill = self.mask[..., None]
        self.base = src.copy()
        reg = self.base[self.y0:self.y1, self.x0:self.x1]
        self.base[self.y0:self.y1, self.x0:self.x1] = donor * fill + reg * (1 - fill)
        self.start, self.dur = float(spec.get("start", 0.0)), max(0.1, float(spec.get("dur", 5.0)))
        self.sx, self.sy = spec.get("shift", [0.2, 0.0])[0] * w, spec.get("shift", [0.2, 0.0])[1] * h
        self.shrink = float(spec.get("shrink", 0.6))
        self.bw, self.bh = bw, bh
        self.fade_r = np.clip((bw - np.arange(bw, dtype=np.float32)) / (0.18 * bw), 0, 1)[None, :]

    def apply(self, cur, t):
        u = (t - self.start) / self.dur
        reg = cur[self.y0:self.y1, self.x0:self.x1]
        if u <= 0:  # ยังจอดอยู่
            a = self.mask[..., None]
            reg[:] = self.layer * a + reg * (1 - a)
            return
        if u >= 1:
            return
        e = u ** 1.7  # ออกตัวช้าแล้วเร่ง
        s = 1 + (self.shrink - 1) * e
        tx, ty = self.sx * e, self.sy * e
        M = np.float32([[s, 0, (1 - s) * self.bw + tx], [0, s, (1 - s) * self.bh / 2 + ty]])  # หดเข้าหาปลายทางด้านขวา
        if cv2 is not None:
            lay = cv2.warpAffine(self.layer, M, (self.bw, self.bh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
            msk = cv2.warpAffine(self.mask, M, (self.bw, self.bh), flags=cv2.INTER_LINEAR, borderValue=0)
        else:  # ไม่มี OpenCV: เลื่อนอย่างเดียว
            dx, dy = int(round(tx)), int(round(ty))
            lay, msk = np.zeros_like(self.layer), np.zeros_like(self.mask)
            ys, xs = slice(max(0, dy), self.bh + min(0, dy)), slice(max(0, dx), self.bw + min(0, dx))
            yd, xd = slice(max(0, -dy), self.bh - max(0, dy)), slice(max(0, -dx), self.bw - max(0, dx))
            lay[ys, xs], msk[ys, xs] = self.layer[yd, xd], self.mask[yd, xd]
        a = (msk * self.fade_r * (1 - soft((u - 0.7) / 0.3)))[..., None]
        reg[:] = lay * a + reg * (1 - a)


class Blinker:
    """กะพริบตาเป็นธรรมชาติ (ทุก 2.4–4.4 วิ บางครั้งกะพริบสองครั้ง): ดึงผิวเปลือกตาด้านบน "ยืดลงมา" ปิดตา
    เส้นขนตาบนจึงเลื่อนลงตามขอบเปลือกตาเอง ได้แสงเงาเดิมของภาพ ไม่ใช่การระบายสีทับ
    eyes: [[cx, cy, rx, ry], ...] สัดส่วนภาพ (rx เทียบความกว้าง ry เทียบความสูง) ให้พอดีช่องตา (ตาขาว+ตาดำ)"""

    def __init__(self, eyes, base, w, h, seconds, seed=7):
        rng = np.random.default_rng(seed + 21)
        self.times, t = [], rng.uniform(0.5, 1.4)
        while t < seconds:
            self.times.append(t)
            if rng.random() < 0.18:
                self.times.append(t + 0.32)
            t += rng.uniform(2.4, 4.4)
        self.eyes = []
        for cx, cy, rx, ry in eyes:
            cx, cy, rx, ry = cx * w, cy * h, rx * w, ry * h
            x0, x1 = int(max(0, cx - 1.1 * rx)), int(min(w, cx + 1.1 * rx + 1))
            y0, y1 = int(max(0, cy - 2.2 * ry)), int(min(h, cy + 1.3 * ry + 1))
            yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            ex = np.clip((xx[0] - cx) / rx, -1, 1)
            half = ry * np.sqrt(np.maximum(0.0, 1 - ex * ex))
            top, bot = cy - half, cy + half              # ขอบบน/ล่างของช่องตาในแต่ละคอลัมน์
            ext = top - 0.9 * ry                         # ผิวเปลือกตาที่จะยืดลงมา
            wcol = soft((1 - np.abs((xx[0] - cx) / rx)) / 0.18)  # มุมตาเปลี่ยนน้อย ไม่ให้ขอบแตก
            self.eyes.append((y0, y1, x0, x1, xx - x0, yy, top, bot, ext, wcol))

    def closure(self, t):
        c = 0.0
        for tb in self.times:
            d = t - tb
            if 0 <= d < 0.07:
                c = max(c, d / 0.07)
            elif 0.07 <= d < 0.11:
                c = 1.0
            elif 0.11 <= d < 0.22:
                c = max(c, 1 - (d - 0.11) / 0.11)
        return float(soft(c))

    def apply(self, cur, t):
        c = self.closure(t)
        if c < 0.02:
            return
        for y0, y1, x0, x1, px, yy, top, bot, ext, wcol in self.eyes:
            lid = top + c * (bot - top) * 0.96                    # ขอบเปลือกตาใหม่
            span = np.maximum(1.0, lid - ext)
            stretched = ext + (yy - ext) * (top - ext) / span     # แถว ext..lid ← ผิว ext..top (ยืด)
            src_y = np.where((yy >= ext) & (yy <= lid), stretched, yy)
            src_y = yy + (src_y - yy) * wcol                       # มุมตาค่อย ๆ จางกลับเป็นภาพเดิม
            patch = cur[y0:y1, x0:x1].copy()
            cur[y0:y1, x0:x1] = remap(patch, px, src_y - y0)


def talk_envelope(audio, t0, n, fps):
    """ความเปิดของปาก 0–1 ต่อเฟรม จากความดังของเสียงพากย์ช่วง [t0, t0 + n/fps] (attack เร็ว release ช้า เหมือนพยางค์)"""
    sr = int(fps) * 1000
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", audio, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True)
    x = np.frombuffer(r.stdout, np.float32)
    hop = 1000
    k = len(x) // hop
    if k == 0:
        return np.zeros(n, np.float32)
    rms = np.sqrt(np.mean(x[:k * hop].reshape(k, hop) ** 2, axis=1) + 1e-10)
    db = 20 * np.log10(rms)
    voiced = db[db > -55]
    ref = float(np.percentile(voiced, 95)) if voiced.size else -20.0
    o = np.clip((db - (ref - 26)) / 22, 0, 1)
    i0 = int(round(t0 * fps))
    seg = np.zeros(n, np.float32)
    part = o[max(0, i0):max(0, i0) + n]
    seg[:len(part)] = part
    out, v = np.zeros(n, np.float32), 0.0
    for i, val in enumerate(seg):
        v += (0.6 if val > v else 0.35) * (val - v)
        out[i] = v
    return out ** 1.25


class Talker:
    """ปากขยับตามเสียงพากย์: ขากรรไกร/ริมฝีปากล่างเลื่อนลงตามความดัง + ช่องปากด้านใน (มีฟันบนเมื่อเปิดกว้าง)
    mouth: [x, y, w] จุดกึ่งกลางรอยปิดปาก และความกว้างช่วงที่ขยับ (สัดส่วนความกว้างภาพ)"""

    def __init__(self, mouth, w, h, env):
        self.mx, self.my, self.mw = mouth[0] * w, mouth[1] * h, mouth[2] * w
        x0, x1 = int(max(0, self.mx - 0.9 * self.mw)), int(min(w, self.mx + 0.9 * self.mw + 1))
        y0, y1 = int(max(0, self.my - 0.35 * self.mw)), int(min(h, self.my + 1.25 * self.mw + 1))
        self.box = (y0, y1, x0, x1)
        self.yy, self.xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        rel = (self.yy - self.my) / self.mw
        self.wgt = (np.exp(-((self.xx - self.mx) / (0.42 * self.mw)) ** 2) * soft(rel / 0.12)
                    * soft((1.15 - rel) / 0.45)).astype(np.float32)
        self.env = env
        self.mouth = np.array([0.30, 0.10, 0.11], np.float32)
        self.teeth = np.array([0.82, 0.76, 0.74], np.float32)

    def apply(self, cur, i):
        o = float(self.env[i]) if i < len(self.env) else 0.0
        if o < 0.04:
            return
        d = o * 0.22 * self.mw
        y0, y1, x0, x1 = self.box
        patch = cur[y0:y1, x0:x1].copy()
        warped = remap(patch, self.xx - x0, self.yy - d * self.wgt - y0)
        ax, ay = self.mw * (0.15 + 0.09 * o), max(1.0, 0.45 * d)
        e = ((self.xx - self.mx) / ax) ** 2 + ((self.yy - (self.my + 0.5 * d)) / ay) ** 2
        inner = (np.clip((1 - e) / 0.45, 0, 1) * 0.92)[..., None]          # ขอบนุ่ม กลืนกับริมฝีปาก
        depth = np.clip((self.yy - self.my) / max(1.0, d), 0, 1)[..., None]  # ด้านล่างช่องปากมืดกว่า
        col = self.mouth * (1.15 - 0.35 * depth)
        if o > 0.35:  # ฟันบนจาง ๆ เฉพาะตอนอ้ากว้าง
            tm = (np.clip((self.my + 0.22 * d - self.yy) / 2.0, 0, 1) * min(1.0, (o - 0.35) / 0.4) * 0.55)[..., None]
            col = col * (1 - tm) + self.teeth * tm
        cur[y0:y1, x0:x1] = warped * (1 - inner) + col * inner


class Rain:
    """ฝนตก: เส้นสายฝนบาง ๆ เฉียงเล็กน้อย สะท้อนแสง (screen-space) จำกัดพื้นที่ได้
    spec: true หรือ {"drops": 140, "angle": 12, "alpha": 1.0, "region": [x0, y0, x1, y1]}"""

    def __init__(self, spec, w, h, seed=7):
        spec = spec if isinstance(spec, dict) else {}
        rng = np.random.default_rng(seed + 31)
        s = w / 1080
        n = int(spec.get("drops", 140))
        x0, y0, x1, y1 = spec.get("region", [0, 0, 1, 1])
        self.reg = (x0 * w, y0 * h, x1 * w, y1 * h)
        ang = math.radians(float(spec.get("angle", 12)))
        self.ux, self.uy = math.sin(ang), math.cos(ang)
        self.x = rng.uniform(self.reg[0], self.reg[2], n)
        self.y = rng.uniform(self.reg[1], self.reg[3], n)
        self.sp = rng.uniform(900, 1400, n) * s
        self.L = rng.uniform(18, 42, n) * s
        self.a = rng.uniform(0.06, 0.16, n) * float(spec.get("alpha", 1.0))
        self.th = max(1, int(round(1.4 * s)))

    def draw(self, acc, t):
        x0, y0, x1, y1 = self.reg
        hh, ww = max(1.0, y1 - y0), max(1.0, x1 - x0)
        if cv2 is None:
            from PIL import ImageDraw
            layer = Image.new("L", (acc.shape[1], acc.shape[0]), 0)
            dr = ImageDraw.Draw(layer)
        for i in range(len(self.x)):
            dist = self.sp[i] * t
            y = y0 + (self.y[i] - y0 + dist) % hh
            x = x0 + (self.x[i] - x0 + dist * self.ux / self.uy) % ww
            p0, p1 = (int(x), int(y)), (int(x - self.L[i] * self.ux), int(y - self.L[i] * self.uy))
            if cv2 is not None:
                cv2.line(acc, p0, p1, float(self.a[i]), self.th)
            else:
                dr.line([p0, p1], fill=int(self.a[i] * 255), width=self.th)
        if cv2 is None:
            acc += np.asarray(layer, np.float32) / 255.0


def grade_params(fx, p):
    """โทนสีตามอารมณ์ของฉาก ไล่จาก grade → gradeEnd ตลอดฉาก"""
    g0 = fx.get("grade") or {}
    g1 = fx.get("gradeEnd") or g0
    return {k: float(g0.get(k, g1.get(k, 0 if k not in ("sat", "contrast") else 1))) * (1 - p)
            + float(g1.get(k, g0.get(k, 0 if k not in ("sat", "contrast") else 1))) * p
            for k in ("temp", "sat", "contrast", "lift", "vignette")}


def apply_grade(frame, g, vig):
    if g["temp"]:
        frame *= np.array([1 + 0.22 * g["temp"], 1 + 0.04 * g["temp"], 1 - 0.22 * g["temp"]], np.float32)
    if abs(g["sat"] - 1) > 1e-3:
        lum = (frame @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
        frame = lum + (frame - lum) * g["sat"]
    if abs(g["contrast"] - 1) > 1e-3:
        frame = (frame - 0.5) * g["contrast"] + 0.5
    if g["lift"]:
        frame = frame + g["lift"] * (1 - frame)
    if g["vignette"]:
        frame = frame * (1 - g["vignette"] * vig)[..., None]
    return frame


def animate(still, out, seconds=6.0, camera="push-in", size=(1080, 1920), fps=24, fx=None, seed=7, crf=18,
            audio=None, audio_t0=0.0):
    fx = dict(fx or {})
    w, h = size
    n = max(2, int(round(seconds * fps)))
    img = cover(Image.open(still).convert("RGB"), w, h)
    src = np.asarray(img, dtype=np.float32) / 255.0
    lum = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    aux = np.zeros((h, w, 3), dtype=np.float32)  # [ไฮไลต์, เฟสระยิบ, แสงเต้น] ติดไปกับภาพตามกล้อง
    if fx.get("twinkle"):
        # เฉพาะ "จุดไฟเล็ก ๆ" (ไฟเมือง โบเก้ หลอดไฟ) ไม่ใช่พื้นที่สว่างกว้าง ๆ อย่างเสื้อขาว: ไฮไลต์ลบค่าเฉลี่ยรอบข้าง (top-hat)
        hi = np.clip((lum - 0.55) / 0.30, 0, 1)
        to_img = lambda a: Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))  # noqa: E731
        local = np.asarray(to_img(hi).filter(ImageFilter.GaussianBlur(14 * w / 1080)), dtype=np.float32) / 255.0
        spot = np.clip((hi - local) * 2.2, 0, 1)
        spot = np.asarray(to_img(spot).filter(ImageFilter.GaussianBlur(2 * w / 1080)), dtype=np.float32) / 255.0
        if isinstance(fx["twinkle"], list):  # จำกัดเฉพาะกรอบที่กำหนด [[x0, y0, x1, y1], ...]
            keep = np.zeros_like(spot)
            for x0, y0, x1, y1 in fx["twinkle"]:
                keep[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 1
            spot *= np.asarray(to_img(keep).filter(ImageFilter.GaussianBlur(20 * w / 1080)), dtype=np.float32) / 255.0
        aux[..., 0] = spot
        rng = np.random.default_rng(seed + 3)
        ph = Image.fromarray((rng.uniform(0, 255, (max(2, h // 60), max(2, w // 60)))).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        aux[..., 1] = np.asarray(ph, dtype=np.float32) / 255.0 * 2 * np.pi
    for gx, gy, gr in fx.get("glow") or []:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        aux[..., 2] = np.maximum(aux[..., 2], np.exp(-((xx - gx * w) ** 2 + (yy - gy * h) ** 2) / (2 * (gr * w) ** 2)))
    use_aux = bool(fx.get("twinkle") or fx.get("glow"))
    zs, cxs, cys = camera_path(camera if camera in CAMERAS else "push-in", n, fps, w, h, fx.get("focus"), seed)
    X, Y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    parts = Particles(int(fx.get("particles", 0)), w, h, seed + 5) if fx.get("particles") else None
    steam = Steam(fx.get("steam") or [], w, h, seconds, seed + 11) if fx.get("steam") else None
    breaths = fx.get("breath") or []
    ripples = fx.get("ripple") or []
    heads = fx.get("head") or []
    train = Train(src, fx["train"], w, h) if fx.get("train") else None
    base = train.base if train else src
    blink = Blinker(fx["blink"], base, w, h, seconds, seed) if fx.get("blink") else None
    talk = Talker(fx["talk"], w, h, talk_envelope(audio, audio_t0, n, fps)) if fx.get("talk") and audio else None
    rain = Rain(fx["rain"], w, h, seed) if fx.get("rain") else None
    graded = bool(fx.get("grade") or fx.get("gradeEnd"))
    if graded:
        r2 = ((X - w / 2) / (w / 2)) ** 2 + ((Y - h / 2) / (h / 2)) ** 2
        vig = soft((r2 - 0.35) / 1.0).astype(np.float32)
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                             "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    try:
        for i in range(n):
            t = i / fps
            z, cx, cy = zs[i], cxs[i], cys[i]
            mx = cx + (X - w / 2) / z
            my = cy + (Y - h / 2) / z
            for bx, by, br in breaths:  # หายใจ: ขยายรอบอกเป็นจังหวะ ~4 วินาทีต่อรอบ
                amp = 0.018 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 4.0))
                ax_, ay_, rr = bx * w, by * h, br * w
                g = np.exp(-((mx - ax_) ** 2 + (my - ay_) ** 2) / (2 * (rr * 0.55) ** 2))
                mx = mx - (mx - ax_) * amp * g
                my = my - (my - ay_) * amp * g + 0.006 * rr * g * (0.5 - 0.5 * math.cos(2 * math.pi * t / 4.0))
            for x0, y0, x1, y1 in ripples:  # พื้นเปียก: เงาสะท้อนพลิ้วแนวนอน
                m = ((mx > x0 * w) & (mx < x1 * w) & (my > y0 * h) & (my < y1 * h)).astype(np.float32)
                depth = np.clip((my - y0 * h) / max(1.0, (y1 - y0) * h), 0, 1)
                mx = mx + m * (0.6 + 1.6 * depth) * (w / 1080) * np.sin(my / (7.0 * w / 1080) - 2 * np.pi * 0.8 * t)
            for hx_, hy_, hr_, deg in heads:  # ศีรษะเอียง/พยักเบา ๆ รอบจุดคอ
                th = math.radians(deg) * (0.65 * math.sin(2 * math.pi * t / 6.5 + 0.7) + 0.35 * math.sin(2 * math.pi * t / 2.9 + 2.1))
                px, py, rr = hx_ * w, hy_ * h, hr_ * w
                g = np.exp(-((mx - px) ** 2 + (my - (py - 0.55 * rr)) ** 2) / (2 * (0.6 * rr) ** 2))
                ang = -th * g
                ca, sa = np.cos(ang), np.sin(ang)
                dx, dy = mx - px, my - py
                mx, my = px + ca * dx - sa * dy, py + sa * dx + ca * dy
            cur = base
            if train or blink or talk:  # แก้ภาพต้นทางของเฟรมนี้ (รถไฟ ตา ปาก) ก่อนกล้องเคลื่อน
                cur = base.copy()
                if train:
                    train.apply(cur, t)
                if blink:
                    blink.apply(cur, t)
                if talk:
                    talk.apply(cur, i)
            frame = remap(cur, mx, my)
            if use_aux:
                a = remap(aux, mx, my)
                if fx.get("twinkle"):
                    frame *= (1 + 0.16 * a[..., 0] * np.sin(2 * np.pi * 0.55 * t + a[..., 1]))[..., None]
                if fx.get("glow"):
                    frame *= (1 + 0.07 * a[..., 2] * (0.5 + 0.5 * math.sin(2 * np.pi * 0.35 * t)))[..., None]
            if parts or steam or rain:
                acc = np.zeros((h, w), dtype=np.float32)
                if parts:
                    parts.draw(acc, t)
                if steam:
                    steam.draw(acc, t, lambda x, y, z=z, cx=cx, cy=cy: ((x - cx) * z + w / 2, (y - cy) * z + h / 2, z))
                if rain:
                    rain.draw(acc, t)
                acc = np.clip(acc, 0, 0.85)[..., None]
                frame = 1 - (1 - frame) * (1 - acc * np.array([1.0, 0.97, 0.92], dtype=np.float32))  # screen สีขาวอุ่น
            if graded:
                frame = apply_grade(frame, grade_params(fx, i / max(1, n - 1)), vig)
            proc.stdin.write((np.clip(frame, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc:
        raise RuntimeError(f"ffmpeg ล้มเหลว ({rc})")
    return out


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("still")
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--camera", default="push-in", choices=CAMERAS)
    ap.add_argument("--size", default="1080x1920")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--fx", default="{}", help="JSON ของเอฟเฟกต์ (ดูด้านบน)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--audio", help="เสียงพากย์ (สำหรับ fx talk: ปากขยับตามเสียง)")
    ap.add_argument("--audio-start", type=float, default=0.0, help="วินาทีในไฟล์เสียงที่ตรงกับเฟรมแรก")
    a = ap.parse_args(argv)
    w, h = (int(v) for v in a.size.lower().split("x"))
    animate(a.still, a.out, a.seconds, a.camera, (w, h), a.fps, json.loads(a.fx), a.seed, audio=a.audio,
            audio_t0=a.audio_start)
    print(f"✔ {a.out}  {a.seconds:.1f} วิ {w}x{h} {a.fps} fps · กล้อง {a.camera} · {'OpenCV' if cv2 else 'numpy'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
