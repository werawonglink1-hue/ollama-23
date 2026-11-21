#!/usr/bin/env python3
"""เรนเดอร์คลิปจาก project.json (ส่งออกจากเว็บ video-studio-web หรือที่ agent เขียน) เป็น MP4 ด้วย ffmpeg

ใช้:  python3 render.py project.json --out out/ [--formats 9x16,16x9] [--clips 1,3] [--fps 30]

ต่อคลิปจะได้  out/<n>_<slug>_<format>.mp4  + .srt + .ass
- สไตล์ collage (ค่าเริ่มต้นแบบคลิปตัวอย่าง): พื้นสีต่อบท ฮาล์ฟโทน หน้าต่างภาพขอบกระดาษฉีก ป้ายปี หัวข้อ
  สติกเกอร์วงกลม แถบซับกระดาษฉีก ซับคำต่อคำ และทรานซิชันสไลด์ระหว่างฉาก
- สไตล์อื่น: พื้นหลังสังเคราะห์ตาม visualStyle + Ken Burns
- ภาพ: scenes[j].media (รูป/วิดีโอ) ไม่มีก็สร้างภาพแทนที่ให้
- เสียง: clips[i].voice (ไฟล์พากย์ เริ่มที่วินาที 0; ทำจังหวะ/timings ด้วย voice_align.py) + project.musicFile · ปรับความดังรวม -14 LUFS (2 รอบ)
  หรือเพลงสังเคราะห์ตาม project.music + เสียงประกอบตาม {เสียง: ...} และตอนเปลี่ยนฉาก (project.sfxFiles หรือสังเคราะห์)
- ภาพคนแบบ PNG พื้นหลังโปร่งใสในฉาก "ภาพ: วงกลม" จะกลายเป็นสติกเกอร์ขอบขาวแบบคลิปตัวอย่าง
- ซับ: จาก script + clips[i].timings (ถ้ามี จากโหมดแตะเพื่อซิงก์) ไม่งั้นประมาณจากความเร็วอ่าน
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import struct
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_subs as bs  # noqa: E402

PALETTES = {  # ท้องฟ้าบน, ล่าง, สีจุด/วัตถุ ...
    "pastel3d":   ["#8f7bd8", "#f4b6d2", "#ffd9a8", "#7ec8f0", "#ff8a5c", "#ffffff"],
    "kinetic":    ["#2a1a5e", "#ff6a3d", "#3dd68c", "#ffcf3d", "#b04dff", "#ff9ec7"],
    "watercolor": ["#f6ecd8", "#e8d3b0", "#9cbf8f", "#e59a6b", "#7fa7c4", "#fff8ea"],
    "anime-dusk": ["#2b2d6e", "#f08a4b", "#ffd27a", "#c45ba8", "#ffffff", "#8fb6ff"],
    "papercut":   ["#f3e9d7", "#e6d5b8", "#c2523c", "#5f7f6a", "#e9b44c", "#2f3e46"],
    "neon-night": ["#060b2e", "#16307a", "#22e3ff", "#ff4fb3", "#7b5cff", "#ffe066"],
    "film":       ["#3b2a20", "#c79a6b", "#f1d9b0", "#8a5a3c", "#e8c79c", "#fff3dc"],
    "cinematic":  ["#0e1a24", "#3a3027", "#e0a85b", "#2f5d6b", "#c96f3b", "#f3e3c3"],
    "toon3d":     ["#6fa8dc", "#f6d7b0", "#f28c6b", "#5bb39a", "#ffd166", "#ffffff"],
}
SCALE = bs.FORMATS
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")

# กล้องเคลื่อนต่อฉาก: บรรทัดฉาก "| กล้อง: ดันเข้า" (ไม่ใส่ = วนตามสไตล์ ให้แต่ละฉากต่างกัน)
CAMERA = {"ดันเข้า": "push-in", "ซูมเข้า": "push-in", "push-in": "push-in", "zoom-in": "push-in",
          "ถอยออก": "pull-out", "ซูมออก": "pull-out", "pull-out": "pull-out", "zoom-out": "pull-out",
          "แพนซ้าย": "pan-left", "pan-left": "pan-left", "แพนขวา": "pan-right", "pan-right": "pan-right",
          "เงยขึ้น": "tilt-up", "tilt-up": "tilt-up", "ก้มลง": "tilt-down", "tilt-down": "tilt-down",
          "นิ่ง": "static", "static": "static"}
CAMERA_CYCLE = {"cinematic": ["push-in", "pan-right", "tilt-up", "pull-out", "pan-left", "tilt-down"],
                "toon3d": ["push-in", "pan-right", "static", "pull-out", "pan-left", "push-in"]}
# ทรานซิชันเข้าฉาก: "| เปลี่ยน: ดำ" (ตามเหตุการณ์ เช่น ข้ามเวลา=ดำ, ย้อนอดีต=ขาว, ตื่นเต้น=ซูม, ที่เดิม=ละลาย)
XFADE = {"ตัด": "cut", "cut": "cut", "จาง": "fade", "fade": "fade", "ดำ": "fadeblack", "จางดำ": "fadeblack",
         "fadeblack": "fadeblack", "ขาว": "fadewhite", "แฟลช": "fadewhite", "fadewhite": "fadewhite",
         "ละลาย": "dissolve", "dissolve": "dissolve", "สไลด์": "slideleft", "slideleft": "slideleft",
         "สไลด์นุ่ม": "smoothleft", "smoothleft": "smoothleft", "ปัด": "wipeleft", "wipeleft": "wipeleft",
         "ซูม": "zoomin", "zoomin": "zoomin", "วงกลม": "circleopen", "circleopen": "circleopen",
         "เบลอ": "hblur", "hblur": "hblur"}
XFADE_CYCLE = {"collage": ["slideleft"], "cinematic": ["fade", "dissolve", "smoothleft", "fadeblack", "zoomin", "fade"],
               "toon3d": ["cut", "fade", "cut", "smoothleft", "cut", "fadeblack"]}
XFADE_LEN = {"cut": 0.0, "fadeblack": 0.7, "fadewhite": 0.5, "dissolve": 0.6, "fade": 0.5, "zoomin": 0.5}
# โทนสี/แสงทั้งคลิป (project.grade): film = ฟิล์มอุ่น-เงาฟ้าอมเขียว คมขึ้น ขอบมืด เกรนบาง, soft = สว่างนุ่มละมุนตา
GRADES = {"film": "eq=contrast=1.06:saturation=0.9:gamma=0.98,colorbalance=rs=-0.03:bs=0.04:rh=0.05:gh=0.01:bh=-0.05,"
                  "unsharp=5:5:0.35:5:5:0,vignette=PI/5,noise=alls=5:allf=t",
          "soft": "eq=contrast=0.97:brightness=0.015:saturation=0.96,colorbalance=rh=0.03:bh=-0.02,"
                  "unsharp=5:5:0.25:5:5:0,vignette=PI/6",
          "none": ""}
GRADE_DEFAULT = {"cinematic": "film", "film": "film", "toon3d": "soft"}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-3000:])
        raise SystemExit(f"ffmpeg ล้มเหลว: {' '.join(cmd[:6])} ...")


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    a, b = hex2rgb(a), hex2rgb(b)
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))


# ---------- พื้นหลังสังเคราะห์ (สไตล์ทั่วไป) ----------
def make_background(path, w, h, style, seed, desc=""):
    from PIL import Image, ImageDraw, ImageFilter
    pal = [hex2rgb(c) for c in PALETTES.get(style, PALETTES["pastel3d"])]
    rnd = random.Random(seed)
    W, H = int(w * 1.2), int(h * 1.2)  # เผื่อซูม
    top, bot = pal[0], pal[1]
    night = any(k in desc for k in ("กลางคืน", "ดึก", "คืน", "จอดำ", "จอมืด"))
    if night and style != "neon-night":
        top, bot = (14, 18, 52), (40, 52, 120)
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    if "จอดำ" in desc or "จอมืด" in desc:
        img.save(path)
        return
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(rnd.randint(14, 24)):
        c = pal[rnd.randint(2, len(pal) - 1)]
        r = rnd.randint(int(min(W, H) * 0.02), int(min(W, H) * 0.16))
        x, y = rnd.randint(0, W), rnd.randint(0, int(H * 0.75))
        if style in ("papercut", "kinetic"):
            d.ellipse([x - r, y - r, x + r, y + r], fill=c + (230,))
        else:
            d.ellipse([x - r, y - r // 2, x + r, y + r // 2], fill=c + (rnd.randint(60, 170),))
    if style == "neon-night" or night:
        for _ in range(160):
            x, y = rnd.randint(0, W), rnd.randint(0, int(H * 0.6))
            s = rnd.choice((1, 1, 2, 3))
            d.ellipse([x, y, x + s, y + s], fill=(255, 255, 255, rnd.randint(120, 255)))
    if style not in ("papercut", "kinetic"):
        layer = layer.filter(ImageFilter.GaussianBlur(6))
    img.paste(layer, (0, 0), layer)
    city = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(city)
    x, base = 0, int(H * 0.82)
    shade = tuple(max(0, int(v * 0.55)) for v in bot)
    while x < W:
        bw = rnd.randint(int(W * 0.06), int(W * 0.16))
        bh = rnd.randint(int(H * 0.08), int(H * 0.26))
        cd.rectangle([x, base - bh, x + bw, H], fill=shade + (235,))
        for wy in range(base - bh + 20, base - 10, 46):
            for wx in range(x + 14, x + bw - 20, 38):
                if rnd.random() < 0.45:
                    cd.rectangle([wx, wy, wx + 16, wy + 22], fill=pal[2] + (200,))
        x += bw + rnd.randint(0, 12)
    img.paste(city, (0, 0), city)
    img.save(path)


# ---------- สไตล์สารคดีคอลลาจ ----------
def _torn(x0, x1, y, amp, rnd):
    n = max(8, round(abs(x1 - x0) / (amp * 2.4)))
    return [(x0 + (x1 - x0) * i / n, y + (0 if i in (0, n) else (rnd.random() - 0.5) * 2 * amp)) for i in range(n + 1)]


def _torn_v(x, y0, y1, amp, rnd):
    n = max(8, round(abs(y1 - y0) / (amp * 2.4)))
    return [(x + (0 if i in (0, n) else (rnd.random() - 0.5) * 2 * amp), y0 + (y1 - y0) * i / n) for i in range(n + 1)]


def _window_poly(L, ox, oy, seed, grow=0.0):
    x0, x1, y0, y1 = L["win"]
    a = L["amp"]
    if L["portrait"]:
        pts = _torn(x0 - 2, x1 + 2, y0 - grow, a, random.Random(seed)) + _torn(x1 + 2, x0 - 2, y1 + grow, a, random.Random(seed + 7))
    else:
        pts = [(x0 - grow, y0 - 2), (x1 + 2, y0 - 2), (x1 + 2, y1 + grow)] + _torn_v(x0 - grow, y1 + grow, y0 - 2, a, random.Random(seed))
    return [(ox + x, oy + y) for x, y in pts]


def _halftone(draw, box, step, rad, fill):
    x0, y0, x1, y1 = box
    y = y0 + step / 2
    while y < y1:
        x = x0 + step / 2
        while x < x1:
            draw.ellipse([x - rad, y - rad, x + rad, y + rad], fill=fill)
            x += step
        y += step


def _dot_cluster(draw, cx, cy, R, step, fill):
    y = -R
    while y <= R:
        x = -R
        while x <= R:
            d = math.hypot(x, y) / R
            r = step * 0.45 * (1 - d)
            if d <= 1 and r >= 0.7:
                draw.ellipse([cx + x - r, cy + y - r, cx + x + r, cy + y + r], fill=fill)
            x += step
        y += step


def _paste_masked(dst, layer, mask_shape):
    """วาง layer (RGBA) ลงบน dst เฉพาะในรูปทรง mask_shape (callable รับ ImageDraw ของ mask)"""
    from PIL import Image, ImageChops, ImageDraw
    mask = Image.new("L", dst.size, 0)
    mask_shape(ImageDraw.Draw(mask))
    dst.alpha_composite(Image.merge("RGBA", (*layer.split()[:3], ImageChops.multiply(layer.getchannel("A"), mask))))


def _load_image(path, tmpdir):
    from PIL import Image
    if not path or not os.path.exists(path):
        return None
    if path.lower().endswith(VIDEO_EXT):  # ใช้เฟรมจากวิดีโอสำหรับสติกเกอร์วงกลม
        frame = os.path.join(tmpdir, "frame_" + os.path.basename(path) + ".png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", path, "-frames:v", "1", frame])
        path = frame if os.path.exists(frame) else None
    try:
        return Image.open(path).convert("RGB") if path else None
    except OSError:
        return None


def _load_cutout(path):
    """PNG/WebP ที่มีพื้นหลังโปร่งใส (เช่น จาก remove_background ของ Higgsfield) → ใช้ทำสติกเกอร์คนขอบขาว"""
    from PIL import Image
    if not path or not os.path.exists(path) or not path.lower().endswith((".png", ".webp")):
        return None
    try:
        im = Image.open(path).convert("RGBA")
    except OSError:
        return None
    lo, hi = im.getchannel("A").getextrema()
    return im.crop(im.getchannel("A").getbbox()) if lo < 200 and hi > 0 else None


def _sticker(cut, height, stroke):
    """ย่อภาพตัดพื้นหลังให้สูง height แล้วใส่ขอบขาว + เงา แบบสติกเกอร์ในคลิปตัวอย่าง"""
    from PIL import Image, ImageFilter
    sc = height / cut.height
    cut = cut.resize((max(2, int(cut.width * sc)), max(2, int(cut.height * sc))), Image.LANCZOS)
    pad = stroke * 2
    a = Image.new("L", (cut.width + pad * 2, cut.height + pad * 2), 0)
    a.paste(cut.getchannel("A"), (pad, pad))
    small = a.resize((max(1, a.width // 2), max(1, a.height // 2)))
    k = max(3, stroke | 1)
    grown = small.filter(ImageFilter.MaxFilter(k)).resize(a.size).point(lambda v: 255 if v > 90 else 0)
    out = Image.new("RGBA", a.size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", a.size, (0, 0, 0, 0))
    shadow.putalpha(grown.filter(ImageFilter.GaussianBlur(stroke)).point(lambda v: int(v * 0.35)))
    out.alpha_composite(shadow, (stroke // 2, stroke))
    white = Image.new("RGBA", a.size, (255, 255, 255, 0))
    white.putalpha(grown)
    out.alpha_composite(white)
    out.alpha_composite(cut, (pad, pad))
    return out


def is_circle(scene, j):
    layout = (scene.meta or {}).get("layout", "")
    if any(k in layout for k in ("วงกลม", "สติกเกอร์", "circle")):
        return True
    return not any(k in layout for k in ("เต็ม", "full")) and j % 3 == 1


def collage_overlay(path, w, h, scene, j, clip_index, framed, media_path, hole, tmpdir):
    """วาดการ์ดคอลลาจทั้งเฟรม (RGBA). hole=True: หน้าต่างภาพโปร่งใสให้ ffmpeg วางสื่อด้านล่าง"""
    from PIL import Image, ImageDraw, ImageOps
    col = bs.scene_color(scene, j, clip_index)
    cx0, cy0, cw, ch = bs.card_rect(w, h, framed)
    L = bs.collage_layout(cw, ch)
    seed = clip_index * 131 + j * 17 + 3
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(img, "RGBA")
    card = (cx0, cy0, cx0 + cw, cy0 + ch)
    d.rectangle(card, fill=hex2rgb(col) + (255,))
    _halftone(d, card, max(5, cw / 75), max(1, cw / 75 * 0.13), (0, 0, 0, 20))
    d.polygon(_window_poly(L, cx0, cy0, seed + 1, L["amp"] * 1.6), fill=mix(col, "#ffffff", 0.75) + (255,))
    win = _window_poly(L, cx0, cy0, seed)
    wx0, wx1, wy0, wy1 = L["win"]
    bx, by, bw, bh = cx0 + wx0, cy0 + wy0, wx1 - wx0, wy1 - wy0
    circle = is_circle(scene, j)
    content = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(content, "RGBA")
    if circle:
        cd.rectangle([bx, by, bx + bw, by + bh], fill=mix(col, "#ffffff", 0.22) + (255,))
        R = min(bw, bh) * 0.42
        ccx, ccy = bx + bw / 2, by + bh * 0.53
        acc = "#f6c624" if col in ("#b3123a", "#e94b6a") else "#e8304a"
        cd.ellipse([ccx - R, ccy - R, ccx + R, ccy + R], fill=hex2rgb(acc) + (255,))
        _halftone(cd, (ccx - R * 0.72, ccy - R * 0.72, ccx + R * 0.72, ccy + R * 0.72), max(6, R / 9), max(1.5, R / 9 * 0.25), (255, 255, 255, 90))
        cut = _load_cutout(media_path)
        if cut is not None:  # คนตัดพื้นหลัง (PNG โปร่งใส) เป็นสติกเกอร์ขอบขาว โผล่พ้นวงกลมด้านล่างแบบคลิปตัวอย่าง
            st = _sticker(cut, min(R * 1.85, bh * 0.9), max(6, int(R * 0.06)))
            if st.width > bw * 0.98:
                st = st.resize((int(bw * 0.98), int(st.height * bw * 0.98 / st.width)))
            content.alpha_composite(st, (int(ccx - st.width / 2), int(min(by + bh, ccy + R * 1.02) - st.height)))
        else:  # รูปทั่วไป: ครอปเป็นวงกลมขอบขาว
            r2, cyy = R * 0.8, ccy - R * 0.06
            cd.ellipse([ccx - r2 - 4, cyy - r2 + 6, ccx + r2 + 4, cyy + r2 + 14], fill=(0, 0, 0, 70))
            cd.ellipse([ccx - r2, cyy - r2, ccx + r2, cyy + r2], fill=(255, 255, 255, 255))
            ri = r2 * 0.93
            size = (max(2, int(ri * 2)), max(2, int(ri * 2)))
            pic = _load_image(media_path, tmpdir)
            if pic is not None:
                pic = ImageOps.fit(pic, size)
            else:  # ภาพแทนที่: เงาคน
                pic = Image.new("RGB", size, mix(col, "#ffffff", 0.55))
                pd = ImageDraw.Draw(pic)
                s0, dark = size[0], mix(col, "#000000", 0.35)
                pd.ellipse([s0 * 0.34, s0 * 0.24, s0 * 0.66, s0 * 0.56], fill=dark)
                pd.ellipse([s0 * 0.19, s0 * 0.61, s0 * 0.81, s0 * 1.11], fill=dark)
            m2 = Image.new("L", size, 0)
            ImageDraw.Draw(m2).ellipse([0, 0, size[0] - 1, size[1] - 1], fill=255)
            content.paste(pic, (int(ccx - ri), int(cyy - ri)), m2)
    elif not hole:  # ภาพแทนที่: ฟ้าโทนสีฉาก + วงกลมฮาล์ฟโทน + เมือง
        top, bot = mix(col, "#ffffff", 0.55), mix(col, "#ffffff", 0.2)
        for yy in range(int(by), int(by + bh) + 1):
            t = (yy - by) / max(1, bh)
            cd.line([(bx, yy), (bx + bw, yy)], fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)) + (255,))
        R = min(bw, bh) * 0.3
        sx, sy = bx + bw * 0.5, by + bh * 0.58
        cd.ellipse([sx - R, sy - R, sx + R, sy + R], fill=(246, 198, 36, 255))
        _halftone(cd, (sx - R * 0.7, sy - R * 0.7, sx + R * 0.7, sy + R * 0.7), max(6, R / 8), max(1.5, R / 8 * 0.28), (230, 120, 20, 110))
        rnd = random.Random(j * 31 + clip_index * 7 + 1)
        x, base = bx, by + bh * 0.86
        while x < bx + bw:
            ww, hh = bw * (0.06 + rnd.random() * 0.1), bh * (0.08 + rnd.random() * 0.28)
            cd.rectangle([x, base - hh, x + ww, by + bh], fill=mix(col, "#000000", 0.3) + (255,))
            x += ww + rnd.random() * bw * 0.02
        cd.rectangle([bx, base, bx + bw, by + bh], fill=mix(col, "#000000", 0.45) + (255,))
    if hole and not circle:
        ImageDraw.Draw(img).polygon(win, fill=(0, 0, 0, 0))  # เจาะหน้าต่างให้สื่อด้านล่างโผล่
    else:
        _paste_masked(img, content, lambda md: md.polygon(win, fill=255))
    if not circle:  # ฮาล์ฟโทนบาง ๆ ทับภาพ
        dots = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        _halftone(ImageDraw.Draw(dots, "RGBA"), (bx, by, bx + bw, by + bh), max(4, bw / 110), max(1, bw / 110 * 0.2), (0, 0, 0, 34))
        _paste_masked(img, dots, lambda md: md.polygon(win, fill=255))
    d = ImageDraw.Draw(img, "RGBA")
    if L["portrait"] and j % 3 == 2:  # เทปสีเหลืองเฉียง
        ty, k = cy0 + wy0 + (wy1 - wy0) * 0.07, math.tan(-0.07)
        x0, x1, th = cx0 - cw * 0.1, cx0 + cw * 1.15, ch * 0.03
        tape = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(tape).polygon([(x0, ty), (x1, ty + (x1 - x0) * k), (x1, ty + (x1 - x0) * k + th), (x0, ty + th)], fill=(248, 204, 38, 237))
        _paste_masked(img, tape, lambda md: md.rectangle(card, fill=255))
        d = ImageDraw.Draw(img, "RGBA")
    m = min(cw, ch)
    _dot_cluster(d, cx0 + (cw * 0.9 if L["portrait"] else cw * 0.3), cy0 + (wy0 - ch * 0.02 if L["portrait"] else ch * 0.2), m * 0.12, m / 55, (0, 0, 0, 128))
    _dot_cluster(d, cx0 + cw * 0.08, cy0 + L["band"][0] - ch * 0.03, m * 0.1, m / 55, (255, 255, 255, 77))
    for y, color, sd, amp in ((L["band"][0], hex2rgb(col), seed + 11, L["amp"]), (L["band"][1], (246, 198, 36), seed + 13, L["amp"] * 0.8),
                              (L["band"][2], mix(col, "#000000", 0.4), seed + 17, L["amp"] * 0.8)):
        pts = [(cx0 + x, cy0 + yy) for x, yy in _torn(-2, cw + 2, y, amp, random.Random(sd))]
        d.polygon([(cx0 - 2, cy0 + ch + 2)] + pts + [(cx0 + cw + 2, cy0 + ch + 2)], fill=color + (255,))
    if framed:  # นอกการ์ดเป็นดำ (พื้นที่แถบหัว)
        for r in ([0, 0, w, cy0 - 1], [0, cy0 + ch, w, h], [0, 0, cx0 - 1, h], [cx0 + cw, 0, w, h]):
            d.rectangle(r, fill=(0, 0, 0, 255))
    img.save(path)
    return (round(bx), round(by), round(bw), round(bh)), col


def collage_segment(tmp, idx, scene, dur, w, h, fps, clip_index, framed, media):
    out = os.path.join(tmp, f"seg{idx:03d}.mp4")
    ov = os.path.join(tmp, f"ov{idx:03d}.png")
    has_media = bool(media and os.path.exists(media))
    hole = has_media and not is_circle(scene, idx)
    (bx, by, bw, bh), col = collage_overlay(ov, w, h, scene, idx, clip_index, framed, media if has_media else None, hole, tmp)
    frames = max(1, int(round(dur * fps)))
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps)]
    if not hole:
        run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", ov, "-frames:v", str(frames),
             "-vf", "format=yuv420p", *enc, out])
        return out
    bw2, bh2 = bw + bw % 2, bh + bh % 2
    tone = (scene.meta or {}).get("tone", "")
    duo = ""
    if any(k in tone for k in ("ขาวดำ", "ซีเปีย", "เก่า", "duo")):
        r, g, b = (v / 255 for v in mix(col, "#ffffff", 0.5))
        duo = f",hue=s=0,eq=contrast=1.25,colorchannelmixer=rr={r:.3f}:rg=0:rb=0:gr=0:gg={g:.3f}:gb=0:br=0:bg=0:bb={b:.3f}"
    if media.lower().endswith(VIDEO_EXT):
        src = ["-i", media]
        mf = f"[1:v]{fit_video(media, dur)}scale={bw2}:{bh2}:force_original_aspect_ratio=increase,crop={bw2}:{bh2},fps={fps},setsar=1{duo}[m]"
    else:
        src = ["-i", media]
        W2, H2 = int(bw2 * 1.15) // 2 * 2, int(bh2 * 1.15) // 2 * 2
        mf = (f"[1:v]scale={W2}:{H2}:force_original_aspect_ratio=increase,crop={W2}:{H2},"
              f"zoompan=z='1+0.08*on/{frames}':x='(iw-iw/zoom)*{0.5 if idx % 2 else 0.3}':y='(ih-ih/zoom)/2':d={frames}:s={bw2}x{bh2}:fps={fps},setsar=1{duo}[m]")
    fc = f"{mf};[0:v][m]overlay={bx}:{by}:eof_action=repeat[b];[b][2:v]overlay=0:0,format=yuv420p[v]"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}:d={dur:.3f}", *src,
         "-loop", "1", "-framerate", str(fps), "-i", ov, "-filter_complex", fc, "-map", "[v]", "-frames:v", str(frames), *enc, out])
    return out


# ---------- ฉากทั่วไป ----------
def camera_of(scene, idx, style):
    want = CAMERA.get(str((scene.meta or {}).get("camera", "")).strip().lower())
    cycle = CAMERA_CYCLE.get(style, ["push-in", "pan-right", "pull-out", "pan-left"])
    return want or cycle[idx % len(cycle)]


def camera_expr(motion, frames):
    """zoompan แบบนุ่ม (ease in-out) คืน (z, x, y)"""
    e = f"((1-cos(PI*on/{frames}))/2)"
    cx, cy = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    return {"push-in": (f"1+0.15*{e}", cx, cy),
            "pull-out": (f"1.15-0.15*{e}", cx, cy),
            "pan-right": ("1.12", f"(iw-iw/zoom)*{e}", cy),
            "pan-left": ("1.12", f"(iw-iw/zoom)*(1-{e})", cy),
            "tilt-up": ("1.12", cx, f"(ih-ih/zoom)*(1-{e})"),
            "tilt-down": ("1.12", cx, f"(ih-ih/zoom)*{e}"),
            "static": ("1.04", cx, cy)}[motion]


def media_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def fit_video(path, need):
    """ช็อตวิดีโอ (เช่นจาก AI 3–5 วิ) สั้นกว่าฉาก: เล่นช้าลงได้ถึง 1.35 เท่า แล้วค้างเฟรมสุดท้ายไว้ ไม่วนซ้ำ (วนแล้วดูออกว่าเป็นลูป)"""
    vd = media_duration(path)
    if vd <= 0 or vd >= need:
        return ""
    factor = min(1.35, need / vd)
    hold = max(0.0, need - vd * factor) + 0.1
    return f"setpts={factor:.4f}*PTS,tpad=stop_mode=clone:stop_duration={hold:.3f},"


def scene_segment(tmp, idx, scene, dur, w, h, fps, style, seed, media):
    out = os.path.join(tmp, f"seg{idx:03d}.mp4")
    frames = max(1, int(round(dur * fps)))
    if media and os.path.exists(media) and media.lower().endswith(VIDEO_EXT):
        vf = f"{fit_video(media, dur)}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1"
        run(["ffmpeg", "-y", "-v", "error", "-i", media, "-frames:v", str(frames),
             "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out])
        return out
    img = media if media and os.path.exists(media) else os.path.join(tmp, f"bg{idx:03d}.png")
    if img != media:
        make_background(img, w, h, style, seed, scene.desc)
    W, H = int(w * 1.2), int(h * 1.2)
    zoom, xe, ye = camera_expr(camera_of(scene, idx, style), frames)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"zoompan=z='{zoom}':x='{xe}':y='{ye}':d={frames}:s={w}x{h}:fps={fps},setsar=1")
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", img, "-frames:v", str(frames), "-vf", vf,
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out])
    return out


# ---------- เพลงสังเคราะห์ (ปลอดลิขสิทธิ์) ----------
CHORDS = {
    "musicbox": [[60, 64, 67, 71], [57, 60, 64, 67], [53, 57, 60, 64], [55, 59, 62, 67]],
    "lofi":     [[62, 65, 69, 72], [55, 59, 62, 65], [60, 64, 67, 71], [57, 60, 64, 67]],
    "dream":    [[57, 60, 64, 71], [53, 57, 60, 67], [48, 55, 60, 64], [55, 59, 62, 69]],
    "playful":  [[60, 64, 67, 72], [65, 69, 72, 77], [67, 71, 74, 79], [60, 64, 67, 72]],
    "doc":      [[57, 60, 64, 69], [53, 57, 60, 65], [48, 52, 55, 60], [55, 59, 62, 67]],
}


def synth_music(path, seconds, kind="musicbox", sr=22050):
    prog = CHORDS.get(kind, CHORDS["musicbox"])
    bar = {"playful": 2.4, "doc": 2.6}.get(kind, 4.0)
    n = int(seconds * sr)
    buf = [0.0] * n
    f = lambda m: 440 * 2 ** ((m - 69) / 12)  # noqa: E731

    def tone(st, dur, fr, amp, decay, harm=0.3):
        st = int(st)
        for i in range(st, min(n, st + int(sr * dur))):
            t = (i - st) / sr
            buf[i] += amp * math.exp(-t * decay) * (math.sin(2 * math.pi * fr * t) + harm * math.sin(4 * math.pi * fr * t))

    for b in range(int(seconds / bar) + 1):
        chord = prog[b % len(prog)]
        s0, s1 = int(b * bar * sr), min(n, int((b + 1) * bar * sr))
        for m in chord[:3]:  # pad
            fr = f(m - 12)
            for i in range(s0, s1):
                t = (i - s0) / sr
                env = min(1, t / 0.7) * min(1, (bar - t) / 0.7)
                buf[i] += (0.035 if kind == "doc" else 0.045) * env * math.sin(2 * math.pi * fr * i / sr)
        if kind == "doc":  # เปียโนวนซ้ำ + จังหวะหัวใจ
            for k in range(8):
                tone(s0 + k * bar / 8 * sr, 0.5, f(chord[[0, 2, 3, 2, 1, 2, 3, 2][k]] + 12), 0.07, 6.0, 0.25)
            if b >= 2:
                for k in range(4):
                    st = int(s0 + k * bar / 4 * sr)
                    for i in range(st, min(n, st + int(sr * 0.35))):
                        t = (i - st) / sr
                        buf[i] += 0.22 * math.exp(-t * 11) * math.sin(2 * math.pi * (42 + 53 * math.exp(-t * 12)) * t)
            continue
        for k in range(8):
            if kind == "dream" and k % 2:
                continue
            m = chord[(k * 3 + b) % len(chord)] + (12 if kind in ("musicbox", "dream") else 0)
            tone(s0 + k * bar / 8 * sr, 1.6 if kind != "playful" else 0.35, f(m), 0.09 if kind != "dream" else 0.05,
                 3.2 if kind != "playful" else 9)
    rnd = random.Random(1)
    fade_in, fade_out = sr * 1, sr * 2
    with wave.open(path, "wb") as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(sr)
        out = bytearray()
        for i, v in enumerate(buf):
            if kind == "lofi":
                v += (rnd.random() - 0.5) * 0.012
            g = min(1, i / fade_in) * min(1, (n - i) / fade_out)
            out += struct.pack("<h", int(max(-1, min(1, v * g)) * 32000))
        wv.writeframes(bytes(out))


# ---------- เสียงประกอบ (SFX) ----------
def sfx_kind(text):
    if "ลม" in text:
        return "wind"
    if "ฝน" in text:
        return "rain"
    if any(k in text for k in ("วูบ", "ปลิว", "หวือ")):
        return "whoosh"
    return "chime"


def synth_sfx(kind, sr=22050):
    """เสียงประกอบสังเคราะห์ (ตรงกับในเว็บ) ใช้เมื่อไม่มีไฟล์จาก Higgsfield / AudioGen / คลังเสียงของผู้ใช้"""
    rnd = random.Random(7)
    out = []
    if kind == "chime":
        n = int(1.8 * sr)
        out = [0.0] * n
        for j, f in enumerate((1568, 2093, 2637)):
            st = int(j * 0.09 * sr)
            for i in range(st, n):
                t = (i - st) / sr
                out[i] += 0.22 * math.exp(-t * 3.2) * math.sin(2 * math.pi * f * t)
    elif kind == "pop":
        n = int(0.12 * sr)
        ph = 0.0
        for i in range(n):
            t = i / sr
            ph += 2 * math.pi * (300 + 600 * math.exp(-t * 30)) / sr
            out.append(0.5 * math.exp(-t * 40) * math.sin(ph))
    else:  # whoosh / paper / wind / rain = noise ผ่านตัวกรองอย่างง่าย
        dur = {"paper": 0.35, "whoosh": 0.7}.get(kind, 3.0)
        n = int(dur * sr)
        lp = hp = 0.0
        for i in range(n):
            t = i / n
            x = rnd.uniform(-1, 1)
            a = {"paper": 0.6 + 0.35 * t, "whoosh": 0.05 + 0.5 * t, "wind": 0.04, "rain": 0.9}[kind]
            lp += a * (x - lp)
            hp = lp - hp * 0.0 if kind != "rain" else x - lp
            env = min(1.0, t / 0.35) * min(1.0, (1 - t) / 0.65) if kind in ("paper", "whoosh") else min(1.0, t / 0.2) * min(1.0, (1 - t) / 0.3)
            if kind == "wind":
                env *= 0.6 + 0.4 * math.sin(2 * math.pi * 0.7 * i / sr)
            if kind == "rain" and rnd.random() < 0.004:
                hp += rnd.uniform(-1, 1) * 2
            out.append({"paper": 0.7, "whoosh": 0.6, "wind": 0.9, "rain": 0.35}[kind] * env * (hp if kind == "rain" else lp))
    return out


def _decode_mono(path, sr):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], capture_output=True)
    if r.returncode:
        return None
    vals = struct.unpack("<%dh" % (len(r.stdout) // 2), r.stdout[:len(r.stdout) // 2 * 2])
    return [v / 32768.0 for v in vals]


def build_sfx_track(path, total, cues, files=None, sr=22050):
    """รวมเสียงประกอบทุกจุด (เวลา, ชนิด) เป็นไฟล์เดียว: ใช้ไฟล์จริงจาก files[ชนิด] ถ้ามี ไม่งั้นสังเคราะห์"""
    buf = [0.0] * int((total + 3) * sr)
    cache = {}
    for t, kind in cues:
        if kind not in cache:
            src = (files or {}).get(kind)
            cache[kind] = (_decode_mono(src, sr) if src and os.path.exists(src) else None) or synth_sfx(kind, sr)
        snd, st = cache[kind], int(max(0.0, t) * sr)
        for i, v in enumerate(snd):
            if st + i >= len(buf):
                break
            buf[st + i] += v
    with wave.open(path, "wb") as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(sr)
        wv.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32000)) for v in buf))


# ---------- ประกอบคลิป ----------
def slug(s):
    s = re.sub(r"[^\w฀-๿]+", "-", s).strip("-")
    return s[:30] or "clip"


def ff_filter_path(p):
    """path สำหรับใส่ในตัวเลือก filter ของ ffmpeg (เช่น ass=) ให้ใช้ได้ทั้ง Windows และ Linux:
    ใช้ / แทน \\ และ escape ':' ของชื่อไดรฟ์ (D:) กับ ' ไม่งั้น ffmpeg อ่าน D: เป็นตัวคั่นตัวเลือก"""
    p = os.path.abspath(p).replace("\\", "/")
    # ระดับ 2 (ตัวเลือก filter): \\: และ \\' ; ระดับ 1 (อยู่ใน '...'): ปิด quote แล้วใส่ \\' ก่อนเปิดใหม่
    return p.replace(":", "\\:").replace("'", "\\'\\''")


