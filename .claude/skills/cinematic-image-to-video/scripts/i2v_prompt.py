"""i2v_prompt.py — สร้าง prompt วิดีโอจากภาพนิ่ง (image-to-video) ตามมาตรฐาน "CINEMATIC 3D ANIMATION — IMAGE TO VIDEO"

แต่ละช็อตได้ prompt ภาษาอังกฤษ 7 ส่วนตามมาตรฐาน (references/prompt-standard.md):
  เปิด → ความต่อเนื่องของตัวละคร → การแสดง → กล้อง → สภาพแวดล้อม → คุณภาพภาพ → ข้อห้าม
ใส่เฉพาะสิ่งแวดล้อมที่มีอยู่ในช็อตนั้นจริง (ห้ามเติมรถไฟในร้านข้าวต้ม = "No random object generation")

ใช้:  python3 i2v_prompt.py project.json [--clip 1] [--scene 4] [--format 9x16]
      (hf_plan.py --motion เรียก build() นี้ให้อัตโนมัติ)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

OPEN = "Animate this exact still frame into a {ar} shot from a high-end cinematic 3D animated feature film."
CHAR_ANIM = ("Character animation: natural human-like movement with realistic body mechanics, subtle breathing, natural "
             "blinking, small eye movements, a slight head tilt, soft hand gestures and a believable facial expression, "
             "smooth, organic and emotionally expressive.")
QUALITY = ("Visual quality: high-end 3D animated feature film look, detailed character modeling, realistic fabric "
           "simulation, expressive facial animation, cinematic depth of field, global illumination, physically based "
           "rendering, soft volumetric lighting, beautiful cinematic composition, ultra-detailed 4K look, 24 fps feel.")
RULES = ("Requirements: smooth continuous motion without sudden jumps; preserve the original composition; keep the "
         "character's identity and clothing exactly; no facial distortion or body deformation; no extra fingers or "
         "duplicated limbs; no new objects appearing; no scene change or cut; no text, captions, subtitles, logos or watermark.")
CAMERA = {"push-in": "slow cinematic dolly-in toward the subject", "pull-out": "slow dolly-out that gently reveals more of the scene",
          "pan-left": "smooth slow tracking move to the left", "pan-right": "smooth slow tracking move to the right",
          "tilt-up": "gentle slow tilt up", "tilt-down": "gentle slow tilt down",
          "static": "nearly locked-off framing with a barely perceptible handheld drift"}
SHOT_CAMERA = {"โคลสอัพ": "push-in", "ใกล้": "push-in", "กว้าง": "pull-out", "ไกลมาก": "pull-out"}
# (คำในฉาก/ท่าทาง/การเคลื่อนไหว → การเคลื่อนไหวของสภาพแวดล้อม) ใส่เฉพาะที่พบ
ENV = [
    (("รถไฟ", "ขบวน", "train"), "the train gliding along the track with its lights sliding past"),
    (("ไอน้ำ", "ข้าวต้ม", "ก๋วยเตี๋ยว", "ซุป", "ร้อน ๆ", "ชาร้อน", "กาแฟ", "steam", "hot food", "porridge", "soup"),
     "steam rising and curling softly from the hot food"),
    (("เปียก", "ฝน", "wet", "rain"), "reflections shimmering on the wet ground"),
    (("ชานชาลา", "platform", "พื้นมัน", "glossy"), "soft reflections moving on the polished floor"),
    (("เมือง", "ตึก", "city", "skyline"), "distant city lights twinkling and flickering softly"),
    (("หลอดไฟ", "โคม", "ไฟหลอด", "bulb", "lamp", "lantern", "neon"), "warm lights glowing with a gentle natural flicker"),
    (("ลม", "wind", "breeze"), "a gentle breeze moving hair and fabric"),
    (("ทะเล", "คลื่น", "sea", "wave"), "waves rolling in gently"),
    (("ใบไม้", "ต้นไม้", "leaf", "leaves", "tree"), "leaves swaying gently"),
    (("โทรศัพท์", "มือถือ", "จอ", "phone", "screen"), "the phone screen glow softly lighting the face"),
    (("น้ำตา", "tear"), "a single tear slowly rolling down the cheek"),
    (("เทียน", "candle"), "candle flames flickering"),
]
ALWAYS_ENV = "subtle hair movement and fine atmospheric particles drifting in the light"


def _is_en(s: str) -> bool:
    letters = [ch for ch in s if ch.isalpha()]
    return bool(letters) and sum(ch.isascii() for ch in letters) / len(letters) > 0.6


def env_motion(text: str) -> list:
    t = (text or "").lower()
    out = [phrase for keys, phrase in ENV if any(k.lower() in t for k in keys)]
    return out + [ALWAYS_ENV]


def character_block(chars: list, with_refs: bool) -> str:
    if not chars:
        return ""
    who = "; ".join(", ".join(x for x in (c.get("look"), c.get("outfit")) if x) for c in chars)
    src = "the start frame and the attached character reference sheet" if with_refs else "the start frame"
    many = "characters" if len(chars) > 1 else "character"
    return (f"Character consistency: keep exactly the same {many} throughout the whole shot ({who}), with identical facial "
            f"features, hairstyle, clothing, colors, body proportions and character design as in {src}.")


def build(scene_desc: str, meta: dict, chars: list, camera: str = "push-in", aspect: str = "9:16",
          motion_en: str = "", with_refs: bool = False) -> str:
    """prompt หนึ่งช็อต · motion_en = คำบรรยายการเคลื่อนไหวภาษาอังกฤษที่ทีมเขียนไว้ (scenes[j].motionPrompt) ถ้ามี"""
    meta = meta or {}
    m = meta.get("motion", "")
    m = "" if m in ("ใช่", "yes", "true") else m
    if motion_en:
        action = motion_en
    elif m and _is_en(m):  # เขียน เคลื่อนไหว: เป็นอังกฤษมาแล้ว ใช้ตรง ๆ (แม่นกว่าแปลจากท่าทางภาษาไทย)
        action = m
    else:
        action = "; ".join(x for x in (meta.get("action", ""), m) if x)
    ar = {"9:16": "vertical 9:16", "16:9": "horizontal 16:9"}.get(aspect, aspect)
    parts = [OPEN.format(ar=ar), character_block(chars, with_refs)]
    if action:
        parts.append(f"Action in this shot: {action}.")
    if chars:
        parts.append(CHAR_ANIM)
    parts.append(f"Camera: {CAMERA.get(camera, CAMERA['push-in'])}, smooth and steady, cinematic.")
    env = env_motion(" ".join([scene_desc or "", meta.get("action", ""), m, motion_en or ""]))
    parts.append("Environment animation: " + ", ".join(env) + ".")
    parts += [QUALITY, RULES]
    return " ".join(p for p in parts if p)


def _cli(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--clip", type=int, default=1)
    ap.add_argument("--scene", type=int, help="เลขฉาก (ไม่ใส่ = ทุกฉาก)")
    ap.add_argument("--format", default="9x16")
    a = ap.parse_args(argv)
    here = os.path.dirname(os.path.abspath(__file__))
    svs = os.path.join(here, "..", "..", "social-video-studio", "scripts")
    sys.path.insert(0, svs)
    import build_subs as bs  # noqa: E402
    import render  # noqa: E402
    p = json.load(open(a.project, encoding="utf-8"))
    clip = p["clips"][a.clip - 1]
    scenes, _ = bs.parse_script(clip["script"])
    metas = clip.get("scenes") or []
    cm = {c["name"]: c for c in p.get("characters") or [] if c.get("name")}
    for j, sc in enumerate(scenes):
        if a.scene and j + 1 != a.scene:
            continue
        names = [x.strip() for x in (sc.meta or {}).get("cast", "").split(",") if x.strip()]
        chars = [cm[n] for n in names if n in cm]
        md = metas[j] if j < len(metas) and isinstance(metas[j], dict) else {}
        cam = render.camera_of(sc, j, p.get("visualStyle", "toon3d"))
        refs = any((c.get("sheet") or {}).get("job_id") for c in chars)
        print(f"--- ฉาก {j + 1} ---")
        print(build(sc.desc, sc.meta, chars, cam, "9:16" if a.format == "9x16" else "16:9", md.get("motionPrompt", ""), refs))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
