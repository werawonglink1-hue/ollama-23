#!/usr/bin/env python3
"""ช่วยต่อ Higgsfield (MCP) เข้ากับ project.json ของ social-video-studio

  plan   project.json → รายการคำขอที่ส่งให้เครื่องมือ Higgsfield ได้ทันที (ทำเป็น 3 ระยะ เพราะระยะหลังใช้ job id ของระยะก่อน):
         1) --characters  ตัวละคร: character sheet ต่อตัว (เวิร์กโฟลว์ character-sheet) ใช้ซ้ำได้ทั้งซีรีส์
         2) --images      ภาพต่อช็อต ตามบรรทัดฉาก (ช็อต ตัวละคร ท่าทาง) แนบ sheet ของตัวละครในช็อตเป็น image_references
         3) --motion      วิดีโอจากภาพช็อต (image-to-video) เฉพาะช็อตที่ "เคลื่อนไหว: ..." หรือทุกช็อต
         + --voice เสียงพากย์ (qwen_audio_tts, หลายบทบาท) · --music เพลง (elevenlabs_music_v2_5)
  fetch  ผลลัพธ์ (index → url จาก jobs_wait) → ดาวน์โหลดลงไฟล์ปลายทาง แล้วเขียน media / voice / musicFile ลง project.json

ราคาโดยประมาณ (21 พ.ย. 2026 · ต้องเช็กด้วย estimate_*_cost ทุกครั้งก่อนสร้าง):
  เสียงพากย์ qwen_audio_tts ≈ 0.2/คลิป · ภาพช็อต gpt_image_2_6 (1k) ≈ 0.75/ภาพ · character sheet seedream_5_5 2k ≈ 3.5/ตัว (ครั้งเดียว)
  วิดีโอ grok_video_v15_lite ≈ 1/วินาที (3 วิ 480p = 3, 5 วิ 720p = 5) · kling3_0_turbo 5 วิ = 7.5 · seedance_2_5 5 วิ = 35
  เพลง ElevenLabs 60 วิ ≈ 8.7

ตัวอย่าง:
  python3 hf_plan.py plan work/runner/project.json --characters > plan1.json   (สร้าง → jobs_wait → fetch)
  python3 hf_plan.py plan work/runner/project.json --voice --images missing > plan2.json
  python3 hf_plan.py plan work/runner/project.json --motion marked > plan3.json
  (ส่งแต่ละรายการให้ Higgsfield → jobs_wait → เก็บ {"0": "https://...", "3": "https://..."} เป็น results.json)
  python3 hf_plan.py fetch work/runner/hf_plan.json work/runner/results.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
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
    "toon3d": "stylized 3D animated short film still, expressive cartoon characters with clean simple shading, realistic Thai location, soft cinematic lighting, no text",
    "cinematic": "cinematic realism, photorealistic film still, natural lighting, 35mm anamorphic lens, shallow depth of field, film color grading, no text",
}
SHEET_STYLE = {"toon3d": "Classic 3D", "kinetic": "Classic 3D", "pastel3d": "Painterly 3D", "anime-dusk": "Anime",
               "watercolor": "Painterly 2D", "papercut": "Classic 2D", "neon-night": "CGI", "cinematic": "Realism",
               "film": "Realism", "collage": "Realism"}  # สไตล์ของเวิร์กโฟลว์ character-sheet ที่ใกล้สุด
SHOT_EN = {"ไกลมาก": "extreme wide establishing shot", "กว้าง": "wide shot", "กลาง": "medium shot", "ใกล้": "medium close-up",
           "โคลสอัพ": "close-up on the face", "มุมสูง": "high-angle shot", "มุมต่ำ": "low-angle shot",
           "ข้ามไหล่": "over-the-shoulder shot", "มุมมองตัวละคร": "point-of-view shot"}
SHOT_CYCLE = ["wide shot", "medium shot", "close-up on the face", "medium close-up", "low-angle shot", "over-the-shoulder shot"]
CAMERA_EN = {"push-in": "slow camera push-in", "pull-out": "slow camera pull-back", "pan-left": "gentle pan left",
             "pan-right": "gentle pan right", "tilt-up": "slow tilt up", "tilt-down": "slow tilt down", "static": "locked-off camera"}
MOTION_DEFAULT = {"model": "grok_video_v15_lite", "resolution": "480p", "seconds": 3}
COST = {"qwen_audio_tts": 0.2, "gpt_image_2_6": 0.75, "seedream_5_5": 3.5, "elevenlabs_music_v2_5": 8.7}
VIDEO_COST_PER_SEC = {"grok_video_v15_lite": 1.0, "kling3_0_turbo": 1.5, "seedance_2_5": 7.0}


def slugify(s):
    return re.sub(r"[^\w\u0E00-\u0E7F\-]+", "-", str(s)).strip("-")[:40] or "char"  # เก็บสระ/วรรณยุกต์ไทยไว้ครบ


def char_map(p):
    return {c["name"]: c for c in (p.get("characters") or []) if c.get("name")}


def chars_in(scene, p, brief_chars=()):
    """ตัวละครในช็อต: จาก "ตัวละคร:" ในบรรทัดฉาก ไม่ใส่ = ตัวละครที่ชื่ออยู่ในคำบรรยายฉาก"""
    cm = char_map(p)
    named = [x.strip() for x in re.split(r"[,、/]| และ ", (scene.meta or {}).get("cast", "")) if x.strip()]
    if not named:
        named = [n for n in cm if n in scene.desc] or [n for n in brief_chars if n and n in scene.desc]
    return [cm.get(n, {"name": n}) for n in named]


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
    a.images = a.images or ("none" if (a.characters or a.motion != "none") else "missing")
    if a.characters:  # ระยะ 1: ตัวละคร (ใช้ซ้ำทั้งซีรีส์ ทำครั้งเดียว)
        for c in p.get("characters") or []:
            if (c.get("sheet") or {}).get("job_id") and not a.redo:
                continue
            desc = "; ".join(x for x in (c.get("role"), c.get("look"), c.get("outfit")) if x)
            items.append({"index": idx, "kind": "character", "tool": "generate_image", "character": c["name"],
                          "target": f"media/char-{slugify(c['name'])}.png", "workflow": "character-sheet",
                          "sheetStyle": SHEET_STYLE.get(style, "Realism"),
                          "entry": {"name": c["name"], "description": desc,
                                    "facts": [f"{k}: {v}" for k, v in (c.get("facts") or {}).items()]},
                          "params": {"model": "seedream_5_5", "aspect_ratio": "16:9", "resolution": "2k",
                                     "prompt": "<เขียนตามเวิร์กโฟลว์ character-sheet (get_workflow_instructions) จาก entry + sheetStyle>"},
                          "budgetParams": {"model": "gpt_image_2_6", "aspect_ratio": "16:9",
                                           "prompt": f"Character reference sheet of ONE original character, {c['name']}: {desc}. "
                                                     f"Full-body front view, side view, back view and a face close-up on a plain light "
                                                     f"background, consistent design across views. {STYLE_SUFFIX.get(style, '')}"}})
            idx += 1
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
        for j, sc in enumerate(scenes):  # ระยะ 3: วิดีโอจากภาพช็อต
            meta = metas[j] if j < len(metas) and isinstance(metas[j], dict) else {}
            want = a.motion == "all" or (a.motion in ("marked", "key") and (sc.meta or {}).get("motion")) or \
                (a.motion == "key" and j == 0)
            if a.motion == "none" or not want or (meta.get("video") and not a.redo):
                continue
            if not meta.get("job_id"):
                print(f"⚠ คลิป {ci} ฉาก {j + 1}: ยังไม่มีภาพช็อต (job_id) สร้างภาพก่อน แล้วค่อยทำวิดีโอ", file=sys.stderr)
                continue
            mv = {**MOTION_DEFAULT, **(p.get("motion") or {})}
            secs = int(min(max(2, round(sc.end - sc.start)), mv["seconds"]))
            cam = CAMERA_EN.get(__import__("render").camera_of(sc, j, style), "slow camera push-in")
            mdesc = (sc.meta or {}).get("motion", "")
            action = mdesc if mdesc and mdesc not in ("ใช่", "yes", "true") else (sc.meta or {}).get("action", "")
            items.append({"index": idx, "kind": "motion", "tool": "generate_video", "clip": ci, "scene": j + 1,
                          "target": f"media/clip{ci}-scene{j + 1}.mp4",
                          "params": {"model": mv["model"], "duration": secs, "resolution": mv["resolution"],
                                     "aspect_ratio": "9:16" if fmt == "9x16" else "16:9",
                                     "prompt": f"{action + '. ' if action else ''}{cam}, subtle natural character motion and "
                                               f"environmental motion, keep characters, costumes and setting exactly as in the start "
                                               f"frame, no text, no captions",
                                     "medias": [{"role": "start_image", "value": meta["job_id"]}]}})
            idx += 1
        for j, sc in enumerate(scenes):  # ระยะ 2: ภาพต่อช็อต
            has = j < len(metas) and isinstance(metas[j], dict) and metas[j].get("media")
            if a.images == "none" or (a.images == "missing" and has) or (a.images == "hero" and j > 0):
                continue
            if j > 0 and (sc.meta or {}).get("repeat"):  # "ซ้ำ:" = ใช้ภาพช็อตของฉากก่อนหน้า มุมกล้องใหม่ ไม่เสียเครดิต
                items.append({"index": idx, "kind": "reuse", "tool": None, "clip": ci, "scene": j + 1, "from": j,
                              "target": f"(ภาพเดียวกับฉาก {j})", "params": {}})
                idx += 1
                continue
            layout = sc.meta.get("layout", "")
            circle = "วงกลม" in layout or (style == "collage" and "เต็ม" not in layout and j % 3 == 1)
            if style == "collage":
                ar = "1:1" if circle or fmt == "9x16" else "3:2"
            else:
                ar = "9:16" if fmt == "9x16" else "16:9"
            subject = (metas[j].get("prompt") if j < len(metas) and isinstance(metas[j], dict) and metas[j].get("prompt") else sc.desc)
            who = chars_in(sc, p, (brief.get("hero"), brief.get("side")))
            shot = SHOT_EN.get((sc.meta or {}).get("shot", "").strip(), (sc.meta or {}).get("shot") or SHOT_CYCLE[j % len(SHOT_CYCLE)])
            action = (sc.meta or {}).get("action", "")
            people = "; ".join(f"{c['name']}: " + ", ".join(x for x in (c.get("look"), c.get("outfit")) if x) for c in who)
            prompt = (f"{shot}. {subject}" + (f". {action}" if action else "") +
                      (f". Characters (match the attached reference sheets exactly): {people}" if people else
                       (f". Characters: {chars}" if chars else "")) + f". {STYLE_SUFFIX.get(style, '')}")
            if circle:
                prompt += ". Single person, waist-up portrait, facing camera, plain light background (for background removal)"
            refs = [{"role": "image_references", "value": c["sheet"]["job_id"]} for c in who if (c.get("sheet") or {}).get("job_id")]
            missing_sheet = [c["name"] for c in who if not (c.get("sheet") or {}).get("job_id")]
            params = {"model": "gpt_image_2_6", "prompt": prompt, "aspect_ratio": ar}
            if refs:
                params["medias"] = refs
            items.append({"index": idx, "kind": "image", "tool": "generate_image_batch", "clip": ci, "scene": j + 1,
                          "target": f"media/clip{ci}-scene{j + 1}" + (".png" if circle else ".jpg"),
                          "cutout": circle, "characters": [c["name"] for c in who], "params": params})
            if missing_sheet and p.get("characters"):
                print(f"⚠ คลิป {ci} ฉาก {j + 1}: ยังไม่มี sheet ของ {', '.join(missing_sheet)} หน้าตาอาจไม่ตรงกันทุกช็อต "
                      f"(ทำ --characters ก่อน)", file=sys.stderr)
            idx += 1
    if a.music:
        longest = max(bs.build(c["script"], p.get("speed", "normal"), c.get("timings"))[2] for c in p["clips"])
        items.append({"index": idx, "kind": "music", "tool": "generate_audio", "target": "audio/music-higgsfield.mp3",
                      "params": {"model": "elevenlabs_music_v2_5", "prompt": MUSIC_PROMPTS.get(p.get("music", "doc"), MUSIC_PROMPTS["doc"]),
                                 "duration": int(longest + 2), "force_instrumental": True}})
    est = 0.0
    for it in items:
        m = it["params"].get("model", "")
        est += VIDEO_COST_PER_SEC.get(m, 0) * it["params"].get("duration", 0) if it["kind"] == "motion" else COST.get(m, 0)
    plan = {"project": os.path.abspath(a.project), "items": items, "estimatedCredits": round(est, 2),
            "notes": ["เช็กราคาด้วย estimate_audio_cost / estimate_image_cost / estimate_video_cost แล้วขออนุมัติก่อนสร้าง (เกินงบใน production.config.json ต้องถามผู้ใช้)",
                      "character: เขียน prompt ตามเวิร์กโฟลว์ character-sheet ด้วย entry + sheetStyle (หรือใช้ budgetParams เมื่อผู้ใช้เลือกโหมดประหยัด) ดูรูปทุกภาพก่อนไปต่อ",
                      "image: medias ใส่ sheet ของตัวละครในช็อตแล้ว ส่งด้วย generate_image_batch ได้ทันที · motion: start_image คือ job_id ของภาพช็อต",
                      "reuse (ฉากที่มี ซ้ำ:): ไม่ต้องส่งให้ Higgsfield ไม่เสียเครดิต fetch จะใส่ภาพของฉากก่อนหน้าให้เอง",
                      "เก็บผล jobs_wait เป็น {\"index\": {\"url\": ..., \"job_id\": ...}} แล้ว fetch (ระยะถัดไปใช้ job_id ต่อ)",
                      "ภาพที่ cutout=true: หลังสร้างเสร็จให้ remove_background (media_type=image) แล้วใช้ไฟล์ PNG ที่ได้",
                      "ส่งภาพหลายฉากพร้อมกันด้วย generate_image_batch (ครั้งละไม่เกิน 12) แล้ว jobs_wait"]}
    json.dump(plan, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


def set_scene_credit(clip, scene_no, credit):
    """เติม/แทน `| เครดิต: ...` ในบรรทัดฉากที่ scene_no ของสคริปต์ (ภาพ AI ต้องติดป้ายเสมอ)"""
    lines, k = clip["script"].splitlines(), 0
    for i, line in enumerate(lines):
        if re.match(r"^\s*\[\s*ฉาก\s*[:：]", line):
            k += 1
            if k == scene_no:
                body = re.sub(r"\s*\|\s*เครดิต\s*[:：][^|\]]*", "", line.strip()[1:-1])
                lines[i] = f"[{body} | เครดิต: {credit}]"
                break
    clip["script"] = "\n".join(lines)


def cmd_fetch(a):
    plan = json.load(open(a.plan, encoding="utf-8"))
    res = json.load(open(a.results, encoding="utf-8"))
    p_path = plan["project"]
    p = json.load(open(p_path, encoding="utf-8"))
    pdir = os.path.dirname(p_path)
    for it in plan["items"]:
        if it["kind"] == "reuse":  # ฉาก "ซ้ำ:" รับภาพนิ่งของฉากก่อนหน้า (ทำตามลำดับ จึงได้ภาพที่เพิ่ง fetch)
            metas = p["clips"][it["clip"] - 1].setdefault("scenes", [])
            while len(metas) < it["scene"]:
                metas.append({})
            src = metas[it["from"] - 1] if isinstance(metas[it["from"] - 1], dict) else {}
            still = src.get("still") or src.get("media")
            if still:
                metas[it["scene"] - 1].update({"media": still, "still": still, "job_id": src.get("job_id"),
                                               "generator": src.get("generator", "higgsfield")})
                if str(src.get("generator") or "").startswith("higgsfield"):
                    set_scene_credit(p["clips"][it["clip"] - 1], it["scene"], "ภาพสร้างด้วย AI (Higgsfield)")
                print(f"✔ [{it['index']}] reuse ฉาก {it['from']} → ฉาก {it['scene']}")
            continue
        got = res.get(str(it["index"]))
        if not got:
            continue
        url, job = (got.get("url"), got.get("job_id")) if isinstance(got, dict) else (got, None)
        if not url:
            continue
        dst = os.path.join(pdir, it["target"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "SocialVideoStudio/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as fh:
            fh.write(r.read())
        if it["kind"] == "character":
            for c in p.get("characters") or []:
                if c.get("name") == it["character"]:
                    c["sheet"] = {"file": it["target"], "job_id": job, "url": url}
        elif it["kind"] in ("image", "motion"):
            metas = p["clips"][it["clip"] - 1].setdefault("scenes", [])
            while len(metas) < it["scene"]:
                metas.append({})
            m = metas[it["scene"] - 1]
            set_scene_credit(p["clips"][it["clip"] - 1], it["scene"], "ภาพสร้างด้วย AI (Higgsfield)")
            if it["kind"] == "image":
                m.update({"media": it["target"], "still": it["target"], "prompt": it["params"]["prompt"],
                          "generator": "higgsfield", "job_id": job})
            else:  # วิดีโอจากภาพช็อต: ใช้เป็นสื่อของฉาก (ภาพนิ่งเดิมเก็บไว้ที่ still)
                m.update({"media": it["target"], "video": it["target"], "video_job_id": job, "generator": "higgsfield"})
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
    pl.add_argument("--images", choices=["none", "missing", "all", "hero"],
                    help="ภาพต่อช็อต (ค่าเริ่มต้น missing แต่ถ้าสั่ง --characters หรือ --motion จะเป็น none)")
    pl.add_argument("--music", action="store_true")
    pl.add_argument("--characters", action="store_true", help="ระยะ 1: character sheet ของตัวละครใน project.characters")
    pl.add_argument("--motion", default="none", choices=["none", "marked", "key", "all"],
                    help="ระยะ 3: วิดีโอจากภาพช็อต marked = ฉากที่มี 'เคลื่อนไหว:' · key = ฉากแรก + marked · all = ทุกฉาก")
    pl.add_argument("--redo", action="store_true", help="ทำซ้ำแม้มีผลเดิมแล้ว")
    fe = sub.add_parser("fetch")
    fe.add_argument("plan")
    fe.add_argument("results")
    a = ap.parse_args(argv)
    return cmd_plan(a) if a.cmd == "plan" else cmd_fetch(a)


if __name__ == "__main__":
    sys.exit(main())
