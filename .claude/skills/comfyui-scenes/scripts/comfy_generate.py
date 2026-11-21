#!/usr/bin/env python3
"""สร้างภาพประกอบฉากด้วย ComfyUI ที่รันในเครื่องตัวเอง (ฟรี ใช้ GPU ของเรา) ผ่าน HTTP API

  one      สร้างภาพเดียวจาก prompt
  project  สร้างภาพให้ทุกฉากที่ยังไม่มีสื่อใน project.json แล้วใส่ path กลับลงไป

ตัวอย่าง:
  python3 comfy_generate.py one "Thai village at dawn, editorial collage" --size 1024x1024 --out media/test.png
  python3 comfy_generate.py project work/runner/project.json --clip 1 --ckpt sd_xl_base_1.0.safetensors
  python3 comfy_generate.py project project.json --workflow my_flux_api.json   # workflow ที่ Export (API) จาก ComfyUI

workflow ของตัวเอง: ใน ComfyUI กด Workflow → Export (API) แล้วแทนค่าในไฟล์ด้วย {{PROMPT}} {{NEGATIVE}}
"{{SEED}}" "{{WIDTH}}" "{{HEIGHT}}" "{{STEPS}}" (ตัวเลขใส่ในเครื่องหมายคำพูดได้ สคริปต์แปลงเป็นตัวเลขให้)
ไม่ใส่ --workflow จะใช้ workflow มาตรฐาน (CheckpointLoaderSimple → KSampler → SaveImage) ใช้ได้กับ checkpoint SD1.5/SDXL
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "social-video-studio", "scripts"))

STYLE_SUFFIX = {  # ตรงกับ references/styles.md ของ social-video-studio
    "collage": "editorial documentary photo, archival feel, natural light, sharp subject, plain background",
    "pastel3d": "soft low-poly 3D diorama, Thai neighborhood, pastel pink and lavender sky, warm sunset light, toy-like characters",
    "kinetic": "claymation 3D characters, bold saturated colors, playful",
    "watercolor": "warm watercolor storybook illustration, paper texture, soft edges",
    "anime-dusk": "anime background art, golden hour, volumetric light, nostalgic",
    "papercut": "layered paper-cut craft, minimal shapes, soft shadows",
    "neon-night": "quiet night city street, glowing neon, deep blue, bokeh",
    "film": "35mm film photo, warm grain, nostalgic, soft focus",
    "cinematic": "cinematic realism, photorealistic film still, natural lighting, 35mm anamorphic lens, shallow depth of field, film color grading",
}
NEGATIVE = "text, watermark, logo, signature, blurry, deformed hands, extra fingers, lowres"


def default_workflow(ckpt):
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": "{{WIDTH}}", "height": "{{HEIGHT}}", "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{PROMPT}}", "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{NEGATIVE}}", "clip": ["4", 1]}},
        "3": {"class_type": "KSampler", "inputs": {"seed": "{{SEED}}", "steps": "{{STEPS}}", "cfg": 6.5, "sampler_name": "dpmpp_2m",
                                                   "scheduler": "karras", "denoise": 1, "model": ["4", 0], "positive": ["6", 0],
                                                   "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "studio", "images": ["8", 0]}},
    }


def fill(workflow, values):
    """แทน {{KEY}} ทั้งในข้อความและค่าตัวเลข ("{{SEED}}" → 123)"""
    text = json.dumps(workflow, ensure_ascii=False)
    for k, v in values.items():
        if isinstance(v, (int, float)):
            text = text.replace(f'"{{{{{k}}}}}"', json.dumps(v))
        text = text.replace(f"{{{{{k}}}}}", json.dumps(str(v), ensure_ascii=False)[1:-1])
    left = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if left:
        raise SystemExit(f"workflow ยังมีตัวแปรที่ไม่รู้จัก: {sorted(set(left))}")
    return json.loads(text)


def _req(server, path, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(server.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def run(server, workflow, out_path, timeout=600):
    """ส่ง workflow → รอผลใน /history → ดาวน์โหลดภาพแรกผ่าน /view"""
    try:
        resp = json.loads(_req(server, "/prompt", {"prompt": workflow, "client_id": str(uuid.uuid4())}))
    except OSError as e:
        raise SystemExit(f"ติดต่อ ComfyUI ที่ {server} ไม่ได้ ({e}) เปิด ComfyUI ก่อน (python main.py --listen 127.0.0.1 --port 8188)")
    if resp.get("error") or resp.get("node_errors"):
        raise SystemExit(f"ComfyUI ไม่รับ workflow: {json.dumps(resp.get('error') or resp.get('node_errors'), ensure_ascii=False)[:600]}")
    pid, t0 = resp["prompt_id"], time.time()
    while time.time() - t0 < timeout:
        hist = json.loads(_req(server, f"/history/{pid}")).get(pid)
        if hist and hist.get("outputs"):
            for node in hist["outputs"].values():
                for img in node.get("images", []):
                    q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
                    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                    with open(out_path, "wb") as fh:
                        fh.write(_req(server, "/view?" + q, timeout=120))
                    return out_path
        if hist and (hist.get("status") or {}).get("status_str") == "error":
            raise SystemExit(f"ComfyUI ทำงานผิดพลาด: {json.dumps(hist.get('status'), ensure_ascii=False)[:600]}")
        time.sleep(1.0)
    raise SystemExit("รอ ComfyUI นานเกินไป")


def load_workflow(a):
    if a.workflow:
        return json.load(open(a.workflow, encoding="utf-8"))
    return default_workflow(a.ckpt)


def cmd_one(a):
    w, h = (int(x) for x in a.size.lower().split("x"))
    wf = fill(load_workflow(a), {"PROMPT": a.prompt, "NEGATIVE": a.negative, "SEED": a.seed or random.randint(1, 2**31),
                                 "WIDTH": w, "HEIGHT": h, "STEPS": a.steps})
    print("✔", run(a.server, wf, a.out))
    return 0


def scene_size(style, layout_circle, fmt):
    if style == "collage":  # หน้าต่างภาพในการ์ดเกือบจัตุรัส (แนวตั้ง) / 3:2 (แนวนอน); วงกลม = จัตุรัส
        return (1024, 1024) if layout_circle or fmt == "9x16" else (1216, 832)
    return (832, 1472) if fmt == "9x16" else (1472, 832)


def cmd_project(a):
    import build_subs as bs
    p = json.load(open(a.project, encoding="utf-8"))
    pdir = os.path.dirname(os.path.abspath(a.project))
    style = p.get("visualStyle", "collage")
    fmt = (p.get("formats") or ["9x16"])[0]
    chars = ", ".join(x for x in [(p.get("brief") or {}).get("hero"), (p.get("brief") or {}).get("side")] if x)
    clips = [a.clip] if a.clip else range(1, len(p["clips"]) + 1)
    done = 0
    for ci in clips:
        clip = p["clips"][ci - 1]
        scenes, _ = bs.parse_script(clip["script"])
        metas = clip.setdefault("scenes", [])
        while len(metas) < len(scenes):
            metas.append({})
        for j, sc in enumerate(scenes):
            if metas[j].get("media") and not a.overwrite:
                continue
            layout = sc.meta.get("layout", "")
            circle = "วงกลม" in layout or (style == "collage" and "เต็ม" not in layout and j % 3 == 1)
            w, h = scene_size(style, circle, fmt)
            subject = metas[j].get("prompt") or sc.desc
            prompt = f"{subject}. {STYLE_SUFFIX.get(style, '')}" + (f", characters: {chars}" if chars else "")
            if circle:
                prompt += ", single person portrait, centered, plain light background"
            rel = os.path.join("media", f"clip{ci}-scene{j + 1}.png")
            wf = fill(load_workflow(a), {"PROMPT": prompt, "NEGATIVE": a.negative, "SEED": (a.seed or 1000) + ci * 100 + j,
                                         "WIDTH": w, "HEIGHT": h, "STEPS": a.steps})
            run(a.server, wf, os.path.join(pdir, rel))
            metas[j]["media"], metas[j]["prompt"] = rel, prompt
            done += 1
            print(f"✔ คลิป {ci} ฉาก {j + 1} → {rel} ({w}×{h})")
            json.dump(p, open(a.project, "w", encoding="utf-8"), ensure_ascii=False, indent=2)  # บันทึกทุกภาพ เผื่อหยุดกลางทาง
    print(f"เสร็จ {done} ภาพ")
    return 0


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--workflow")
    ap.add_argument("--ckpt", default="sd_xl_base_1.0.safetensors")
    ap.add_argument("--steps", type=int, default=28)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--negative", default=NEGATIVE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("one")
    o.add_argument("prompt")
    o.add_argument("--size", default="1024x1024")
    o.add_argument("--out", required=True)
    pr = sub.add_parser("project")
    pr.add_argument("project")
    pr.add_argument("--clip", type=int)
    pr.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    return cmd_one(a) if a.cmd == "one" else cmd_project(a)


if __name__ == "__main__":
    sys.exit(main())
