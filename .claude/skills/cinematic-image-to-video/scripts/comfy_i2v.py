"""comfy_i2v.py — วิดีโอจากภาพ (image-to-video) ด้วย ComfyUI บนเครื่องตัวเอง ฟรี ใช้ GPU ของเรา ไม่เชื่อม Higgsfield

ค่าเริ่มต้นใช้ workflow Wan 2.2 TI2V-5B (โมเดล Apache-2.0 ใช้เชิงพาณิชย์ได้ · 720p 24 fps · GPU ~8–12 GB ขึ้นไป)
ไฟล์ `references/comfyui_wan22_ti2v_5b_api.json` · ใช้ workflow ของตัวเองได้ (ComfyUI › Workflow › Export (API))
โดยใส่ตัวแทน {{IMAGE}} {{PROMPT}} {{NEGATIVE}} {{SEED}} {{LENGTH}} {{FPS}} {{WIDTH}} {{HEIGHT}}
หรือไม่ใส่ก็ได้ สคริปต์จะหาโหนดเอง: LoadImage, CLIPTextEncode ที่ต่อเข้า positive/negative, seed, length, fps, width/height

prompt ใช้มาตรฐานเดียวกับ Higgsfield (i2v_prompt.py) จึงได้การแสดง กะพริบตา สีหน้า กล้อง ตามสเปกของช่อง
เรียกผ่าน i2v_free.py --engine comfyui (ทำทุกฉากใน project.json) หรือใช้ run_one() ตรง ๆ
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKFLOW = os.path.join(HERE, "..", "references", "comfyui_wan22_ti2v_5b_api.json")
NEGATIVE = ("blurry, low quality, distorted face, deformed body, extra fingers, extra limbs, duplicated limbs, mutated hands, "
            "text, subtitles, captions, watermark, logo, sudden scene change, cut, flicker, jitter, frozen frame, "
            "new objects appearing, inconsistent character, different outfit, different hairstyle")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv", ".gif", ".webp")


def wan_length(seconds, fps, max_frames=121):
    """จำนวนเฟรมแบบ Wan (4k+1) ที่ยาวพอ ไม่เกิน max_frames"""
    frames = min(max_frames, max(5, round(seconds * fps)))
    return 4 * math.ceil((frames - 1) / 4) + 1


def fill(obj, values):
    """แทน {{KEY}}: ทั้งสตริงเป็นตัวแทนเดียว → ใส่ค่าตามชนิด (ตัวเลขเป็นตัวเลข) · อยู่ในข้อความ → แทนเป็นข้อความ"""
    if isinstance(obj, dict):
        return {k: fill(v, values) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fill(v, values) for v in obj]
    if isinstance(obj, str):
        m = re.fullmatch(r"\{\{(\w+)\}\}", obj.strip())
        if m and m.group(1) in values:
            return values[m.group(1)]
        return re.sub(r"\{\{(\w+)\}\}", lambda mm: str(values.get(mm.group(1), mm.group(0))), obj)
    return obj


def has_placeholders(wf):
    return "{{" in json.dumps(wf)


def autopatch(wf, v):
    """workflow ที่ไม่มีตัวแทน: หาโหนดตามชนิดแล้วใส่ค่า"""
    pos_ids, neg_ids = set(), set()
    for node in wf.values():
        ins = node.get("inputs", {})
        if isinstance(ins.get("positive"), list):
            pos_ids.add(str(ins["positive"][0]))
        if isinstance(ins.get("negative"), list):
            neg_ids.add(str(ins["negative"][0]))
    for nid, node in wf.items():
        ct, ins = node.get("class_type", ""), node.setdefault("inputs", {})
        if ct == "LoadImage":
            ins["image"] = v["IMAGE"]
        elif ct.startswith("CLIPTextEncode") and "text" in ins:
            ins["text"] = v["NEGATIVE"] if nid in neg_ids else v["PROMPT"] if (nid in pos_ids or not pos_ids) else ins["text"]
        for key in ("seed", "noise_seed"):
            if key in ins and not isinstance(ins[key], list):
                ins[key] = v["SEED"]
        if "length" in ins and not isinstance(ins["length"], list):
            ins["length"] = v["LENGTH"]
            for k, val in (("width", v["WIDTH"]), ("height", v["HEIGHT"])):
                if k in ins and not isinstance(ins[k], list):
                    ins[k] = val
        for key in ("fps", "frame_rate"):
            if key in ins and not isinstance(ins[key], list):
                ins[key] = v["FPS"]
    return wf


def _req(server, path, data=None, headers=None, timeout=30):
    req = urllib.request.Request(server.rstrip("/") + path, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def upload_image(server, path):
    boundary = uuid.uuid4().hex
    name = f"i2v_{uuid.uuid4().hex[:8]}{os.path.splitext(path)[1] or '.png'}"
    body = io.BytesIO()
    for field, val in (("overwrite", "true"), ("type", "input")):
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{val}\r\n'.encode())
    body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
               f"Content-Type: application/octet-stream\r\n\r\n".encode())
    body.write(open(path, "rb").read())
    body.write(f"\r\n--{boundary}--\r\n".encode())
    resp = json.loads(_req(server, "/upload/image", body.getvalue(),
                           {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=120))
    return (resp.get("subfolder") + "/" if resp.get("subfolder") else "") + resp["name"]


def to_mp4(src, dst, fps):
    """ผลเป็น .webp/.gif เคลื่อนไหว → mp4 (ffmpeg อ่าน animated webp ไม่ได้ จึงใช้ Pillow แตกเฟรม)"""
    if src.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
        if src != dst:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", dst],
                           check=True)
        return dst
    from PIL import Image, ImageSequence
    im = Image.open(src)
    frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    w, h = frames[0].size
    w2, h2 = w - w % 2, h - h % 2
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w2}x{h2}", "-r", str(fps),
                          "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", dst], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.crop((0, 0, w2, h2)).tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError("แปลงวิดีโอไม่สำเร็จ")
    return dst


def run_one(server, image_path, prompt, out_path, seconds=5.0, fps=24, size=(704, 1280), seed=1234,
            workflow_path=None, negative=NEGATIVE, max_frames=121, timeout=1800, poll=3.0):
    """ส่งภาพ 1 ช็อต → รอ ComfyUI → บันทึกวิดีโอ mp4 ที่ out_path"""
    wf = json.load(open(workflow_path or DEFAULT_WORKFLOW, encoding="utf-8"))
    try:
        image = upload_image(server, image_path)
    except OSError as e:
        raise SystemExit(f"ติดต่อ ComfyUI ที่ {server} ไม่ได้ ({e}) — เปิด ComfyUI ก่อน (python main.py --listen 127.0.0.1 --port 8188)")
    values = {"IMAGE": image, "PROMPT": prompt, "NEGATIVE": negative, "SEED": int(seed), "FPS": fps,
              "LENGTH": wan_length(seconds, fps, max_frames), "WIDTH": size[0], "HEIGHT": size[1]}
    wf = fill(wf, values) if has_placeholders(wf) else autopatch(wf, values)
    resp = json.loads(_req(server, "/prompt", json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
                           {"Content-Type": "application/json"}))
    if resp.get("node_errors"):
        raise RuntimeError(f"ComfyUI ไม่รับ workflow: {json.dumps(resp['node_errors'], ensure_ascii=False)[:600]}")
    pid, t0 = resp["prompt_id"], time.time()
    while time.time() - t0 < timeout:
        hist = json.loads(_req(server, f"/history/{pid}")).get(pid)
        if hist:
            status = (hist.get("status") or {}).get("status_str")
            if status == "error":
                raise RuntimeError(f"ComfyUI ทำงานผิดพลาด: {json.dumps(hist.get('status'), ensure_ascii=False)[:600]}")
            files = [f for out in (hist.get("outputs") or {}).values() for lst in out.values() if isinstance(lst, list)
                     for f in lst if isinstance(f, dict) and str(f.get("filename", "")).lower().endswith(VIDEO_EXT)]
            if files:
                f = files[0]
                q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                            "type": f.get("type", "output")})
                raw = out_path + ".download" + os.path.splitext(f["filename"])[1].lower()  # ลงท้ายด้วยนามสกุลจริง
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                with open(raw, "wb") as fh:
                    fh.write(_req(server, "/view?" + q, timeout=300))
                try:
                    return to_mp4(raw, out_path, fps)
                finally:
                    if os.path.exists(raw) and raw != out_path:
                        os.remove(raw)
            if status == "success":
                raise RuntimeError("ComfyUI ทำเสร็จแต่ไม่มีไฟล์วิดีโอ (workflow ต้องจบด้วย SaveVideo / VHS_VideoCombine / SaveAnimatedWEBP)")
        time.sleep(poll)
    raise TimeoutError(f"รอ ComfyUI เกิน {timeout} วินาที")
