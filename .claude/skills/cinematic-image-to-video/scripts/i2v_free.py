"""i2v_free.py — ทำวิดีโอให้ฉากใน project.json แบบไม่ใช้ Higgsfield (ทางเลือกเสริมของสกิล cinematic-image-to-video)

  --engine local     ฟรีทุกเครื่อง ไม่ใช้ AI: ภาพนิ่ง "มีชีวิต" 2.5D (กล้อง ไฟระยิบ ฝุ่นในแสง ไอน้ำ พื้นเปียก หายใจ)
                     ใช้ Python + numpy + Pillow + ffmpeg (animate_still.py) · ตัวละครไม่เปลี่ยนสีหน้า/ไม่กะพริบตา
  --engine comfyui   ฟรีถ้ามี GPU: AI image-to-video จริงด้วย ComfyUI บนเครื่องตัวเอง (Wan 2.2 TI2V-5B, comfy_i2v.py)
                     prompt ตามมาตรฐานเดียวกับ Higgsfield (i2v_prompt.py) ได้การแสดงตามสเปก

ใช้:
  python3 i2v_free.py project.json --engine local                    # ฉากที่มี เคลื่อนไหว: และยังไม่มีวิดีโอ
  python3 i2v_free.py project.json --engine local --scenes all       # ทุกฉากที่ยังเป็นภาพนิ่ง (ฟรี ทำได้หมด)
  python3 i2v_free.py project.json --engine comfyui --server http://127.0.0.1:8188 [--workflow my_wan_api.json]
  แล้ว render.py ตามปกติ (ใส่ "fps": 24 ใน project.json) และตรวจด้วย check_i2v.py

เอฟเฟกต์ต่อฉาก (engine local): ใส่ scenes[j].localFx ใน project.json หลังเปิดดูภาพ เช่น
  {"twinkle": 1, "particles": 40, "steam": [[0.83, 0.47]], "breath": [[0.5, 0.45, 0.2]],
   "ripple": [[0, 0.65, 0.35, 1]], "glow": [[0.5, 0.6, 0.12]], "focus": [0.5, 0.3]}
  ไม่ใส่ = เลือกให้จากคำในฉาก (กลางคืน/ไฟเมือง → twinkle, ทุกฉากมีฝุ่นในแสง)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SVS = os.path.join(HERE, "..", "..", "social-video-studio", "scripts")
sys.path.insert(0, SVS)
sys.path.insert(0, HERE)

NIGHT = ("ยามดึก", "กลางคืน", "เที่ยงคืน", "ค่ำ", "ไฟ", "เมือง", "โคม", "หลอด", "night", "city", "light", "neon", "bokeh", "lamp")
STEAMY = ("ไอน้ำ", "ข้าวต้ม", "ก๋วยเตี๋ยว", "ซุป", "กาแฟ", "ชาร้อน", "steam", "soup", "porridge", "coffee")
CLOSE = ("โคลสอัพ", "ใกล้")
SIZES = {"9x16": (1080, 1920), "16x9": (1920, 1080)}
COMFY_SIZES = {"9x16": (704, 1280), "16x9": (1280, 704)}


def auto_fx(sc):
    meta = sc.meta or {}
    text = " ".join([sc.desc or "", meta.get("action", ""), meta.get("motion", "")]).lower()
    fx = {"particles": 22 if meta.get("shot", "") in CLOSE else 36}
    if any(k in text for k in NIGHT):
        fx["twinkle"] = 1
    if any(k in text for k in STEAMY):
        print(f"  ⚠ ฉาก '{sc.desc[:30]}' น่าจะมีไอน้ำ: ใส่ localFx.steam = [[x, y]] ตรงชาม/หม้อ แล้วทำใหม่ด้วย --redo",
              file=sys.stderr)
    return fx


def targets(scenes, metas, mode, redo):
    out = []
    pick = {int(x) for x in mode.split(",")} if mode not in ("marked", "all") else None
    for j, sc in enumerate(scenes):
        m = metas[j] if j < len(metas) and isinstance(metas[j], dict) else {}
        if pick is not None and j + 1 not in pick:
            continue
        if mode == "marked" and not (sc.meta or {}).get("motion"):
            continue
        if m.get("video") and not redo:
            continue
        still = m.get("still") or m.get("media")
        if not still or still.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
            continue
        out.append((j, sc, m, still))
    return out


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--engine", choices=["local", "comfyui"], default="local")
    ap.add_argument("--clip", type=int, default=1)
    ap.add_argument("--scenes", default="marked", help="marked | all | เลขฉาก เช่น 1,3,6")
    ap.add_argument("--redo", action="store_true", help="ทำใหม่แม้ฉากมีวิดีโอแล้ว")
    ap.add_argument("--server", default=os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--workflow", help="workflow ComfyUI แบบ API ของตัวเอง (ค่าเริ่มต้น Wan 2.2 TI2V-5B)")
    ap.add_argument("--max-seconds", type=float, default=5.0, help="engine comfyui: ความยาวสูงสุดต่อช็อต (Wan 5B ≈ 5 วิ)")
    a = ap.parse_args(argv)

    import build_subs as bs
    import render
    import i2v_prompt

    p = json.load(open(a.project, encoding="utf-8"))
    pdir = os.path.dirname(os.path.abspath(a.project))
    clip = p["clips"][a.clip - 1]
    fmt = (p.get("formats") or ["9x16"])[0]
    fps = int(p.get("fps") or 24)
    style = p.get("visualStyle", "toon3d")
    scenes, _, _ = bs.build(clip["script"], p.get("speed", "normal"), clip.get("timings"))
    metas = clip.setdefault("scenes", [])
    cm = {c["name"]: c for c in p.get("characters") or [] if c.get("name")}
    todo = targets(scenes, metas, a.scenes, a.redo)
    if not todo:
        print("ไม่มีฉากที่ต้องทำ (ใช้ --scenes all หรือ --redo)")
        return 0
    for j, sc, m, still in todo:
        dur = max(1.0, sc.end - sc.start) + 0.25
        cam = render.camera_of(sc, j, style)
        out_rel = f"media/clip{a.clip}-scene{j + 1}-{a.engine}.mp4"
        out = os.path.join(pdir, out_rel)
        src = still if os.path.isabs(still) else os.path.join(pdir, still)
        seed = int(hashlib.md5(f"{a.clip}-{j}".encode()).hexdigest()[:6], 16)
        if a.engine == "local":
            import animate_still
            fx = m.get("localFx") or auto_fx(sc)
            animate_still.animate(src, out, dur, cam, SIZES.get(fmt, SIZES["9x16"]), fps, fx, seed)
            gen = "local-2.5d (animate_still.py)"
        else:
            import comfy_i2v
            names = [x.strip() for x in (sc.meta or {}).get("cast", "").split(",") if x.strip()]
            chars = [cm[n] for n in names if n in cm]
            ar = "9:16" if fmt == "9x16" else "16:9"
            prompt = i2v_prompt.build(sc.desc, sc.meta, chars, cam, ar, m.get("motionPrompt", ""), False)
            secs = min(a.max_seconds, dur / 1.35 + 0.2)
            comfy_i2v.run_one(a.server, src, prompt, out, secs, fps, COMFY_SIZES.get(fmt, COMFY_SIZES["9x16"]), seed,
                              a.workflow)
            gen = "comfyui (Wan 2.2 TI2V-5B)" if not a.workflow else f"comfyui ({os.path.basename(a.workflow)})"
        while len(metas) <= j:
            metas.append({})
        metas[j].update({"still": still, "media": out_rel, "video": out_rel, "generator": gen, "engine": a.engine})
        print(f"✔ ฉาก {j + 1} ({dur:.1f} วิ · กล้อง {cam}) → {out_rel}")
        json.dump(p, open(a.project, "w", encoding="utf-8"), ensure_ascii=False, indent=1)  # บันทึกทีละฉาก กันงานหาย
    print("ต่อไป: check_i2v.py ตรวจคลิป → render.py (fps 24) → qc_check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
