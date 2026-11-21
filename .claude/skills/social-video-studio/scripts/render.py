#!/usr/bin/env python3
"""เรนเดอร์คลิปจาก project.json (ส่งออกจากเว็บ video-studio-web หรือที่ agent เขียน) เป็น MP4 ด้วย ffmpeg

ใช้:  python3 render.py project.json --out out/ [--formats 9x16,16x9] [--clips 1,3] [--fps 30]

ต่อคลิปจะได้  out/<n>_<slug>_<format>.mp4  + .srt + .ass
- สไตล์ collage (ค่าเริ่มต้นแบบคลิปตัวอย่าง): พื้นสีต่อบท ฮาล์ฟโทน หน้าต่างภาพขอบกระดาษฉีก ป้ายปี หัวข้อ
  สติกเกอร์วงกลม แถบซับกระดาษฉีก ซับคำต่อคำ และทรานซิชันสไลด์ระหว่างฉาก
- สไตล์อื่น: พื้นหลังสังเคราะห์ตาม visualStyle + Ken Burns
- ภาพ: scenes[j].media (รูป/วิดีโอ) ไม่มีก็สร้างภาพแทนที่ให้
- เสียง: clips[i].voice (ไฟล์พากย์ เริ่มที่วินาที 0) + project.musicFile หรือเพลงสังเคราะห์ตาม project.music
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
}
SCALE = bs.FORMATS
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")


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
        src = ["-stream_loop", "-1", "-i", media]
        mf = f"[1:v]scale={bw2}:{bh2}:force_original_aspect_ratio=increase,crop={bw2}:{bh2},fps={fps},setsar=1{duo}[m]"
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
def scene_segment(tmp, idx, scene, dur, w, h, fps, style, seed, media):
    out = os.path.join(tmp, f"seg{idx:03d}.mp4")
    frames = max(1, int(round(dur * fps)))
    motion = ["zoom-in", "pan-right", "zoom-out", "pan-left"][idx % 4]
    if media and os.path.exists(media) and media.lower().endswith(VIDEO_EXT):
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1"
        run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", media, "-frames:v", str(frames),
             "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out])
        return out
    img = media if media and os.path.exists(media) else os.path.join(tmp, f"bg{idx:03d}.png")
    if img != media:
        make_background(img, w, h, style, seed, scene.desc)
    W, H = int(w * 1.2), int(h * 1.2)
    zoom = {"zoom-in": f"1+0.12*on/{frames}", "zoom-out": f"1.12-0.12*on/{frames}"}.get(motion, "1.08")
    if motion == "pan-right":
        xe, ye = f"(iw-iw/zoom)*on/{frames}", "(ih-ih/zoom)/2"
    elif motion == "pan-left":
        xe, ye = f"(iw-iw/zoom)*(1-on/{frames})", "(ih-ih/zoom)/2"
    else:
        xe, ye = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
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


# ---------- ประกอบคลิป ----------
def slug(s):
    s = re.sub(r"[^\w฀-๿]+", "-", s).strip("-")
    return s[:30] or "clip"


def concat(segs, out):
    lst = out + ".txt"
    with open(lst, "w") as fh:
        fh.write("".join(f"file '{p}'\n" for p in segs))
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
        if collage:
            D = min(0.4, min(s.end - s.start for s in scenes) * 0.4) if len(scenes) > 1 else 0.0
            segs = []
            for j, s in enumerate(scenes):  # เผื่อเวลาซ้อน ให้ทรานซิชันอยู่กึ่งกลางจุดเปลี่ยนฉาก (ซับไม่เลื่อน)
                dur = (s.end - s.start) + (D / 2 if j > 0 else 0) + (D / 2 if j + 1 < len(scenes) else 0)
                segs.append(collage_segment(tmp, j, s, dur, w, h, fps, ci, framed, media_of(j)))
            if len(segs) == 1 or D <= 0:
                concat(segs, video)
            else:
                ins = sum((["-i", p] for p in segs), [])
                fc, prev = [], "[0:v]"
                for j in range(1, len(segs)):
                    fc.append(f"{prev}[{j}:v]xfade=transition=slideleft:duration={D:.3f}:offset={scenes[j].start - D / 2:.3f}[x{j}]")
                    prev = f"[x{j}]"
                run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(fc), "-map", prev,
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", video])
        else:
            concat([scene_segment(tmp, j, s, max(0.2, s.end - s.start), w, h, fps, style, ci * 100 + j, media_of(j))
                    for j, s in enumerate(scenes)], video)
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
        sub = f"ass='{ass_path}'" + (f":fontsdir='{bs.FONTS_DIR}'" if os.path.isdir(bs.FONTS_DIR) else "")
        fc = f"[0:v]{sub}[vo]"
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
    return base + ".mp4", total, bs.warnings(chunks)


def main(argv=None):
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
