"""animate_still.py — ทำภาพนิ่งให้ "มีชีวิต" แบบ 2.5D บนเครื่องตัวเอง ฟรี ไม่ใช้ AI/เครดิต/อินเทอร์เน็ต

ทางเลือกเสริมของสกิล cinematic-image-to-video (ไม่เชื่อม Higgsfield) ใช้แค่ Python + numpy + Pillow + ffmpeg
(มี OpenCV จะเร็วขึ้นเอง) ได้ตามมาตรฐาน CINEMATIC 3D ANIMATION ในส่วนที่ทำได้โดยไม่ต้องวาดภาพใหม่:
  กล้อง     dolly-in / ถอย / แพน / เงย / ก้ม / นิ่ง + ส่ายเบา ๆ แบบถือกล้อง (ease นุ่ม ไม่กระตุก)
  สภาพแวดล้อม  ไฟเมือง/โคมไฟกะพริบระยิบ (twinkle) · ฝุ่นละอองลอยในแสง (particles) · ไอน้ำลอยจากอาหาร (steam)
              · เงาสะท้อนบนพื้นเปียกพลิ้ว (ripple) · แสงจอ/โคมเต้นเบา ๆ (glow)
  ตัวละคร   หายใจ (breath: ขยาย-หดเบา ๆ รอบหน้าอก)
ทำไม่ได้ (ต้องใช้ AI image-to-video): กะพริบตา เปลี่ยนสีหน้า ขยับมือ น้ำตาไหล — ใช้ Higgsfield หรือ ComfyUI (comfy_i2v.py)

ใช้:
  python3 animate_still.py shot.png out.mp4 --seconds 8 --camera push-in --size 1080x1920 --fps 24 \
      --fx '{"twinkle": 1, "particles": 40, "steam": [[0.83, 0.47]], "breath": [[0.5, 0.45, 0.2]]}'
  พิกัดทุกตัวเป็นสัดส่วนของภาพ (0–1) จากมุมซ้ายบน · breath/glow = [x, y, รัศมีเทียบความกว้าง]
  ripple = [[x0, y0, x1, y1]] กรอบพื้นที่สะท้อน (อย่าครอบตัวละคร) · focus = [x, y] จุดที่กล้องดันเข้าไปหา
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


def animate(still, out, seconds=6.0, camera="push-in", size=(1080, 1920), fps=24, fx=None, seed=7, crf=18):
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
            frame = remap(src, mx, my)
            if use_aux:
                a = remap(aux, mx, my)
                if fx.get("twinkle"):
                    frame *= (1 + 0.16 * a[..., 0] * np.sin(2 * np.pi * 0.55 * t + a[..., 1]))[..., None]
                if fx.get("glow"):
                    frame *= (1 + 0.07 * a[..., 2] * (0.5 + 0.5 * math.sin(2 * np.pi * 0.35 * t)))[..., None]
            if parts or steam:
                acc = np.zeros((h, w), dtype=np.float32)
                if parts:
                    parts.draw(acc, t)
                if steam:
                    steam.draw(acc, t, lambda x, y, z=z, cx=cx, cy=cy: ((x - cx) * z + w / 2, (y - cy) * z + h / 2, z))
                acc = np.clip(acc, 0, 0.85)[..., None]
                frame = 1 - (1 - frame) * (1 - acc * np.array([1.0, 0.97, 0.92], dtype=np.float32))  # screen สีขาวอุ่น
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
    a = ap.parse_args(argv)
    w, h = (int(v) for v in a.size.lower().split("x"))
    animate(a.still, a.out, a.seconds, a.camera, (w, h), a.fps, json.loads(a.fx), a.seed)
    print(f"✔ {a.out}  {a.seconds:.1f} วิ {w}x{h} {a.fps} fps · กล้อง {a.camera} · {'OpenCV' if cv2 else 'numpy'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
