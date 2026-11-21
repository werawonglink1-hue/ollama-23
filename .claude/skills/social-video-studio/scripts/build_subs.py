#!/usr/bin/env python3
"""แปลงสคริปต์พูดภาษาไทย (รูปแบบใน references/script-rules.md) เป็นท่อนซับที่ตั้งเวลาแล้ว + SRT/ASS

ใช้:  python3 build_subs.py script.txt [--speed slow|normal|fast] [--srt out.srt] [--ass out.ass] [--json out.json]
                                       [--format 9x16|16x9|1x1|4x5] [--style collage] [--caption auto|word|phrase]
                                       [--framed] [--series "ชื่อซีรีส์"] [--title "ชื่อคลิป"] [--font Kanit]

--caption word  = ซับคำต่อคำแบบคาราโอเกะ (คำใหม่เด้งสีเหลือง) แบบคลิปตัวอย่างสารคดี
--caption phrase = ซับทีละวลี + ไฮไลต์ *คำ* แบบคลิปเล่าเรื่องละมุน
--style collage  = วางป้ายปี หัวข้อ เครดิต และแถบหัว (ถ้า --framed) ตำแหน่งเดียวกับเว็บ
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict

PAUSE = {"": 0.30, "/": 0.35, "//": 0.80, "///": 1.40}
CPS = {"slow": 7.5, "normal": 9.0, "fast": 10.5}  # ตัวอักษรฐานต่อวินาที
PAUSE_SCALE = {"slow": 1.0, "normal": 0.75, "fast": 0.55}  # ช้า = เว้นเต็มที่ (ละมุน), ปกติ = กระชับแบบสารคดี
MIN_DUR_BY = {"slow": 1.0, "normal": 0.85, "fast": 0.7}
MIN_DUR = 1.0
MAX_BASE = 20          # ยาวกว่านี้จะพยายามแบ่งที่ช่องว่าง
TOO_FAST_CPS = 12.0
LEAD_IN = 0.4
TAIL = 1.6
EMOTION_FACTOR = {
    "ช้าลง": 1.2, "กระซิบ": 1.15, "เศร้า": 1.15, "ลุ้น": 1.1,
    "ตื่นเต้น": 0.92, "ขำ": 0.95, "ยิ้ม": 1.0,
}
FORMATS = {"9x16": (1080, 1920), "16x9": (1920, 1080), "1x1": (1080, 1080), "4x5": (1080, 1350)}
SUB_Y = {"9x16": 0.68, "16x9": 0.84, "1x1": 0.80, "4x5": 0.78}  # ตำแหน่งกึ่งกลางซับเทียบความสูง
KEYMAP = {"ป้าย": "badge", "ปี": "badge", "หัวข้อ": "title", "ภาพ": "layout", "เลย์เอาต์": "layout",
          "เครดิต": "credit", "สี": "color", "โทน": "tone", "กล้อง": "camera", "เปลี่ยน": "transition",
          "ทรานซิชัน": "transition", "ซ้ำ": "repeat"}
COLLAGE = ["#1f2a5c", "#f2b21b", "#6cb4e4", "#b3123a", "#1aa391", "#2b4fd6", "#e94b6a"]
COLOR_TH = {"น้ำเงิน": "#1f2a5c", "กรมท่า": "#1f2a5c", "เหลือง": "#f2b21b", "ฟ้า": "#6cb4e4", "แดง": "#b3123a",
            "เขียว": "#1aa391", "น้ำเงินสด": "#2b4fd6", "ชมพู": "#e94b6a", "ดำ": "#16141c"}
HI_LIME, HI_YELLOW, HI_GOLD = "#e6ff3d", "#ffd21f", "#ffc96b"
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts")

# สระบน/ล่าง/วรรณยุกต์ ไม่นับเป็นตัวอักษรฐาน
_COMBINING = set("ัิีึืฺุู็่้๊๋์ํ๎")


def base_len(s: str) -> int:
    s = s.replace("*", "")
    return sum(1 for ch in s if ch not in _COMBINING and not ch.isspace() and ch not in "\"“”'.,!?…")


@dataclass
class Chunk:
    text: str                 # มี *ไฮไลต์*
    pause: str = ""           # เครื่องหมายเว้นหลังท่อน
    emotion: str = ""
    speaker: str = ""         # บทพูดของตัวละคร (บรรทัด "@ชื่อ: ...") ว่าง = ผู้บรรยาย
    sfx: list = field(default_factory=list)
    scene: int = 0
    start: float = 0.0
    end: float = 0.0          # จบเสียงพูดของท่อน
    show_end: float = 0.0     # ซับค้างจอถึง

    @property
    def plain(self) -> str:
        return self.text.replace("*", "")


@dataclass
class Scene:
    desc: str
    meta: dict = field(default_factory=dict)   # badge / title / layout / credit / color / tone
    first_chunk: int = 0
    start: float = 0.0
    end: float = 0.0


def _split_long(text: str) -> list[str]:
    if base_len(text) <= MAX_BASE or " " not in text.strip():
        return [text]
    words = text.split()
    best, best_diff = 1, 10**9
    for i in range(1, len(words)):
        diff = abs(base_len(" ".join(words[:i])) - base_len(" ".join(words[i:])))
        if diff < best_diff:
            best, best_diff = i, diff
    return _split_long(" ".join(words[:best])) + _split_long(" ".join(words[best:]))


def parse_scene(body: str) -> Scene:
    parts = [p.strip() for p in body.split("|")]
    meta = {}
    for p in parts[1:]:
        m = re.match(r"^([^:：]+)[:：]\s*(.*)$", p)
        if m:
            meta[KEYMAP.get(m.group(1).strip(), m.group(1).strip())] = m.group(2).strip()
    return Scene(desc=parts[0], meta=meta)


def parse_script(script: str) -> tuple[list[Scene], list[Chunk]]:
    scenes: list[Scene] = []
    chunks: list[Chunk] = []
    pending_sfx: list[str] = []
    hl_open = False  # ไฮไลต์ *...* ที่คร่อมเครื่องหมายเว้น ให้ปิด/เปิดใหม่ในแต่ละท่อน
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.fullmatch(r"\[\s*ฉาก\s*[:：]\s*(.*?)\s*\]", line)
        if m:
            sc = parse_scene(m.group(1))
            sc.first_chunk = len(chunks)
            scenes.append(sc)
            continue
        sp = re.match(r"^@\s*([^:：]{1,30}?)\s*[:：]\s*(.*)$", line)  # บทพูดตัวละคร: @แม่: ลูกจ๋า / กลับบ้านเถอะ //
        speaker = sp.group(1).strip() if sp else ""
        if sp:
            line = sp.group(2)
        for s in re.findall(r"\{\s*เสียง\s*[:：]\s*(.*?)\s*\}", line):
            pending_sfx.append(s)
        line = re.sub(r"\{.*?\}", " ", line)
        parts = re.split(r"(/{1,3})", line)
        emotion = ""
        i = 0
        while i < len(parts):
            seg = parts[i]
            mark = parts[i + 1] if i + 1 < len(parts) else ""
            i += 2
            emos = re.findall(r"\(([^)]*)\)", seg)
            if emos:
                emotion = emos[-1].strip()
            seg = re.sub(r"\([^)]*\)", " ", seg)
            seg = re.sub(r"\s+", " ", seg).strip()
            if not seg:
                if mark and chunks and len(mark) > len(chunks[-1].pause):
                    chunks[-1].pause = mark
                continue
            pieces = []
            for p in _split_long(seg):
                if hl_open:
                    p = "*" + p
                hl_open = p.count("*") % 2 == 1
                pieces.append(p + "*" if hl_open else p)
            for k, p in enumerate(pieces):
                chunks.append(Chunk(text=p, pause=mark if k == len(pieces) - 1 else "/",
                                    emotion=emotion, sfx=pending_sfx, scene=max(len(scenes) - 1, 0), speaker=speaker))
                pending_sfx = []
        if chunks and chunks[-1].pause == "":
            chunks[-1].pause = "/"
    if not scenes:
        scenes.append(Scene(desc="", first_chunk=0))
    return scenes, chunks


def time_chunks(scenes, chunks, speed="slow", timings=None, min_total=0.0):
    cps = CPS.get(speed, CPS["slow"])
    pscale, min_dur = PAUSE_SCALE.get(speed, 1.0), MIN_DUR_BY.get(speed, MIN_DUR)
    t = LEAD_IN
    for idx, c in enumerate(chunks):
        tm = timings[idx] if timings and idx < len(timings) else None
        if tm is not None:
            c.start = float(tm["start"] if isinstance(tm, dict) else tm)
        else:
            c.start = t
        c.end = c.start + max(min_dur, base_len(c.text) / cps * EMOTION_FACTOR.get(c.emotion, 1.0))
        if isinstance(tm, dict) and tm.get("end"):
            c.end = float(tm["end"])
        t = c.end + PAUSE[c.pause] * pscale
    if timings:  # เวลาจากการแตะซิงก์: อย่าให้ท่อนทับท่อนถัดไป
        for idx, c in enumerate(chunks[:-1]):
            n = chunks[idx + 1]
            if c.end > n.start - 0.05:
                c.end = max(c.start + 0.3, n.start - 0.05)
    for idx, c in enumerate(chunks):
        nxt = chunks[idx + 1].start if idx + 1 < len(chunks) else c.end + 0.6
        # เว้นสั้น: ค้างซับจนท่อนถัดไป; เว้นกลาง/ยาว: ซับหายให้ภาพพูด
        c.show_end = min(nxt, c.end + 0.25) if len(c.pause) >= 2 else nxt
    total = max((chunks[-1].end if chunks else 0) + TAIL, min_total)
    for j, s in enumerate(scenes):
        s.start = 0.0 if j == 0 else (chunks[s.first_chunk].start - 0.2 if s.first_chunk < len(chunks) else total)
    for j, s in enumerate(scenes):
        s.end = scenes[j + 1].start if j + 1 < len(scenes) else total
    return total


def warnings(chunks):
    out = []
    for i, c in enumerate(chunks, 1):
        n = base_len(c.text)
        dur = c.show_end - c.start
        if dur > 0 and n / dur > TOO_FAST_CPS:
            out.append(f"TOO FAST  ท่อน {i}: '{c.plain}' {n / dur:.1f} ตัว/วิ")
        if n > MAX_BASE:
            out.append(f"LONG      ท่อน {i}: '{c.plain}' {n} ตัวอักษร ใส่ / เพิ่ม")
    return out


# ---------------- ตัดคำสำหรับซับคำต่อคำ ----------------
_NODE_SEG = ('const s=new Intl.Segmenter("th",{granularity:"word"});let d="";'
             'process.stdin.on("data",c=>d+=c).on("end",()=>{process.stdout.write('
             'JSON.stringify(JSON.parse(d).map(t=>[...s.segment(t)].map(x=>x.segment))))})')


def _segment_many(texts):
    """ตัดคำภาษาไทยด้วย ICU ผ่าน Node (Intl.Segmenter) ถ้ามี ไม่งั้นคืน None"""
    node = shutil.which("node")
    if not node or not texts:
        return None
    try:
        r = subprocess.run([node, "-e", _NODE_SEG], input=json.dumps(texts), capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def karaoke_tokens(chunks):
    """คืนรายการ token ต่อท่อน: {s, hi, space, w} — ใช้ช่องว่างที่ผู้เขียนใส่ก่อน แล้วค่อยตัดคำด้วย ICU
    (รวมชิ้นสั้น ≤2 ตัวอักษรเข้ากับคำก่อนหน้า กันตัดผิดแบบ 'หมอบ|อก')"""
    raw = []
    need = []
    for c in chunks:
        toks = []
        hi = False
        for part in re.split(r"(\*)", c.text):
            if part == "*":
                hi = not hi
                continue
            for piece in re.split(r"(\s+)", part):
                if not piece:
                    continue
                if piece.isspace():
                    toks.append({"s": " ", "space": True, "hi": hi})
                else:
                    toks.append({"s": piece, "space": False, "hi": hi, "seg": base_len(piece) > 4})
                    if base_len(piece) > 4:
                        need.append(piece)
        raw.append(toks)
    seg = _segment_many(sorted(set(need))) if need else None
    segmap = dict(zip(sorted(set(need)), seg)) if seg else {}
    out = []
    for toks in raw:
        res = []
        for t in toks:
            if t["space"]:
                res.append(t)
                continue
            parts = segmap.get(t["s"], [t["s"]]) if t.get("seg") else [t["s"]]
            merged = []
            for p in parts:
                if merged and (base_len(p) <= 2 or base_len(merged[-1]) <= 1):
                    merged[-1] += p
                else:
                    merged.append(p)
            res += [{"s": p, "space": False, "hi": t["hi"], "w": max(1, base_len(p))} for p in merged]
        out.append(res)
    return out


# ---------------- เลย์เอาต์ (ตรงกับเว็บ video-studio-web) ----------------
def card_rect(w, h, framed):
    if not framed:
        return (0, 0, w, h)
    return (w * 0.165, h * 0.165, w * 0.67, h * 0.69) if h > w else (w * 0.03, h * 0.17, w * 0.94, h * 0.8)


def collage_layout(cw, ch):
    if cw / ch < 0.9:
        return {"portrait": True, "amp": ch * 0.007,
                "win": (0, cw, ch * 0.285, ch * 0.83), "band": (ch * 0.815, ch * 0.905, ch * 0.93),
                "cap": (ch * 0.86, cw * 0.08, cw * 0.92),
                "badge": (cw * 0.06, ch * 0.148, cw * 0.055), "title": (cw / 2, ch * 0.243, cw * 0.075, cw * 0.92),
                "credit": (cw * 0.97, ch * 0.2, max(9, cw * 0.017))}
    return {"portrait": False, "amp": ch * 0.01,
            "win": (cw * 0.36, cw, 0, ch * 0.8), "band": (ch * 0.78, ch * 0.9, ch * 0.94),
            "cap": (ch * 0.84, min(cw * 0.042, ch * 0.075), cw * 0.9),
            "badge": (cw * 0.035, ch * 0.1, ch * 0.05), "title": (cw * 0.18, ch * 0.42, ch * 0.07, cw * 0.31),
            "credit": (cw * 0.985, ch * 0.04, max(9, ch * 0.022))}


def scene_color(scene, j, clip_index=0):
    c = (scene.meta or {}).get("color") if scene else None
    if c:
        return COLOR_TH.get(c) or (c if re.fullmatch(r"#[0-9a-fA-F]{6}", c) else COLLAGE[0])
    return COLLAGE[(j * 3 + clip_index * 2) % len(COLLAGE)]


_FONT_CACHE = {}


def text_width(text, size):
    """ความกว้างข้อความโดยประมาณ (ใช้ฟอนต์ Kanit ที่แนบมาถ้ามี)"""
    try:
        from PIL import ImageFont
        path = os.path.join(FONTS_DIR, "Kanit-Bold.ttf")
        key = int(size)
        if key not in _FONT_CACHE:
            _FONT_CACHE[key] = ImageFont.truetype(path, max(1, key))
        return _FONT_CACHE[key].getlength(text)
    except Exception:
        return base_len(text) * size * 0.58


def fit_size(text, size, max_w):
    w = text_width(text, size)
    return size * max_w / w if w > max_w else size


def _font_file(font):
    if font == "Kanit" and os.path.exists(os.path.join(FONTS_DIR, "Kanit-Bold.ttf")):
        return os.path.join(FONTS_DIR, "Kanit-Bold.ttf")
    if shutil.which("fc-match"):
        r = subprocess.run(["fc-match", "-f", "%{file}", f"{font}:bold"], capture_output=True, text=True)
        return r.stdout.strip() or None
    return None


def font_scale(font="Kanit"):
    """libass วัดขนาดฟอนต์จาก winAscent+winDescent ส่วนเว็บ (canvas) ใช้ em
    คืนตัวคูณให้ \\fs ใน ASS ได้ตัวอักษรขนาดเท่ากับในเว็บ (Kanit ≈ 1.58)"""
    import struct
    path = _font_file(font)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        num = struct.unpack(">H", data[4:6])[0]
        tables = {}
        for i in range(num):
            tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            tables[tag.decode("latin1")] = off
        upm = struct.unpack(">H", data[tables["head"] + 18:tables["head"] + 20])[0]
        wa, wd = struct.unpack(">HH", data[tables["OS/2"] + 74:tables["OS/2"] + 78])
        return (wa + wd) / upm if upm else 1.0
    except (OSError, KeyError, TypeError, struct.error):
        return 1.0


def pick_font(preferred="Kanit"):
    if preferred == "Kanit" and os.path.exists(os.path.join(FONTS_DIR, "Kanit-Bold.ttf")):
        return "Kanit"  # ฟอนต์ที่แนบมากับ skill (OFL)
    if shutil.which("fc-list"):
        fams = subprocess.run(["fc-list", ":lang=th", "family"], capture_output=True, text=True).stdout
        names = {n.strip() for line in fams.splitlines() for n in line.split(",")}
        for f in (preferred, "Kanit", "Prompt", "Sarabun", "Noto Sans Thai", "Loma"):
            if f in names:
                return f
    return preferred


# ---------------- ส่งออก ----------------
def _ts_srt(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _ts_ass(t):
    cs = int(round(max(0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def to_srt(chunks):
    return "\n".join(f"{i}\n{_ts_srt(c.start)} --> {_ts_srt(c.show_end)}\n{c.plain}\n"
                     for i, c in enumerate(chunks, 1))


def ass_color(hexc, alpha=0):
    hexc = hexc.lstrip("#")
    r, g, b = int(hexc[0:2], 16), int(hexc[2:4], 16), int(hexc[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def ass_ovc(hexc):
    """สีสำหรับ override tag เช่น \\1c&HBBGGRR&"""
    hexc = hexc.lstrip("#")
    return f"&H{hexc[4:6]}{hexc[2:4]}{hexc[0:2]}&".upper().replace("&H", "&H", 1)


def _esc(s):
    return s.replace("{", "(").replace("}", ")").replace("\\", "/")


def caption_mode(style, mode):
    if mode in ("word", "phrase"):
        return mode
    return "word" if style in ("collage", "kinetic", "cinematic") else "phrase"


def to_ass(chunks, fmt="9x16", font="Kanit", scenes=None, style="pastel3d", mode="auto", framed=None,
           header=None, clip_index=0):
    """ซับ ASS ตามตำแหน่งเดียวกับเว็บ; สไตล์ collage จะเพิ่มแถบหัว ป้ายปี หัวข้อ และเครดิตด้วย"""
    w, h = FORMATS[fmt]
    collage = style == "collage"
    framed = collage if framed is None else framed
    mode = caption_mode(style, mode)
    hi = HI_YELLOW if collage else HI_GOLD if style == "cinematic" else HI_LIME
    if collage:
        cx0, cy0, cw, ch = card_rect(w, h, framed)
        L = collage_layout(cw, ch)
        cap_x, cap_y = cx0 + cw / 2, cy0 + L["cap"][0]
        cap_size, cap_w = L["cap"][1], L["cap"][2]
    else:
        cap_x, cap_y = w / 2, h * SUB_Y[fmt]
        cap_size = min(w, h) * (0.085 if fmt == "9x16" else 0.075) * (1.12 if style == "kinetic" else 1)
        cap_w = w * 0.84
    K = font_scale(font)  # ขนาดใน ASS = ขนาด em × K
    size = round(cap_size)
    outline = max(3, round(size * (0.085 if mode == "word" else 0.1)))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},{round(size * K)},&H00FFFFFF,&H00FFFFFF,{ass_color('#16121f')},&H64000000,-1,0,0,0,100,100,0,0,1,{outline},{max(2, size // 22)},5,{round(w * 0.06)},{round(w * 0.06)},0,222
Style: Label,{font},40,&H00121212,&H00FFFFFF,&H00FFFFFF,&H000B0B0B,-1,0,0,0,100,100,0,0,3,12,6,5,0,0,0,222
Style: Head,{font},40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,5,0,0,0,222
Style: Credit,{font},20,&H26FFFFFF,&H00FFFFFF,&H64000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,6,0,0,0,222

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    total_end = max((c.show_end for c in chunks), default=1) + 2
    # ----- ส่วนประกอบของสไตล์คอลลาจ -----
    if collage and scenes:
        if framed and header:
            portrait = h > w
            top, avail = (h * 0.025, h * 0.13) if portrait else (h * 0.012, h * 0.15)
            lh = avail / 3
            cols = [("#ffffff", "#000000"), ("#ffd21f", "#000000"), ("#ff2b2b", "#ffffff")]
            for i, txt in enumerate(header[:3]):
                if not txt:
                    continue
                fs = fit_size(txt, lh * (0.84 if i == 0 else 0.72), w * 0.92)
                fc, oc = cols[i]
                ev.append(f"Dialogue: 1,{_ts_ass(0)},{_ts_ass(total_end)},Head,,0,0,0,,"
                          f"{{\\an5\\pos({w / 2:.0f},{top + lh * (i + 0.5):.0f})\\fs{fs * K:.0f}\\bord{max(2, fs * 0.08):.1f}"
                          f"\\1c{ass_ovc(fc)}\\3c{ass_ovc(oc)}}}{_esc(txt)}")
        for j, s in enumerate(scenes):
            m = s.meta or {}
            st, en = s.start, s.end
            if m.get("badge"):
                bx, by, bs = L["badge"]
                box, ink = [("#e8304a", "#ffffff"), ("#121212", "#ffffff"), ("#ffffff", "#121212")][j % 3]
                x, y = cx0 + bx + bs * 0.4, cy0 + by + bs * 0.68
                ev.append(f"Dialogue: 2,{_ts_ass(st + 0.15)},{_ts_ass(en)},Label,,0,0,0,,"
                          f"{{\\an4\\move({cx0 - bs * 4:.0f},{y:.0f},{x:.0f},{y:.0f},0,260)\\fs{bs * K:.0f}\\bord{bs * 0.32:.1f}\\shad{bs * 0.12:.1f}"
                          f"\\1c{ass_ovc(ink)}\\3c{ass_ovc(box)}}}{_esc(m['badge'])}")
            if m.get("title"):
                tx, ty, ts, tmax = L["title"]
                fs = fit_size(m["title"], ts, tmax - ts * 0.9)
                box, ink = [("#ffffff", "#121212"), ("#121212", "#ffffff"), ("#e8304a", "#ffffff")][(1 if j % 2 else (0 if j % 4 == 0 else 2))]
                rot = 1.4 if j % 2 == 0 else -1.4
                ev.append(f"Dialogue: 2,{_ts_ass(st + 0.25)},{_ts_ass(en)},Label,,0,0,0,,"
                          f"{{\\an5\\pos({cx0 + tx:.0f},{cy0 + ty:.0f})\\frz{rot}\\fs{fs * K:.0f}\\bord{fs * 0.42:.1f}\\shad{fs * 0.13:.1f}"
                          f"\\1c{ass_ovc(ink)}\\3c{ass_ovc(box)}\\fscx60\\fscy60\\t(0,180,\\fscx104\\fscy104)\\t(180,300,\\fscx100\\fscy100)}}{_esc(m['title'])}")
            if m.get("credit"):
                kx, ky, ks = L["credit"]
                ev.append(f"Dialogue: 2,{_ts_ass(st)},{_ts_ass(en)},Credit,,0,0,0,,"
                          f"{{\\an6\\pos({cx0 + kx:.0f},{cy0 + ky:.0f})\\fs{ks * K:.0f}}}ภาพ: {_esc(m['credit'])}")
    # ----- ซับ -----
    hi_c = ass_ovc(hi)
    if mode == "word":
        all_toks = karaoke_tokens(chunks)
        for c, toks in zip(chunks, all_toks):
            words = [t for t in toks if not t["space"]]
            tot = sum(t["w"] for t in words) or 1
            span = (c.end - c.start) * 0.9
            acc = 0
            for t in words:
                t["at"] = c.start + acc / tot * span
                acc += t["w"]
            fs = size if text_width(c.plain, size) <= cap_w else size * cap_w / text_width(c.plain, size)
            for k, wd in enumerate(words):
                st = wd["at"]
                en = words[k + 1]["at"] if k + 1 < len(words) else c.show_end
                if en - st < 0.02:
                    continue
                parts = []
                shown = 0
                for t in toks:
                    if t["space"]:
                        if parts and shown <= k:
                            parts.append(" ")
                        continue
                    if shown > k:
                        break
                    txt = _esc(t["s"])
                    if shown == k:
                        parts.append(f"{{\\1c{hi_c}\\fscx35\\fscy35\\t(0,140,\\fscx108\\fscy108)\\t(140,220,\\fscx100\\fscy100)}}{txt}")
                    else:
                        parts.append(f"{{\\1c{hi_c if t['hi'] else '&HFFFFFF&'}}}{txt}")
                    shown += 1
                fade = "\\fad(0,120)" if k == len(words) - 1 else ""
                ev.append(f"Dialogue: 3,{_ts_ass(st)},{_ts_ass(en)},Sub,,0,0,0,,{{\\an5\\pos({cap_x:.0f},{cap_y:.0f})\\fs{fs * K:.0f}{fade}}}" + "".join(parts).rstrip())
    else:
        for c in chunks:
            txt = re.sub(r"\*(.+?)\*", lambda m: "{\\c" + hi_c + "}" + _esc(m.group(1)) + "{\\c&HFFFFFF&}", c.text)
            txt = txt.replace("*", "")
            fs = size if text_width(c.plain, size) <= cap_w * 1.9 else size * 0.85
            pop = f"{{\\an5\\pos({cap_x:.0f},{cap_y:.0f})\\fs{fs * K:.0f}\\fad(80,120)\\fscx92\\fscy92\\t(0,160,\\fscx100\\fscy100)}}"
            ev.append(f"Dialogue: 3,{_ts_ass(c.start)},{_ts_ass(c.show_end)},Sub,,0,0,0,,{pop}{txt}")
    return head + "\n".join(ev) + "\n"


def build(script, speed="slow", timings=None, min_total=0.0):
    scenes, chunks = parse_script(script)
    total = time_chunks(scenes, chunks, speed, timings, min_total)
    return scenes, chunks, total


def utf8_console():
    """คอนโซล Windows (cp874/cp1252) พิมพ์ภาษาไทยและสัญลักษณ์ ✔ ⚠ ไม่ได้เมื่อ output ถูก pipe: บังคับ UTF-8"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--speed", default="slow", choices=list(CPS))
    ap.add_argument("--srt")
    ap.add_argument("--ass")
    ap.add_argument("--json")
    ap.add_argument("--format", default="9x16", choices=list(FORMATS))
    ap.add_argument("--style", default="pastel3d")
    ap.add_argument("--caption", default="auto", choices=["auto", "word", "phrase"])
    ap.add_argument("--framed", action="store_true", help="กรอบ + แถบหัวด้านบน (สไตล์ collage)")
    ap.add_argument("--series", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--font", default="Kanit")
    a = ap.parse_args(argv)
    with open(a.script, encoding="utf-8") as fh:
        scenes, chunks, total = build(fh.read(), a.speed)
    for i, c in enumerate(chunks, 1):
        print(f"{i:3d}  {c.start:6.2f} → {c.show_end:6.2f}  [{c.pause or ' ':3s}] {c.plain}")
    print(f"\nรวม {len(chunks)} ท่อน · {len(scenes)} ฉาก · ยาว {total:.1f} วินาที")
    for wmsg in warnings(chunks):
        print("⚠", wmsg, file=sys.stderr)
    if a.srt:
        with open(a.srt, "w", encoding="utf-8") as fh:
            fh.write(to_srt(chunks))
    if a.ass:
        header = (a.series, a.title, "") if a.framed else None
        with open(a.ass, "w", encoding="utf-8") as fh:
            fh.write(to_ass(chunks, a.format, pick_font(a.font), scenes, a.style, a.caption,
                            a.framed if a.style == "collage" else False, header))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"total": total, "scenes": [asdict(s) for s in scenes],
                       "chunks": [asdict(c) | {"plain": c.plain} for c in chunks]}, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
