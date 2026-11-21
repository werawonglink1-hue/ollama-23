"""check_i2v.py — ตรวจวิดีโอที่ AI สร้างจากภาพช็อต (image-to-video) ก่อนนำไปตัดต่อ

ตรวจตาม "Animation Requirements" ของมาตรฐาน CINEMATIC 3D ANIMATION — IMAGE TO VIDEO:
  ✔ สัดส่วนภาพตรงรูปแบบ (9:16 / 16:9)       ✔ ไม่มีการตัดฉาก/ภาพกระโดดกลางช็อต (No sudden scene changes)
  ✔ ไม่มีจอดำ                                ✔ ภาพขยับจริง ไม่ค้างนิ่ง (Smooth continuous motion)
และทำภาพเทียบ (เฟรมแรก กลาง ท้าย + หน้าตรงจาก character sheet) ให้ผู้ตรวจ "เปิดดูจริง" ว่า
หน้า ทรงผม เสื้อผ้า ตรงเดิม ไม่มีนิ้วเกิน/แขนขาซ้ำ ไม่มีตัวหนังสือ (ข้อนี้เครื่องตรวจแทนคนไม่ได้)

ใช้:
  python3 check_i2v.py project.json [--clip 1] [--out qc]        ตรวจทุกฉากที่มี video ใน project.json
  python3 check_i2v.py --video a.mp4 [--sheet sheet.png] [--format 9x16]
ออก 0 = ผ่าน · 1 = ไม่ผ่าน (ส่งกลับแผนกภาพ สร้างใหม่ได้เมื่อผู้ใช้อนุมัติเครดิตเท่านั้น ห้ามสร้างซ้ำเอง)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

CUT_SCORE = 0.18      # คะแนนเปลี่ยนฉากขั้นต่ำของ ffmpeg (0–1) ที่ถือว่าภาพกระโดด (ต้องสูงผิดปกติเทียบทั้งคลิปด้วย)
MAX_BLACK = 0.30      # วินาที
FREEZE_NOISE = 0.002  # ภาพต่างกันน้อยกว่านี้ถือว่าค้าง
MAX_FREEZE = 1.5      # วินาที ค้างนานกว่านี้ = ไม่ขยับ
ASPECT = {"9x16": 9 / 16, "16x9": 16 / 9}


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


def probe(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate:format=duration", "-of", "json", path])
    d = json.loads(r.stdout or "{}")
    st = (d.get("streams") or [{}])[0]
    num, _, den = (st.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {"width": st.get("width", 0), "height": st.get("height", 0), "fps": round(fps, 2),
            "duration": round(float((d.get("format") or {}).get("duration") or 0), 2)}


def scene_cuts(path):
    """ภาพกระโดด = คะแนนเปลี่ยนฉากของเฟรมนั้นสูงผิดปกติเทียบกับทั้งคลิป (≥ CUT_SCORE และ ≥ 8 เท่าค่ามัธยฐาน)
    ช็อตที่ขยับต่อเนื่องได้คะแนนราว 0.01–0.05 ต่อเฟรม การตัดฉากจริงได้ 0.25 ขึ้นไป"""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-an", "-vf",
             "select='gte(scene,0)',metadata=print:key=lavfi.scene_score", "-f", "null", "-"])
    pairs = re.findall(r"pts_time:([0-9.]+)[^\n]*\n[^\n]*lavfi\.scene_score=([0-9.]+)", r.stderr)
    scores = [(float(t), float(s)) for t, s in pairs]
    if len(scores) < 3:
        return []
    vals = sorted(s for _, s in scores[1:])  # เฟรมแรกไม่มีเฟรมก่อนหน้า
    median = vals[len(vals) // 2]
    return [round(t, 2) for t, s in scores[1:] if s >= max(CUT_SCORE, 8 * median)]


def black_spans(path):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-an", "-vf",
             f"blackdetect=d={MAX_BLACK}:pix_th=0.10", "-f", "null", "-"])
    return [float(x) for x in re.findall(r"black_duration:([0-9.]+)", r.stderr)]


def freeze_spans(path, duration):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-an", "-vf",
             f"freezedetect=n={FREEZE_NOISE}:d={MAX_FREEZE}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"freeze_start: ?([0-9.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"freeze_end: ?([0-9.]+)", r.stderr)]
    # ค้างไปจนจบคลิป ffmpeg พิมพ์แค่ freeze_start (ไม่มี end) → นับถึงท้ายคลิป
    return [(ends[i] if i < len(ends) else duration) - s for i, s in enumerate(starts)]


def contact_sheet(path, dur, sheet, out_jpg, h=640):
    """เฟรมแรก/กลาง/ท้าย + หน้าตรงจาก character sheet (แผงขวา) เรียงแนวนอน ให้คนเปิดดูเทียบ"""
    times = [0.05, max(0.1, dur / 2), max(0.1, dur - 0.15)]
    inputs, chains = [], []
    for i, t in enumerate(times):
        inputs += ["-ss", f"{t:.2f}", "-i", path]
        chains.append(f"[{i}:v]scale=-2:{h},setsar=1[f{i}]")
    labels = "".join(f"[f{i}]" for i in range(len(times)))
    n = len(times)
    if sheet and os.path.exists(sheet):
        inputs += ["-i", sheet]
        chains.append(f"[{n}:v]crop=iw*0.435:ih:iw*0.565:0,scale=-2:{h},setsar=1[ref]")
        labels += "[ref]"
        n += 1
    fc = ";".join(chains) + f";{labels}hstack=inputs={n}[o]"
    os.makedirs(os.path.dirname(out_jpg) or ".", exist_ok=True)
    r = run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[o]", "-frames:v", "1",
             "-q:v", "4", out_jpg])
    return out_jpg if r.returncode == 0 else None


def check_one(path, fmt="9x16", sheet=None, out_jpg=None):
    res = {"video": path, "checks": [], "ok": True}

    def add(name, ok, msg, level="fail"):
        res["checks"].append({"name": name, "ok": ok, "level": level, "msg": msg})
        if not ok and level == "fail":
            res["ok"] = False

    if not os.path.exists(path):
        add("exists", False, "ไม่พบไฟล์วิดีโอ")
        return res
    m = probe(path)
    res["meta"] = m
    if not m["width"] or m["duration"] <= 0:
        add("open", False, "เปิดไฟล์ไม่ได้หรือไม่มีภาพ")
        return res
    want = ASPECT.get(fmt)
    ar = m["width"] / m["height"]
    add("aspect", want is None or abs(ar - want) / want < 0.03, f"สัดส่วน {m['width']}x{m['height']} ({fmt})")
    cuts = scene_cuts(path)
    add("cuts", not cuts, "ไม่มีภาพกระโดด/ตัดฉาก" if not cuts else f"ภาพกระโดด/ตัดฉากที่ {cuts} วิ (ห้าม sudden scene change)")
    blk = black_spans(path)
    add("black", not blk, "ไม่มีจอดำ" if not blk else f"จอดำ {sum(blk):.2f} วิ")
    frz = freeze_spans(path, m["duration"])
    still = sum(frz) / m["duration"] if m["duration"] else 0
    add("motion", still < 0.5, "ภาพขยับต่อเนื่อง" if not frz else f"ภาพค้าง {sum(frz):.1f} วิ จาก {m['duration']} วิ",
        "fail" if still >= 0.5 else "warn")
    add("fps", m["fps"] >= 23, f"{m['fps']} fps", "warn")
    if out_jpg:
        res["review"] = contact_sheet(path, m["duration"], sheet, out_jpg)
    return res


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?")
    ap.add_argument("--clip", type=int, default=1)
    ap.add_argument("--video", action="append", help="ตรวจไฟล์ตรง ๆ (ใส่ได้หลายครั้ง)")
    ap.add_argument("--sheet", help="character sheet สำหรับภาพเทียบ")
    ap.add_argument("--format", default=None)
    ap.add_argument("--out", default="qc")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    jobs = []
    if a.project:
        p = json.load(open(a.project, encoding="utf-8"))
        pdir = os.path.dirname(os.path.abspath(a.project))
        fmt = a.format or (p.get("formats") or ["9x16"])[0]
        sheets = [os.path.join(pdir, c["sheet"]["file"]) for c in p.get("characters") or []
                  if (c.get("sheet") or {}).get("file")]
        clip = p["clips"][a.clip - 1]
        for j, s in enumerate(clip.get("scenes") or []):
            if isinstance(s, dict) and s.get("video"):
                jobs.append((os.path.join(pdir, s["video"]), fmt, a.sheet or (sheets[0] if sheets else None),
                             os.path.join(pdir, a.out, f"clip{a.clip}-scene{j + 1}-i2v.jpg"), j + 1))
    for k, v in enumerate(a.video or []):
        jobs.append((v, a.format or "9x16", a.sheet, os.path.join(a.out, f"i2v-{k + 1}.jpg"), None))
    if not jobs:
        print("ไม่มีวิดีโอให้ตรวจ (ฉากที่มี video ใน project.json หรือ --video)")
        return 0
    results = [dict(check_one(v, f, sh, jpg), scene=sc) for v, f, sh, jpg, sc in jobs]
    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    else:
        for r in results:
            head = f"ฉาก {r['scene']} · " if r.get("scene") else ""
            print(("✔ ผ่าน" if r["ok"] else "✖ ไม่ผ่าน") + f" · {head}{os.path.basename(r['video'])}")
            for c in r["checks"]:
                mark = "✔" if c["ok"] else ("✖" if c["level"] == "fail" else "⚠")
                print(f"  {mark} {c['msg']}")
            if r.get("review"):
                print(f"  ▸ เปิดดูภาพเทียบ: {r['review']} (หน้า ทรงผม ชุด นิ้วมือ ตัวหนังสือ)")
        bad = [r for r in results if not r["ok"]]
        if bad:
            print("ส่งกลับแผนก: ภาพ (สร้างช็อตนั้นใหม่ได้เมื่อผู้ใช้อนุมัติเครดิตเท่านั้น)")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