def concat(segs, out):
    lst = out + ".txt"
    with open(lst, "w", encoding="utf-8") as fh:
        fh.write("".join(f"file '{os.path.abspath(p).replace(os.sep, '/')}'\n" for p in segs))
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])


def render_clip(project, ci, clip, fmt, outdir, fps, font):
    w, h = SCALE[fmt]
    style = clip.get("visualStyle") or project.get("visualStyle", "pastel3d")
    collage = style == "collage"
    framed = bool(project.get("banner", collage))
    mode = project.get("captionMode", "auto")
    voice = clip.get("voice") if clip.get("voice") and os.path.exists(clip["voice"]) else None
    vdur = 0.0
    if voice:
        vdur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", voice],
                                    capture_output=True, text=True).stdout.strip() or 0)
    scenes, chunks, total = bs.build(clip["script"], project.get("speed", "slow"), clip.get("timings"), vdur + 0.5 if voice else 0)
    meta = clip.get("scenes") or []
    n_clips = len(project.get("clips", [])) or 1
    header = (project.get("series") or project.get("title", ""), clip.get("title", ""),
              f"ตอนที่ {ci + 1}/{n_clips} · {clip.get('angle', '')}".rstrip(" ·"))
    base = os.path.join(outdir, f"{ci + 1}_{slug(clip.get('title', 'clip'))}_{fmt}")
    with open(base + ".srt", "w", encoding="utf-8") as fh:
        fh.write(bs.to_srt(chunks))
    ass_path = base + ".ass"
    with open(ass_path, "w", encoding="utf-8") as fh:
        fh.write(bs.to_ass(chunks, fmt, font, scenes, style, mode, framed if collage else False, header, ci))

    def media_of(j):
        return meta[j].get("media") if j < len(meta) and isinstance(meta[j], dict) else None

    with tempfile.TemporaryDirectory() as tmp:
        video = os.path.join(tmp, "video.mp4")
        # ทรานซิชันเข้าแต่ละฉาก (j ≥ 1): ตามบรรทัดฉาก "เปลี่ยน:" หรือวนตามสไตล์; เวลาซ้อนอยู่กึ่งกลางจุดเปลี่ยนฉาก (ซับไม่เลื่อน)
        cycle = XFADE_CYCLE.get(style, ["fade"])
        kinds, lens = [None], [0.0]
        for j in range(1, len(scenes)):
            want = XFADE.get(str((scenes[j].meta or {}).get("transition", "")).strip().lower())
            kind = want or cycle[(j - 1) % len(cycle)]
            short = min(scenes[j - 1].end - scenes[j - 1].start, scenes[j].end - scenes[j].start)
            D = min(XFADE_LEN.get(kind, 0.4), short * 0.4)
            if kind == "cut" or D < 2.0 / fps:
                kind, D = "fade", 1.0 / fps  # ตัดตรง (ซ้อน 1 เฟรม)
            kinds.append(kind)
            lens.append(D)
        segs = []
        for j, s in enumerate(scenes):
            dur = (s.end - s.start) + (lens[j] / 2 if j > 0 else 0) + (lens[j + 1] / 2 if j + 1 < len(scenes) else 0)
            if collage:
                segs.append(collage_segment(tmp, j, s, dur, w, h, fps, ci, framed, media_of(j)))
            else:
                segs.append(scene_segment(tmp, j, s, max(0.2, dur), w, h, fps, style, ci * 100 + j, media_of(j)))
        if len(segs) == 1:
            concat(segs, video)
        else:
            ins = sum((["-i", p] for p in segs), [])
            fc, prev = [], "[0:v]"
            for j in range(1, len(segs)):
                fc.append(f"{prev}[{j}:v]xfade=transition={kinds[j]}:duration={lens[j]:.3f}:"
                          f"offset={max(0.0, scenes[j].start - lens[j] / 2):.3f}[x{j}]")
                prev = f"[x{j}]"
            run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(fc), "-map", prev,
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", video])
        music = project.get("musicFile")
        if not (music and os.path.exists(music)) and project.get("music", "musicbox") != "none":
            music = os.path.join(tmp, "music.wav")
            synth_music(music, total, project.get("music", "doc" if collage else "musicbox"))
        inputs = ["-i", video]
        tracks, n = [], 1  # (filter, label)
        if voice:
            inputs += ["-i", voice]
            tracks.append((f"[{n}:a]aresample=44100", "[v]"))  # เสียงพากย์เริ่มที่ t=0 (timings วัดจากต้นไฟล์)
            n += 1
        if music and os.path.exists(music):
            inputs += ["-i", music]
            vol = 0.18 if voice else 0.55  # เพลงต่ำกว่าเสียงพูด ~-15 dB เมื่อมีพากย์
            tracks.append((f"[{n}:a]aresample=44100,volume={vol},afade=t=out:st={max(0, total - 2):.2f}:d=2", "[m]"))
            n += 1
        cues = [(c.start, sfx_kind(x)) for c in chunks for x in c.sfx]
        cues += [(s.start, "paper" if collage else "whoosh") for s in scenes[1:]]
        if cues and project.get("sfx", True):
            sfx_path = os.path.join(tmp, "sfx.wav")
            build_sfx_track(sfx_path, total, cues, project.get("sfxFiles"))
            inputs += ["-i", sfx_path]
            tracks.append((f"[{n}:a]aresample=44100,volume={0.55 if voice else 0.8}", "[x]"))
            n += 1
        sub = f"ass='{ff_filter_path(ass_path)}'" + (f":fontsdir='{ff_filter_path(bs.FONTS_DIR)}'" if os.path.isdir(bs.FONTS_DIR) else "")
        grade = GRADES.get(project.get("grade") or GRADE_DEFAULT.get(style, "none"), "")
        bars = ""
        if style == "cinematic" and fmt == "16x9" and project.get("letterbox", True):  # แถบดำแบบจอภาพยนตร์ 2.39:1
            bh = max(0, round((h - w / 2.39) / 2))
            bars = f"drawbox=x=0:y=0:w=iw:h={bh}:color=black:t=fill,drawbox=x=0:y=ih-{bh}:w=iw:h={bh}:color=black:t=fill"
        fc = "[0:v]" + ",".join(x for x in (grade, bars, sub) if x) + "[vo]"
        loud = project.get("loudness", -14)  # ความดังมาตรฐานโซเชียล (LUFS) ใส่ null เพื่อปิด · วัดแล้วปรับทีหลัง (2 รอบ แม่นกว่า)
        if tracks:
            if len(tracks) == 1:
                fc += f";{tracks[0][0]}[ao]"
            else:
                fc += ";" + ";".join(f + lb for f, lb in tracks)
                fc += ";" + "".join(lb for _, lb in tracks) + f"amix=inputs={len(tracks)}:normalize=0:duration=longest[ao]"
            maps = ["-map", "[vo]", "-map", "[ao]"]
        else:
            inputs += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            maps = ["-map", "[vo]", "-map", f"{n}:a"]
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, *maps, "-t", f"{total:.2f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", base + ".mp4"])
        if tracks and isinstance(loud, (int, float)):
            normalize_loudness(base + ".mp4", loud)
    return base + ".mp4", total, bs.warnings(chunks)


