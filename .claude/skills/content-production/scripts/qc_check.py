#!/usr/bin/env python3
"""ตรวจคุณภาพคลิปก่อนส่งเข้าระบบอนุมัติ: ผ่าน/ไม่ผ่าน พร้อมแผนกที่ต้องแก้ (returnTo) สำหรับส่งกลับอัตโนมัติ

  python3 qc_check.py out/1_ชื่อ_9x16.mp4 --project work/ORD-…/clip1/project.json --clip 1
  python3 qc_check.py out/clip.mp4 --json            # ผลเป็น JSON (เขียน <ไฟล์>.qc.json คู่กันเสมอ)

ตรวจไฟล์: เปิดได้ มีภาพ+เสียง ขนาดตรงรูปแบบ fps 23–60 · ความดัง (EBU R128) และ true peak · ช่วงเงียบกลางคลิป · จอดำ · ภาพค้าง
ตรวจโปรเจกต์ (ถ้าใส่ --project): ความยาวตรงสคริปต์ · ซับเร็วเกิน/ทับกัน · ภาพซ้ำโดยไม่มีเหตุผล · ฉากไม่มีภาพ
· สิทธิ์ใช้สื่อ (ช่องหารายได้ห้าม NC/ND) · ภาพ AI ติดป้าย · เครดิตครบ
exit 0 = ผ่าน · 1 = ไม่ผ่าน (ดู returnTo) · 2 = ตรวจไม่ได้
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "social-video-studio", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "video-document-control", "scripts"))
SIZES = {"9x16": (1080, 1920), "16x9": (1920, 1080), "1x1": (1080, 1080), "4x5": (1080, 1350)}
QC_DEFAULT = {"loudnessTarget": -14, "loudnessTolerance": 2.5, "truePeakMax": -1.0, "maxSilence": 2.5,
              "maxBlack": 0.6, "maxFreeze": 6.0, "maxTooFast": 2}
DEPT_TH = {"visual": "ผลิตภาพ", "voice": "เสียง/ดนตรี", "edit": "ตัดต่อ", "creative": "ครีเอทีฟ"}


class QC:
    def __init__(self):
        self.checks = []

    def add(self, cid, ok, dept, msg, severity="fail"):
        self.checks.append({"id": cid, "ok": bool(ok), "severity": "info" if ok else severity, "dept": dept,
                            "message": msg})


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout or "{}")


def analyze(path, has_audio, q):
    """ผ่านไฟล์ครั้งเดียว: ความดัง/peak + ช่วงเงียบ (เสียง) และจอดำ/ภาพค้าง (ภาพ)"""
    parts, maps = [], []
    if has_audio:
        parts.append(f"[0:a]ebur128=peak=true,silencedetect=noise=-45dB:d={q['maxSilence']}[a]")
        maps += ["-map", "[a]"]
    parts.append(f"[0:v]blackdetect=d={q['maxBlack']}:pix_th=0.10,freezedetect=n=-60dB:d={q['maxFreeze']}[v]")
    maps += ["-map", "[v]"]
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", path, "-filter_complex", ";".join(parts), *maps,
                        "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    log = r.stderr
    m = {"integrated": None, "truePeak": None, "silences": [], "blacks": [], "freezes": []}
    tail = log[log.rfind("Summary:"):] if "Summary:" in log else ""
    x = re.search(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", tail)
    if x and x.group(1) != "-inf":
        m["integrated"] = float(x.group(1))
    x = re.search(r"True peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf)", tail)
    if x and x.group(1) != "-inf":
        m["truePeak"] = float(x.group(1))
    starts = [float(s) for s in re.findall(r"silence_start:\s*(-?[\d.]+)", log)]
    ends = [(float(e), float(d)) for e, d in re.findall(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", log)]
    for i, s in enumerate(starts):
        e, d = ends[i] if i < len(ends) else (None, None)
        m["silences"].append({"start": round(max(0.0, s), 2), "end": e, "dur": d})
    m["blacks"] = [{"start": float(a), "end": float(b), "dur": float(c)}
                   for a, b, c in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)", log)]
    fs = re.findall(r"freeze_start:\s*([\d.]+)", log)
    fd = re.findall(r"freeze_duration:\s*([\d.]+)", log)
    m["freezes"] = [{"start": float(s), "dur": float(fd[i]) if i < len(fd) else None} for i, s in enumerate(fs)]
    return m


def license_bad(lic):
    return bool(re.search(r"(^|[\s\-])(nc|nd)([\s\-]|$)|noncommercial|noderiv", (lic or "").lower()))


def check(path, a, cfg):
    q = {**QC_DEFAULT, **(cfg.get("qc") or {})}
    monetized = cfg.get("monetized", True)
    qc = QC()
    info = probe(path)
    if not info:
        qc.add("open", False, "edit", "เปิดไฟล์ไม่ได้ (ffprobe อ่านไม่ได้)")
        return qc, {}
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    au = next((s for s in streams if s.get("codec_type") == "audio"), None)
    dur = float((info.get("format") or {}).get("duration") or 0)
    qc.add("video", bool(v), "edit", "มีภาพวิดีโอ" if v else "ไม่มีภาพวิดีโอ")
    qc.add("audio", bool(au), "voice", "มีเสียง" if au else "ไม่มีเสียง")
    if not v:
        return qc, {"duration": dur}
    w, h = v.get("width"), v.get("height")
    fmt = a.format or next((k for k in SIZES if f"_{k}" in os.path.basename(path)), None)
    if fmt:
        qc.add("size", (w, h) == SIZES[fmt], "edit", f"ขนาด {w}x{h} " + ("ตรง" if (w, h) == SIZES[fmt] else f"ไม่ตรง {fmt} ({SIZES[fmt][0]}x{SIZES[fmt][1]})"))
    n, d = (v.get("r_frame_rate") or "0/1").split("/")
    fps = float(n) / float(d) if float(d) else 0
    qc.add("fps", 23 <= fps <= 61, "edit", f"fps {fps:.2f}" + ("" if 23 <= fps <= 61 else " (แพลตฟอร์มรับ 23–60)"))
    qc.add("codec", v.get("codec_name") == "h264" and (not au or au.get("codec_name") == "aac"), "edit",
           f"codec {v.get('codec_name')}/{(au or {}).get('codec_name')}", "warn")
    m = analyze(path, bool(au), q)
    m.update({"duration": round(dur, 2), "width": w, "height": h, "fps": round(fps, 2)})
    if au:
        il, tp = m["integrated"], m["truePeak"]
        if il is None:
            qc.add("loudness", False, "voice", "วัดความดังไม่ได้ (เสียงเงียบทั้งไฟล์?)")
        else:
            ok = abs(il - q["loudnessTarget"]) <= q["loudnessTolerance"]
            qc.add("loudness", ok, "voice", f"ความดัง {il:.1f} LUFS" + ("" if ok else f" (เป้า {q['loudnessTarget']}±{q['loudnessTolerance']})"))
        if tp is not None:
            qc.add("truepeak", tp <= q["truePeakMax"], "voice", f"true peak {tp:.1f} dBTP" +
                   ("" if tp <= q["truePeakMax"] else f" (เกิน {q['truePeakMax']} เสียงอาจแตกบนแพลตฟอร์ม)"))
        mid = [s for s in m["silences"] if s["start"] > 0.6 and (s["end"] or dur) < dur - 1.5]
        qc.add("silence", not mid, "voice", "ไม่มีช่วงเงียบนานกลางคลิป" if not mid else
               "เงียบนานเกินไป: " + ", ".join(f"{s['start']:.1f}–{(s['end'] or dur):.1f} วิ" for s in mid[:4]))
    qc.add("black", not m["blacks"], "visual", "ไม่มีจอดำ" if not m["blacks"] else
           "จอดำ: " + ", ".join(f"{b['start']:.1f}–{b['end']:.1f} วิ" for b in m["blacks"][:4]))
    qc.add("freeze", not m["freezes"], "visual", "ไม่มีภาพค้างนาน" if not m["freezes"] else
           "ภาพนิ่งค้างนาน (ฉากไม่มีการเคลื่อนไหว): " + ", ".join(f"{f['start']:.1f} วิ ({f['dur'] or '?'} วิ)" for f in m["freezes"][:4]),
           "warn")
    if a.project:
        check_project(a, cfg, q, qc, m, monetized)
    return qc, m


def check_project(a, cfg, q, qc, m, monetized):
    import build_subs as bs
    with open(a.project, encoding="utf-8") as fh:
        p = json.load(fh)
    pdir = os.path.dirname(os.path.abspath(a.project))
    clip = p["clips"][a.clip - 1]
    scenes, chunks, total = bs.build(clip["script"], p.get("speed", "normal"), clip.get("timings"))
    if clip.get("voice"):
        vpath = clip["voice"] if os.path.isabs(clip["voice"]) else os.path.join(pdir, clip["voice"])
        qc.add("voicefile", os.path.exists(vpath), "voice", "มีไฟล์เสียงพากย์" if os.path.exists(vpath) else f"ไม่พบไฟล์เสียง {clip['voice']}")
        timed = clip.get("timings") or []
        qc.add("timings", len(timed) == len(chunks), "voice", f"timings {len(timed)}/{len(chunks)} ท่อน" +
               ("" if len(timed) == len(chunks) else " (ซับไม่ตรงเสียง ให้รัน voice_align.py assemble ใหม่)"))
        over = [i + 1 for i in range(1, len(timed)) if timed[i]["start"] < timed[i - 1]["end"] - 0.05]
        qc.add("overlap", not over, "voice", "ซับไม่ทับกัน" if not over else f"ซับทับกันที่ท่อน {over[:6]}")
    fast = [w for w in bs.warnings(chunks) if w.startswith("TOO FAST")]
    qc.add("subspeed", len(fast) <= q["maxTooFast"], "creative",
           "ซับไม่เร็วเกิน" if not fast else f"ซับเร็วเกิน {len(fast)} ท่อน: " + "; ".join(x.split(":", 1)[1].strip() for x in fast[:3]),
           "fail" if len(fast) > q["maxTooFast"] else "warn")
    if abs(m["duration"] - total) > 1.2:
        qc.add("duration", False, "edit", f"ความยาววิดีโอ {m['duration']} วิ ไม่ตรงสคริปต์ ({total:.1f} วิ) เรนเดอร์ใหม่")
    metas = clip.get("scenes") or []
    medias = [(j, (metas[j] or {}).get("media")) for j in range(len(scenes)) if j < len(metas) and isinstance(metas[j], dict)]
    seen, dups = {}, []
    for j, md in medias:
        if md:
            reason = (scenes[j].meta or {}).get("repeat") or (scenes[j].meta or {}).get("ซ้ำ")  # build_subs แปลง ซ้ำ: → repeat
            if md in seen and not reason:
                dups.append(f"ฉาก {seen[md] + 1} และ {j + 1}")
            seen.setdefault(md, j)
    qc.add("repeat", not dups, "visual", "ไม่มีภาพซ้ำ" if not dups else "ใช้ภาพเดิมซ้ำโดยไม่มีเหตุผล: " + ", ".join(dups) +
           " (ถ้าตั้งใจ ใส่ | ซ้ำ: เหตุผล ในบรรทัดฉาก)")
    missing = [j + 1 for j in range(len(scenes)) if not (j < len(metas) and isinstance(metas[j], dict) and metas[j].get("media"))]
    qc.add("media", not missing, "visual", "ทุกฉากมีภาพ" if not missing else f"ฉาก {missing} ยังใช้ภาพแทนที่", "warn")
    credits_path = os.path.join(pdir, "credits.json")
    credits = json.load(open(credits_path, encoding="utf-8")) if os.path.exists(credits_path) else []
    by_file = {os.path.normcase(os.path.abspath(c.get("file", ""))): c for c in credits}
    bad, nocredit, unlabeled = [], [], []
    for j, md in medias:
        if not md:
            continue
        full = os.path.normcase(os.path.abspath(md if os.path.isabs(md) else os.path.join(pdir, md)))
        cr = by_file.get(full)
        meta = scenes[j].meta or {}
        gen = str((metas[j] or {}).get("generator", ""))
        if cr and monetized and license_bad(cr.get("license")):
            bad.append(f"ฉาก {j + 1} ({cr.get('license')})")
        if cr and not meta.get("credit"):
            nocredit.append(j + 1)
        if gen and not cr and "AI" not in meta.get("credit", "").upper():
            unlabeled.append(j + 1)
    qc.add("license", not bad, "visual", "สิทธิ์ใช้สื่อถูกต้อง" if not bad else "สื่อห้ามใช้เชิงพาณิชย์/ดัดแปลงในช่องหารายได้: " + ", ".join(bad))
    qc.add("credit", not nocredit, "visual", "เครดิตภาพครบ" if not nocredit else f"ฉาก {nocredit} ใช้ภาพจากเว็บแต่ไม่มีเครดิตบนการ์ด")
    qc.add("ailabel", not unlabeled, "visual", "ภาพ AI ติดป้ายครบ" if not unlabeled else
           f"ฉาก {unlabeled} เป็นภาพ AI แต่ไม่มี 'เครดิต: ภาพสร้างด้วย AI'", "warn")
    al = p.get("audioLicense", "")
    qc.add("audiolicense", not (monetized and license_bad(al)), "voice",
           "เพลง/เสียงใช้เชิงพาณิชย์ได้" if not (monetized and license_bad(al)) else f"เพลง/เสียงเป็น {al} ห้ามใช้ในช่องหารายได้")


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--project")
    ap.add_argument("--clip", type=int, default=1)
    ap.add_argument("--format", choices=list(SIZES))
    ap.add_argument("--config")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.video):
        print(f"✖ ไม่พบไฟล์ {a.video}", file=sys.stderr)
        return 2
    import doc_control as dc
    cfg = dc.load_config(a.config)
    try:
        qc, metrics = check(a.video, a, cfg)
    except FileNotFoundError:
        print("✖ ไม่พบ ffmpeg/ffprobe", file=sys.stderr)
        return 2
    fails = [c for c in qc.checks if not c["ok"] and c["severity"] == "fail"]
    warns = [c for c in qc.checks if not c["ok"] and c["severity"] == "warn"]
    res = {"file": os.path.abspath(a.video), "at": dc.now(), "pass": not fails,
           "returnTo": sorted({c["dept"] for c in fails}), "fails": len(fails), "warnings": len(warns),
           "metrics": metrics, "checks": qc.checks}
    with open(os.path.splitext(a.video)[0] + ".qc.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print(f"{'✔ ผ่าน QC' if res['pass'] else '✖ ไม่ผ่าน QC'} · {os.path.basename(a.video)} · {metrics.get('duration', '?')} วิ")
        for c in qc.checks:
            mark = "✔" if c["ok"] else ("✖" if c["severity"] == "fail" else "⚠")
            print(f"  {mark} [{DEPT_TH.get(c['dept'], c['dept'])}] {c['message']}")
        if fails:
            print("  ส่งกลับแผนก: " + ", ".join(DEPT_TH.get(d, d) for d in res["returnTo"]))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
