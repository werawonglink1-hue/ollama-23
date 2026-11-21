#!/usr/bin/env python3
"""ช่วยต่อ Higgsfield (MCP) เข้ากับ project.json ของ social-video-studio

  plan   project.json → รายการคำขอที่ส่งให้เครื่องมือ Higgsfield ได้ทันที:
         เสียงพากย์ไทยต่อคลิป (generate_audio: qwen_audio_tts), ภาพต่อฉาก (generate_image_batch),
         เพลง (generate_audio: elevenlabs_music_v2_5 ถ้าขอ) พร้อมไฟล์ปลายทางของแต่ละรายการ
  fetch  ผลลัพธ์ (index → url จาก jobs_wait) → ดาวน์โหลดลงไฟล์ปลายทาง แล้วเขียน media / voice / musicFile ลง project.json

ราคาโดยประมาณ (ต้องเช็กด้วย estimate_*_cost ทุกครั้งก่อนสร้าง):
  เสียงพากย์ qwen_audio_tts ≈ 0.2 เครดิต/คลิป 60 วิ · ภาพ gpt_image_2_6 ≈ 0.75 เครดิต/ภาพ · เพลง ElevenLabs 60 วิ ≈ 8.7 เครดิต

ตัวอย่าง:
  python3 hf_plan.py plan work/runner/project.json --voice --images missing > work/runner/hf_plan.json
  (ส่งแต่ละรายการให้ Higgsfield → jobs_wait → เก็บ {"0": "https://...", "3": "https://..."} เป็น results.json)
  python3 hf_plan.py fetch work/runner/hf_plan.json work/runner/results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SVS = os.path.join(HERE, "..", "..", "social-video-studio", "scripts")
sys.path.insert(0, SVS)

STYLE_SUFFIX = {
    "collage": "editorial documentary photograph, archival magazine feel, natural light, clear subject, no text",
    "pastel3d": "soft low-poly 3D diorama, Thai neighborhood, pastel pink and lavender sky, warm sunset light, toy-like characters, no text",
    "kinetic": "claymation 3D characters, bold saturated colors, swirling background, playful, no text",
    "watercolor": "warm watercolor storybook illustration, paper texture, soft edges, no text",
    "anime-dusk": "anime background art, golden hour, volumetric light, nostalgic, no text",
    "papercut": "layered paper-cut craft, minimal shapes, soft shadows between layers, no text",
    "neon-night": "quiet night city street, glowing neon lights, deep blue, bokeh, no text",
    "film": "35mm film photo, warm grain, nostalgic Thai street, soft focus, no text",
    "cinematic": "cinematic realism, photorealistic film still, natural lighting, 35mm anamorphic lens, shallow depth of field, film color grading, no text",
}
MUSIC_PROMPTS = {
    "doc": "cinematic documentary underscore, soft piano ostinato in A minor, gentle heartbeat pulse, warm strings, no vocals",
    "musicbox": "gentle music box lullaby, warm soft pad, slow arpeggio, tender, no vocals",
    "lofi": "warm lofi, mellow seventh chords, soft vinyl crackle, relaxed, no vocals",
    "dream": "ambient dreamy night pad, distant soft bells, mysterious and calm, no vocals",
    "playful": "playful pizzicato strings and marimba, light bouncy rhythm, cheerful, no vocals",
}


def cmd_plan(a):
    import build_subs as bs
    import voice_align as va
    p = json.load(open(a.project, encoding="utf-8"))
    style = p.get("visualStyle", "collage")
    fmt = (p.get("formats") or ["9x16"])[0]
    brief = p.get("brief") or {}
    chars = ", ".join(x for x in (brief.get("hero"), brief.get("side")) if x)
    items, idx = [], 0
    clips = [a.clip] if a.clip else range(1, len(p["clips"]) + 1)
    for ci in clips:
        clip = p["clips"][ci - 1]
        scenes, chunks, total = bs.build(clip["script"], p.get("speed", "normal"), clip.get("timings"))
        if a.voice:
            cast = {**(p.get("cast") or {}), **(clip.get("cast") or {})}
            parts, missing = va.voice_parts(chunks, cast, p.get("narratorStyle", "doc"), p.get("speed", "normal"), ci)
            if a.voice_id:
                for part in parts:
                    if part["params"]["voice_id"].startswith("<"):
                        part["params"]["voice_id"] = a.voice_id
            if len(parts) == 1:  # ผู้บรรยายคนเดียว
                part = parts[0]
                items.append({"index": idx, "kind": "voice", "tool": "generate_audio", "clip": ci,
                              "target": f"media/clip{ci}-voice.wav", "params": part["params"],
                              "after": f"whisper_words.py → voice_align.py assemble --project {os.path.basename(a.project)} --clip {ci}"})
                idx += 1
            else:  # หลายบทบาท: หนึ่งคำขอต่อช่วงผู้พูด
                for part in parts:
                    items.append({"index": idx, "kind": "voice-part", "tool": "generate_audio", "clip": ci,
                                  "target": part["target"], "part": {k: part[k] for k in ("part", "speaker", "chunks")},
                                  "params": part["params"],
                                  "after": f"whisper_words.py ทุกช่วง → voice_align.py assemble-cast --project "
                                           f"{os.path.basename(a.project)} --clip {ci}"})
                    idx += 1
                if missing:
                    print(f"⚠ คลิป {ci}: ยังไม่ได้แคสต์เสียงให้ {', '.join(missing)} (ใส่ cast ใน project.json)", file=sys.stderr)
        metas = clip.get("scenes") or []
        for j, sc in enumerate(scenes):
            has = j < len(metas) and isinstance(metas[j], dict) and metas[j].get("media")
            if a.images == "none" or (a.images == "missing" and has) or (a.images == "hero" and j > 0):
                continue
            layout = sc.meta.get("layout", "")
            circle = "วงกลม" in layout or (style == "collage" and "เต็ม" not in layout and j % 3 == 1)
            if style == "collage":
                ar = "1:1" if circle or fmt == "9x16" else "3:2"
            else:
                ar = "9:16" if fmt == "9x16" else "16:9"
            subject = (metas[j].get("prompt") if j < len(metas) and isinstance(metas[j], dict) and metas[j].get("prompt") else sc.desc)
            prompt = f"{subject}. {STYLE_SUFFIX.get(style, '')}" + (f". Characters: {chars}" if chars else "")
            if circle:
                prompt += ". Single person, waist-up portrait, facing camera, plain light background (for background removal)"
            items.append({"index": idx, "kind": "image", "tool": "generate_image_batch", "clip": ci, "scene": j + 1,
                          "target": f"media/clip{ci}-scene{j + 1}" + (".png" if circle else ".jpg"),
                          "cutout": circle, "params": {"model": "gpt_image_2_6", "prompt": prompt, "aspect_ratio": ar}})
            idx += 1
    if a.music:
        longest = max(bs.build(c["script"], p.get("speed", "normal"), c.get("timings"))[2] for c in p["clips"])
        items.append({"index": idx, "kind": "music", "tool": "generate_audio", "target": "audio/music-higgsfield.mp3",
                      "params": {"model": "elevenlabs_music_v2_5", "prompt": MUSIC_PROMPTS.get(p.get("music", "doc"), MUSIC_PROMPTS["doc"]),
                                 "duration": int(longest + 2), "force_instrumental": True}})
    plan = {"project": os.path.abspath(a.project), "items": items,
            "notes": ["เช็กราคาด้วย estimate_audio_cost / estimate_image_cost แล้วขออนุมัติจำนวนเครดิตก่อนสร้างทุกครั้ง",
                      "ภาพที่ cutout=true: หลังสร้างเสร็จให้ remove_background (media_type=image) แล้วใช้ไฟล์ PNG ที่ได้",
                      "ส่งภาพหลายฉากพร้อมกันด้วย generate_image_batch (ครั้งละไม่เกิน 12) แล้ว jobs_wait"]}
    json.dump(plan, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


def cmd_fetch(a):
    plan = json.load(open(a.plan, encoding="utf-8"))
    res = json.load(open(a.results, encoding="utf-8"))
    p_path = plan["project"]
    p = json.load(open(p_path, encoding="utf-8"))
    pdir = os.path.dirname(p_path)
    for it in plan["items"]:
        url = res.get(str(it["index"]))
        if not url:
            continue
        dst = os.path.join(pdir, it["target"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "SocialVideoStudio/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as fh:
            fh.write(r.read())
        if it["kind"] == "image":
            metas = p["clips"][it["clip"] - 1].setdefault("scenes", [])
            while len(metas) < it["scene"]:
                metas.append({})
            metas[it["scene"] - 1].update({"media": it["target"], "prompt": it["params"]["prompt"], "generator": "higgsfield"})
        elif it["kind"] == "voice":
            p["clips"][it["clip"] - 1]["voiceRaw"] = it["target"]  # ยังไม่เว้นจังหวะ: ต้องผ่าน voice_align.py assemble
        elif it["kind"] == "voice-part":  # หลายบทบาท: เก็บรายการช่วงไว้ให้ assemble-cast
            parts = p["clips"][it["clip"] - 1].setdefault("voiceParts", [])
            parts[:] = [x for x in parts if x.get("part") != it["part"]["part"]] + [dict(it["part"], target=it["target"])]
            parts.sort(key=lambda x: x["part"])
        elif it["kind"] == "music":
            p["musicFile"] = it["target"]
        print(f"✔ [{it['index']}] {it['kind']} → {it['target']}")
    json.dump(p, open(p_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("project")
    pl.add_argument("--clip", type=int)
    pl.add_argument("--voice", action="store_true")
    pl.add_argument("--voice-id")
    pl.add_argument("--images", default="missing", choices=["none", "missing", "all", "hero"])
    pl.add_argument("--music", action="store_true")
    fe = sub.add_parser("fetch")
    fe.add_argument("plan")
    fe.add_argument("results")
    a = ap.parse_args(argv)
    return cmd_plan(a) if a.cmd == "plan" else cmd_fetch(a)


if __name__ == "__main__":
    sys.exit(main())