def normalize_loudness(path, target=-14.0, tp=-1.5, lra=11):
    """ปรับความดังทั้งคลิปให้ได้ target LUFS แบบ 2 รอบ (วัด → ปรับ) แตะเฉพาะเสียง ภาพคัดลอกตรง ๆ"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af",
                        f"loudnorm=I={target}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    err = r.stderr
    try:
        m = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
        if float(m["input_i"]) < -70:  # เงียบทั้งคลิป ไม่ต้องปรับ
            return
    except (ValueError, KeyError):
        return
    af = (f"loudnorm=I={target}:TP={tp}:LRA={lra}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,"
          f"aresample=44100")
    tmp = path + ".loud.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", path, "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", af,
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", tmp])
    os.replace(tmp, path)


def main(argv=None):
    bs.utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--out", default="out")
    ap.add_argument("--formats", help="เช่น 9x16,16x9 (ค่าเริ่มต้นจาก project.formats)")
    ap.add_argument("--clips", help="เลขคลิป เช่น 1,3")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--font", default="Kanit")
    a = ap.parse_args(argv)
    with open(a.project, encoding="utf-8") as fh:
        project = json.load(fh)
    pdir = os.path.dirname(os.path.abspath(a.project))
    for c in project.get("clips", []):  # path สัมพัทธ์เทียบกับไฟล์ project
        if c.get("voice") and not os.path.isabs(c["voice"]):
            c["voice"] = os.path.join(pdir, c["voice"])
        for s in c.get("scenes") or []:
            if isinstance(s, dict) and s.get("media") and not os.path.isabs(s["media"]):
                s["media"] = os.path.join(pdir, s["media"])
    if project.get("musicFile") and not os.path.isabs(project["musicFile"]):
        project["musicFile"] = os.path.join(pdir, project["musicFile"])
    for kind, path in list((project.get("sfxFiles") or {}).items()):  # {"chime": "sfx/chime.wav", ...}
        if path and not os.path.isabs(path):
            project["sfxFiles"][kind] = os.path.join(pdir, path)
    formats = (a.formats or ",".join(project.get("formats", ["9x16"]))).split(",")
    pick = {int(x) - 1 for x in a.clips.split(",")} if a.clips else None
    os.makedirs(a.out, exist_ok=True)
    font = bs.pick_font(a.font)
    for ci, clip in enumerate(project.get("clips", [])):
        if pick is not None and ci not in pick:
            continue
        if not clip.get("script", "").strip():
            print(f"ข้ามคลิป {ci + 1}: ยังไม่มีสคริปต์")
            continue
        for fmt in formats:
            path, total, warn = render_clip(project, ci, clip, fmt.strip(), a.out, a.fps, font)
            print(f"✔ {path}  ({total:.1f} วิ, ฟอนต์ {font})")
            for wmsg in warn:
                print("  ⚠", wmsg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
