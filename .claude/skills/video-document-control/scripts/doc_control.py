#!/usr/bin/env python3
"""Document Control & Video Approval: ทะเบียน การอนุมัติ และการจัดเก็บไฟล์วิดีโอ (D:\\VIDEO_WORKFLOW)

โฟลเดอร์: 01_INCOMING · 02_REVIEW_QUEUE · 03_REVISION · 04_APPROVED · 05_FINAL_ARCHIVE · 06_DOCUMENTATION
ชื่อไฟล์:  [PROJECT]_[VIDEO-ID]_[CONTENT-NAME]_V[VERSION]_[STATUS].mp4   เช่น HISTORY_V001_SAMURAI_V01_PENDING.mp4
ทะเบียน:   06_DOCUMENTATION/register.json (+ register.csv สำหรับ Excel) · ประวัติทุกการกระทำ: history.jsonl (เขียนต่อท้ายอย่างเดียว)

  init              สร้างโครงสร้างโฟลเดอร์ + ทะเบียน
  receive FILE      รับคลิปใหม่: ตั้ง VIDEO ID, ตรวจว่าเปิดได้, คัดลอกเข้า INCOMING, ตรวจความครบ แล้วส่งเข้า REVIEW QUEUE
  resubmit ID FILE  รับไฟล์แก้ไข (เวอร์ชันใหม่) ของคลิปที่ไม่ผ่าน แล้วส่งกลับเข้าคิว
  update ID         แก้ข้อมูลทะเบียนที่ขาด (ผู้ผลิต ผู้รวบรวม ชื่อคลิป) แล้วตรวจความครบใหม่ด้วย organize
  organize ID       ตรวจความครบของเวอร์ชันล่าสุดอีกครั้ง และส่งเข้าคิวถ้าครบ
  queue             รายการรออนุมัติ (สำหรับ FINAL APPROVER)
  decide ID         บันทึกผลจากมนุษย์: --approve/--reject + --approver + --evidence (หรือ --from-decision ไฟล์จากหน้าเว็บ)
  process-decisions อ่านไฟล์ผลการตัดสินใจจากหน้าเว็บใน 06_DOCUMENTATION/decisions ที่ยังไม่ได้ดำเนินการ
  archive ID        คัดลอกฉบับที่อนุมัติเข้า 05_FINAL_ARCHIVE แล้วตรวจปลายทาง (ปกติทำให้เองหลังอนุมัติ)
  status [ID] · search · history ID · report [--date] · export · verify

กฎที่สคริปต์บังคับเอง: AI อนุมัติแทนมนุษย์ไม่ได้ · ไม่มีหลักฐานการอนุมัติ = ไม่จัดเก็บ · ไม่เขียนทับไฟล์ใด ๆ
· ไฟล์ซ้ำ/ชื่อไม่ตรง = หยุด (exit 3) · เข้าโฟลเดอร์ระบบไม่ได้ = ล้มเหลว (ไม่มีการรายงานว่าสำเร็จ)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

FOLDERS = ["01_INCOMING", "02_REVIEW_QUEUE", "03_REVISION", "04_APPROVED", "05_FINAL_ARCHIVE", "06_DOCUMENTATION"]
INC, QUEUE, REV, APP, FINAL, DOC = FOLDERS
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
TOKEN = {"RECEIVED": "PENDING", "INCOMPLETE": "PENDING", "PENDING_REVIEW": "PENDING",
         "REVISION_REQUIRED": "REVISION", "APPROVED": "APPROVED", "ARCHIVED": "APPROVED"}
STATUS_TH = {"RECEIVED": "รับเข้าแล้ว", "INCOMPLETE": "ข้อมูล/ไฟล์ไม่ครบ", "PENDING_REVIEW": "รออนุมัติ",
             "REVISION_REQUIRED": "ไม่ผ่าน · รอแก้ไข", "APPROVED": "อนุมัติแล้ว", "ARCHIVED": "จัดเก็บแล้ว"}
TOKEN_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,39}$")
NAME_RE = re.compile(r"^(?P<project>[A-Z0-9-]+)_(?P<vid>V\d{3,})_(?P<content>[A-Z0-9-]+)_V(?P<ver>\d{2,})_"
                     r"(?P<status>PENDING|REVISION|APPROVED)(?P<ext>\.[A-Za-z0-9]+)$")
AI_NAMES = re.compile(r"\b(claude|chatgpt|gpt|gemini|assistant|chatbot|bot|agent|controller)\b|เอไอ|ปัญญาประดิษฐ์", re.I)
AI_WORD = re.compile(r"\bAI\b")  # ตัวพิมพ์ใหญ่เท่านั้น (ไม่บล็อกชื่อคนอย่าง "Ai")
ACTOR = "AI Document Controller"
REQ_DEFAULT = {"minDuration": 3, "maxDuration": 900, "minShortSide": 720, "requireAudio": True,
               "requireCoordinator": False, "requireSubtitle": False, "requireQcPass": False, "deepCheck": True}


class DCError(Exception):
    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def today():
    return dt.date.today().isoformat()


# ---------------- config / root ----------------
def load_config(path=None):
    for p in ([path] if path else []) + [os.path.join(os.getcwd(), "production.config.json")]:
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
    return {}


def resolve_root(arg=None, cfg=None):
    root = arg or os.environ.get("VIDEO_WORKFLOW_ROOT") or (cfg or {}).get("workflowRoot")
    if not root and os.name == "nt":
        root = r"D:\VIDEO_WORKFLOW"
    if not root:
        raise DCError("ยังไม่ได้กำหนดโฟลเดอร์ระบบ ใส่ --root หรือ VIDEO_WORKFLOW_ROOT (บน Windows ค่าเริ่มต้นคือ D:\\VIDEO_WORKFLOW)")
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", root):
        raise DCError(f"โฟลเดอร์ระบบ {root} อยู่บนไดรฟ์ Windows แต่เครื่องที่รันอยู่ไม่ใช่ Windows จึงเข้าถึงไม่ได้ "
                      "ยังไม่ได้รับ/จัดเก็บไฟล์ใด ๆ (รันบนเครื่อง Windows หรือใส่ --root ที่เข้าถึงได้)")
    return os.path.abspath(root)


def require_root(root, create=False):
    drive = os.path.splitdrive(root)[0]
    if drive and not os.path.exists(drive + os.sep):
        raise DCError(f"เข้าถึงไดรฟ์ {drive} ไม่ได้ ยังไม่ได้รับ/จัดเก็บไฟล์ใด ๆ ตรวจว่าไดรฟ์เสียบอยู่และมีสิทธิ์เขียน")
    if create:
        for f in FOLDERS:
            os.makedirs(os.path.join(root, f), exist_ok=True)
        for sub in ("reports", "decisions", "notices", "orders"):
            os.makedirs(os.path.join(root, DOC, sub), exist_ok=True)
    if not os.path.isdir(root):
        raise DCError(f"ไม่พบโฟลเดอร์ระบบ {root} ให้รัน init ก่อน")
    missing = [f for f in FOLDERS if not os.path.isdir(os.path.join(root, f))]
    if missing:
        raise DCError(f"โครงสร้างโฟลเดอร์ไม่ครบ ขาด {', '.join(missing)} ให้รัน init")
    probe_file = os.path.join(root, DOC, f".write-test-{os.getpid()}")
    try:
        with open(probe_file, "w") as fh:
            fh.write("ok")
        os.remove(probe_file)
    except OSError as e:
        raise DCError(f"เขียนลงโฟลเดอร์ระบบไม่ได้ ({e}) ยังไม่ได้จัดเก็บอะไร")
    return root


def ab(root, rel):
    return os.path.join(root, *rel.split("/")) if rel else ""


def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


class Lock:
    """ล็อกทะเบียน ป้องกันสองงานเขียนพร้อมกัน (หลายทีมส่งงานพร้อมกันได้)"""

    def __init__(self, root):
        self.path = os.path.join(root, DOC, ".lock")

    def __enter__(self):
        t0 = time.time()
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {now()}".encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > 600:  # ล็อกค้างจากงานที่ตายไปแล้ว
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                if time.time() - t0 > 30:
                    raise DCError("ทะเบียนถูกล็อกโดยงานอื่นนานเกิน 30 วินาที ลองใหม่อีกครั้ง")
                time.sleep(0.3)

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass


# ---------------- register / history ----------------
def reg_path(root):
    return os.path.join(root, DOC, "register.json")


def load_reg(root):
    p = reg_path(root)
    if not os.path.exists(p):
        return {"schema": 1, "nextId": 1, "videos": {}, "processedDecisions": []}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_reg(root, reg):
    p = reg_path(root)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    export_csv(root, reg)


def log(root, action, vid=None, ver=None, actor=ACTOR, **detail):
    rec = {"at": now(), "actor": actor, "action": action, "videoId": vid, "version": ver}
    rec.update({k: v for k, v in detail.items() if v not in (None, "", [], {})})
    with open(os.path.join(root, DOC, "history.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_history(root):
    p = os.path.join(root, DOC, "history.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


CSV_COLS = ["VIDEO ID", "Project Name", "Video Name", "Producer", "Coordinator", "Submission Date", "Version",
            "Approval Status", "Approver", "Approval Date", "Revision Notes", "Final File Location"]


def export_csv(root, reg):
    path = os.path.join(root, DOC, "register.csv")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLS)
        for vid in sorted(reg["videos"]):
            r = reg["videos"][vid]
            v = cur_ver(r)
            ap = r.get("approval") or {}
            notes = " | ".join(f"V{n['version']:02d}: {n['notes']}" for n in r.get("revisionNotes", []))
            w.writerow([vid, r["project"], r.get("videoName", ""), r.get("producer", ""), r.get("coordinator", ""),
                        v.get("submittedAt", ""), f"V{r['currentVersion']:02d}", r["status"], ap.get("approver", ""),
                        ap.get("approvedAt", ""), notes, r.get("finalLocation", "")])
    try:
        os.replace(tmp, path)
    except PermissionError:  # ไฟล์ csv เปิดค้างใน Excel: ทะเบียนหลัก (json) บันทึกแล้ว แจ้งเตือนเฉย ๆ
        print("⚠ register.csv เปิดอยู่ในโปรแกรมอื่น ยังไม่ได้อัปเดต (register.json บันทึกครบแล้ว)", file=sys.stderr)
        os.remove(tmp)


def get_video(reg, vid):
    vid = (vid or "").upper()
    if vid not in reg["videos"]:
        raise DCError(f"ไม่พบ {vid} ในทะเบียน")
    return reg["videos"][vid]


def cur_ver(rec):
    return next(v for v in rec["versions"] if v["version"] == rec["currentVersion"])


def set_status(rec, verrec, status):
    rec["status"] = status
    verrec["status"] = status
    rec["updatedAt"] = now()


def find_sha(reg, digest):
    for vid, r in reg["videos"].items():
        for v in r["versions"]:
            if v.get("sha256") == digest:
                return f"{vid} V{v['version']:02d}"
    return None


# ---------------- files ----------------
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def copy_verified(src, dst, digest):
    if os.path.exists(dst):
        raise DCError(f"มีไฟล์ {dst} อยู่แล้ว ห้ามเขียนทับ หยุดและแจ้งผู้ดูแล", 3)
    shutil.copy2(src, dst)
    if sha256(dst) != digest:
        os.remove(dst)  # ลบเฉพาะสำเนาที่เราเพิ่งคัดลอกเสีย ไม่ใช่ต้นฉบับ
        raise DCError(f"คัดลอก {os.path.basename(src)} แล้วข้อมูลไม่ตรงต้นฉบับ (sha256) ยกเลิกขั้นนี้", 4)


def move_verified(src, dst, digest):
    """ย้ายสำเนาทำงาน (ไม่ใช่ต้นฉบับใน 01_INCOMING) ระหว่างโฟลเดอร์ในระบบ"""
    if os.path.exists(dst):
        raise DCError(f"มีไฟล์ {dst} อยู่แล้ว ห้ามเขียนทับ หยุดและแจ้งผู้ดูแล", 3)
    try:
        os.replace(src, dst)
    except OSError:
        copy_verified(src, dst, digest)
        os.remove(src)
    if sha256(dst) != digest:
        raise DCError(f"ไฟล์ {dst} ไม่ตรงกับที่ลงทะเบียน (sha256) หยุดและแจ้งผู้ดูแล", 4)


def sidecar(path):
    s = os.path.splitext(path)[0] + ".srt"
    return s if os.path.exists(s) else None


def file_name(project, vid, content, ver, token, ext):
    return f"{project}_{vid}_{content}_V{ver:02d}_{token}{ext.lower()}"


def norm_token(value, label):
    v = (value or "").strip().upper().replace(" ", "-").replace("_", "-")
    if not TOKEN_RE.match(v):
        raise DCError(f"{label} '{value}' ใช้ได้เฉพาะ A-Z 0-9 และ - (ไม่เกิน 40 ตัว) ใส่ชื่อภาษาไทยในช่องชื่อคลิป (--title) แทน")
    return v


def probe(path, deep=True):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                           capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise DCError("ไม่พบ ffprobe ติดตั้ง ffmpeg ก่อน (winget install Gyan.FFmpeg)")
    if r.returncode != 0:
        err = " ".join((r.stderr or "").replace(path, os.path.basename(path)).split())
        return {"ok": False, "error": err[:300] or "ffprobe เปิดไฟล์ไม่ได้"}
    d = json.loads(r.stdout or "{}")
    streams = d.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    dur = float((d.get("format") or {}).get("duration") or (v or {}).get("duration") or 0)
    fps = 0.0
    if v and v.get("r_frame_rate") and "/" in v["r_frame_rate"]:
        n, m = v["r_frame_rate"].split("/")
        fps = round(float(n) / float(m), 2) if float(m) else 0.0
    info = {"ok": bool(v) and dur > 0, "duration": round(dur, 2), "width": (v or {}).get("width"),
            "height": (v or {}).get("height"), "fps": fps, "vcodec": (v or {}).get("codec_name"),
            "audio": bool(a), "acodec": (a or {}).get("codec_name"), "size": os.path.getsize(path)}
    if not info["ok"]:
        info["error"] = "ไม่มีภาพวิดีโอ หรือความยาวเป็น 0"
    elif deep:  # ถอดรหัสทั้งไฟล์ จับไฟล์ที่เสียกลางทาง
        r2 = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", path, "-f", "null", "-"],
                            capture_output=True, text=True, timeout=900)
        if r2.returncode != 0:
            info["ok"], info["error"] = False, "ไฟล์เสียระหว่างเล่น: " + (r2.stderr or "").strip()[:200]
    return info


# ---------------- completeness ----------------
def check_complete(rec, verrec, req):
    problems, warnings = [], []
    for key, label in (("project", "Project Name"), ("contentName", "Content Name"), ("videoName", "Video Name"),
                       ("producer", "Producer")):
        if not str(rec.get(key) or "").strip():
            problems.append(f"ไม่มี {label}")
    if not str(rec.get("coordinator") or "").strip():
        (problems if req.get("requireCoordinator") else warnings).append("ไม่มี Coordinator")
    p = verrec.get("probe") or {}
    if not p.get("ok"):
        problems.append(f"เปิดไฟล์ไม่ได้: {p.get('error', 'ไม่ทราบสาเหตุ')}")
        return problems, warnings
    if p["duration"] < req["minDuration"]:
        problems.append(f"สั้นเกินไป ({p['duration']} วิ < {req['minDuration']} วิ)")
    if p["duration"] > req["maxDuration"]:
        problems.append(f"ยาวเกินไป ({p['duration']} วิ > {req['maxDuration']} วิ)")
    if min(p["width"] or 0, p["height"] or 0) < req["minShortSide"]:
        problems.append(f"ความละเอียดต่ำ ({p['width']}x{p['height']}, ด้านสั้นต้อง ≥ {req['minShortSide']})")
    if req.get("requireAudio", True) and not p.get("audio"):
        problems.append("ไม่มีเสียง")
    if p.get("fps") and not (23 <= p["fps"] <= 61):
        warnings.append(f"fps {p['fps']} อยู่นอกช่วงที่แพลตฟอร์มรับ (23–60)")
    if req.get("requireSubtitle") and not verrec.get("subtitleFile"):
        problems.append("ไม่มีไฟล์ซับ .srt")
    qc = verrec.get("qc")
    if req.get("requireQcPass"):
        if not qc:
            problems.append("ยังไม่มีผลตรวจคุณภาพ (.qc.json จาก qc_check.py) หรือผลเก่ากว่าไฟล์")
        elif not qc.get("pass"):
            problems.append(f"ไม่ผ่าน QC ({qc.get('fails')} ข้อ) ส่งกลับ: {', '.join(qc.get('returnTo') or [])}")
    elif qc and not qc.get("pass"):
        warnings.append(f"ผล QC ไม่ผ่าน {qc.get('fails')} ข้อ")
    return problems, warnings


def notify(root, rec, verrec, problems, who="ผู้รวบรวม (Video Coordinator)"):
    path = os.path.join(root, DOC, "notices", f"{today()}.md")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new:
            fh.write(f"# แจ้งเตือนวันที่ {today()}\n\n")
        fh.write(f"- {now()} · ถึง {who} · {rec['videoId']} V{verrec['version']:02d} ({rec.get('videoName', '')}): "
                 + "; ".join(problems) + "\n")


def organize_version(root, rec, verrec, req):
    problems, warnings = check_complete(rec, verrec, req)
    verrec["checks"] = {"at": now(), "problems": problems, "warnings": warnings}
    if problems:
        set_status(rec, verrec, "INCOMPLETE")
        notify(root, rec, verrec, problems)
        log(root, "INCOMPLETE", rec["videoId"], verrec["version"], problems=problems)
        return False
    inc = ab(root, verrec["incomingFile"])
    q = os.path.join(root, QUEUE, os.path.basename(inc))
    copy_verified(inc, q, verrec["sha256"])
    if verrec.get("subtitleFile"):
        s = ab(root, verrec["subtitleFile"])
        if os.path.exists(s) and not os.path.exists(os.path.splitext(q)[0] + ".srt"):
            shutil.copy2(s, os.path.splitext(q)[0] + ".srt")
    verrec["queueFile"] = rel(root, q)
    set_status(rec, verrec, "PENDING_REVIEW")
    log(root, "QUEUED", rec["videoId"], verrec["version"], file=verrec["queueFile"], warnings=warnings)
    return True


def add_version(root, reg, rec, src, submitted_by, changes=""):
    ext = os.path.splitext(src)[1].lower()
    if ext not in VIDEO_EXT:
        raise DCError(f"นามสกุล {ext or '(ไม่มี)'} ไม่ใช่วิดีโอที่รับ ({', '.join(VIDEO_EXT)})")
    m = NAME_RE.match(os.path.basename(src))
    if m and (m["project"] != rec["project"] or m["content"] != rec["contentName"] or m["vid"] != rec["videoId"]):
        raise DCError(f"ชื่อไฟล์ {os.path.basename(src)} ไม่ตรงกับทะเบียน ({rec['project']}_{rec['videoId']}_"
                      f"{rec['contentName']}) หยุดและแจ้งผู้ดูแล", 3)
    digest = sha256(src)
    dup = find_sha(reg, digest)
    if dup:
        raise DCError(f"ไฟล์นี้ซ้ำกับ {dup} ที่ลงทะเบียนแล้ว (เนื้อไฟล์เหมือนกันทุกไบต์) หยุดและแจ้งผู้ดูแล", 3)
    ver = rec["currentVersion"] + 1 if rec["versions"] else 1
    name = file_name(rec["project"], rec["videoId"], rec["contentName"], ver, "PENDING", ext)
    inc = os.path.join(root, INC, name)
    copy_verified(src, inc, digest)
    verrec = {"version": ver, "submittedAt": now(), "submittedBy": submitted_by, "source": os.path.abspath(src),
              "fileName": name, "incomingFile": rel(root, inc), "sha256": digest, "status": "RECEIVED"}
    if changes:
        verrec["changes"] = changes
    s = sidecar(src)
    if s:
        dst = os.path.splitext(inc)[0] + ".srt"
        if not os.path.exists(dst):
            shutil.copy2(s, dst)
        verrec["subtitleFile"] = rel(root, dst)
    qcf = os.path.splitext(src)[0] + ".qc.json"
    if os.path.exists(qcf) and os.path.getmtime(qcf) >= os.path.getmtime(src):  # ผล QC ต้องใหม่กว่าไฟล์ที่ตรวจ
        try:
            with open(qcf, encoding="utf-8") as fh:
                q = json.load(fh)
            verrec["qc"] = {"pass": bool(q.get("pass")), "fails": q.get("fails", 0), "warnings": q.get("warnings", 0),
                            "returnTo": q.get("returnTo", []), "at": q.get("at", ""),
                            "issues": [c["message"] for c in q.get("checks", []) if not c.get("ok")][:12]}
        except (OSError, ValueError, KeyError):
            pass
    rec["versions"].append(verrec)
    rec["currentVersion"] = ver
    set_status(rec, verrec, "RECEIVED")
    return verrec


# ---------------- commands ----------------
def cmd_init(a, cfg):
    root = resolve_root(a.root, cfg)
    require_root(root, create=True)
    if not os.path.exists(reg_path(root)):
        save_reg(root, load_reg(root))
        log(root, "INIT", path=root)
    readme = os.path.join(root, DOC, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as fh:
            fh.write(README_DOC)
    print(f"✔ ระบบพร้อมที่ {root}")
    for f in FOLDERS:
        print("  ", os.path.join(root, f))
    return 0


def cmd_receive(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    src = os.path.abspath(a.file)
    if not os.path.isfile(src):
        raise DCError(f"ไม่พบไฟล์ {src}")
    project, content = norm_token(a.project, "PROJECT"), norm_token(a.name, "CONTENT-NAME")
    req = {**REQ_DEFAULT, **(cfg.get("requirements") or {})}
    with Lock(root):
        reg = load_reg(root)
        same = [v for v, r in reg["videos"].items() if r["project"] == project and r["contentName"] == content]
        if same and not a.allow_same_name:
            raise DCError(f"มี {project}_{same[0]}_{content} ในทะเบียนแล้ว ถ้าเป็นฉบับแก้ไขให้ใช้ resubmit {same[0]} "
                          f"ถ้าเป็นคลิปใหม่จริงให้ตั้ง CONTENT-NAME ใหม่ (หรือ --allow-same-name)", 3)
        vid = f"V{reg['nextId']:03d}"
        rec = {"videoId": vid, "project": project, "contentName": content, "videoName": a.title or content,
               "producer": a.producer or "", "coordinator": a.coordinator or "", "orderId": a.order or "",
               "createdAt": now(), "updatedAt": now(), "status": "RECEIVED", "currentVersion": 0, "versions": [],
               "revisionNotes": [], "revisionRound": 0}
        verrec = add_version(root, reg, rec, src, a.producer or a.actor)
        verrec["probe"] = probe(ab(root, verrec["incomingFile"]), req.get("deepCheck", True))
        reg["nextId"] += 1
        reg["videos"][vid] = rec
        log(root, "RECEIVED", vid, 1, a.actor, file=verrec["incomingFile"], source=src, producer=rec["producer"],
            order=rec["orderId"])
        save_reg(root, reg)  # ลงทะเบียนทันทีที่ไฟล์เข้า INCOMING (ไม่มีไฟล์ไร้ทะเบียน แม้ขั้นถัดไปล้ม)
        try:
            queued = organize_version(root, rec, verrec, req)
        finally:
            save_reg(root, reg)
    report_line(rec, verrec, queued)
    return 0 if queued else 2


def cmd_resubmit(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    src = os.path.abspath(a.file)
    if not os.path.isfile(src):
        raise DCError(f"ไม่พบไฟล์ {src}")
    req = {**REQ_DEFAULT, **(cfg.get("requirements") or {})}
    with Lock(root):
        reg = load_reg(root)
        rec = get_video(reg, a.video_id)
        if rec["status"] not in ("REVISION_REQUIRED", "INCOMPLETE"):
            raise DCError(f"{rec['videoId']} สถานะ {rec['status']} ส่งฉบับแก้ได้เฉพาะ REVISION_REQUIRED หรือ INCOMPLETE", 3)
        if a.producer:
            rec["producer"] = a.producer
        verrec = add_version(root, reg, rec, src, a.producer or rec.get("producer") or a.actor, a.changes or "")
        verrec["probe"] = probe(ab(root, verrec["incomingFile"]), req.get("deepCheck", True))
        log(root, "RESUBMITTED", rec["videoId"], verrec["version"], a.actor, file=verrec["incomingFile"],
            changes=a.changes)
        save_reg(root, reg)
        try:
            queued = organize_version(root, rec, verrec, req)
        finally:
            save_reg(root, reg)
    report_line(rec, verrec, queued)
    return 0 if queued else 2


def cmd_update(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    with Lock(root):
        reg = load_reg(root)
        rec = get_video(reg, a.video_id)
        changed = {}
        for key, val in (("producer", a.producer), ("coordinator", a.coordinator), ("videoName", a.title),
                         ("orderId", a.order)):
            if val is not None and val != rec.get(key):
                changed[key] = {"from": rec.get(key, ""), "to": val}
                rec[key] = val
        if not changed:
            print("ไม่มีอะไรเปลี่ยน")
            return 0
        rec["updatedAt"] = now()
        log(root, "UPDATED", rec["videoId"], rec["currentVersion"], a.actor, changes=changed)
        save_reg(root, reg)
    print(f"✔ แก้ข้อมูล {rec['videoId']}: {', '.join(changed)}" +
          (" · รัน organize เพื่อตรวจความครบและส่งเข้าคิว" if rec["status"] == "INCOMPLETE" else ""))
    return 0


def cmd_organize(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    req = {**REQ_DEFAULT, **(cfg.get("requirements") or {})}
    with Lock(root):
        reg = load_reg(root)
        rec = get_video(reg, a.video_id)
        verrec = cur_ver(rec)
        if rec["status"] not in ("RECEIVED", "INCOMPLETE"):
            raise DCError(f"{rec['videoId']} สถานะ {rec['status']} ไม่ต้องจัดเข้าคิวใหม่")
        queued = organize_version(root, rec, verrec, req)
        save_reg(root, reg)
    report_line(rec, verrec, queued)
    return 0 if queued else 2


def report_line(rec, verrec, queued):
    p = verrec.get("probe") or {}
    print(f"{'✔' if queued else '✖'} {rec['videoId']} V{verrec['version']:02d} {rec['project']} · {rec.get('videoName')} → "
          f"{STATUS_TH[rec['status']]} ({rec['status']})")
    if p.get("ok"):
        print(f"   ไฟล์: {verrec['fileName']} · {p['width']}x{p['height']} · {p['duration']} วิ · "
              f"{'มีเสียง' if p.get('audio') else 'ไม่มีเสียง'} · sha256 {verrec['sha256'][:12]}…")
    for x in (verrec.get("checks") or {}).get("problems", []):
        print("   ✖", x)
    for x in (verrec.get("checks") or {}).get("warnings", []):
        print("   ⚠", x)
    if not queued:
        print("   แจ้งผู้รวบรวมแล้ว (06_DOCUMENTATION/notices) แก้ข้อมูลด้วย update หรือส่งไฟล์ใหม่ด้วย resubmit")


def cmd_queue(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    reg = load_reg(root)
    items = [r for r in reg["videos"].values() if r["status"] == "PENDING_REVIEW"]
    if a.json:
        print(json.dumps([{"videoId": r["videoId"], "version": r["currentVersion"], "videoName": r.get("videoName"),
                           "file": cur_ver(r).get("queueFile"), "sha256": cur_ver(r)["sha256"]} for r in items],
                         ensure_ascii=False, indent=1))
        return 0
    if not items:
        print("ไม่มีคลิปรออนุมัติ")
        return 0
    print(f"รออนุมัติ {len(items)} คลิป (ผู้อนุมัติขั้นสุดท้ายเท่านั้นที่ตัดสินได้):")
    for r in sorted(items, key=lambda r: r["videoId"]):
        v = cur_ver(r)
        print(f"  {r['videoId']} V{v['version']:02d} · {r.get('videoName')} · ผู้ผลิต {r.get('producer') or '-'}\n"
              f"     {ab(root, v['queueFile'])}")
    return 0


def load_decision(path):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("type") != "video-decision":
        raise DCError(f"{path} ไม่ใช่ไฟล์ผลการตัดสินใจ (type ต้องเป็น video-decision)")
    for k in ("videoId", "version", "decision", "approver", "decidedAt"):
        if not d.get(k):
            raise DCError(f"ไฟล์ {os.path.basename(path)} ขาดช่อง {k}")
    if d["decision"] not in ("APPROVE", "REJECT"):
        raise DCError(f"decision ต้องเป็น APPROVE หรือ REJECT (ได้ {d['decision']})")
    return d


def decide(root, reg, rec, decision, version, approver, evidence, notes, actor, cfg, dfile_sha=None,
           archive_after=True):
    """ตรวจทุกอย่างก่อน แล้วค่อยย้ายไฟล์ แล้วค่อยแก้ทะเบียน (ถ้าล้มกลางทาง ทะเบียนไม่เพี้ยน) คืนค่า exit code"""
    approver = (approver or "").strip()
    if not approver:
        raise DCError("ต้องมีชื่อผู้อนุมัติ (FINAL APPROVER ที่เป็นมนุษย์) AI อนุมัติแทนไม่ได้")
    if AI_NAMES.search(approver) or AI_WORD.search(approver):
        raise DCError(f"ผู้อนุมัติ '{approver}' ดูเหมือน AI/บอท ผู้อนุมัติขั้นสุดท้ายต้องเป็นมนุษย์เท่านั้น")
    if not (evidence or "").strip():
        raise DCError("ต้องมีหลักฐานการตัดสินใจ (--evidence หรือไฟล์ decision จากหน้าเว็บ) ห้ามคาดเดาผลการอนุมัติ")
    if decision == "REJECT" and not (notes or "").strip():
        raise DCError("ไม่อนุมัติต้องมีเหตุผลและข้อเสนอแนะ (--notes) เพื่อส่งกลับทีมผู้ผลิต")
    if rec["status"] != "PENDING_REVIEW":
        raise DCError(f"{rec['videoId']} สถานะ {rec['status']} ตัดสินได้เฉพาะคลิปที่ PENDING_REVIEW", 3)
    if int(version) != rec["currentVersion"]:
        raise DCError(f"ผลนี้เป็นของ V{int(version):02d} แต่ฉบับที่รอพิจารณาคือ V{rec['currentVersion']:02d} หยุดและแจ้งผู้ดูแล", 3)
    verrec = cur_ver(rec)
    q = ab(root, verrec.get("queueFile", ""))
    if not q or not os.path.exists(q):
        raise DCError(f"ไม่พบไฟล์ในคิว {verrec.get('queueFile')} หยุดและแจ้งผู้ดูแล", 3)
    digest = sha256(q)
    if digest != verrec["sha256"]:
        raise DCError("ไฟล์ในคิวถูกเปลี่ยนหลังลงทะเบียน (sha256 ไม่ตรง) ห้ามตัดสินบนไฟล์นี้ หยุดและแจ้งผู้ดูแล", 3)
    if dfile_sha and dfile_sha != digest:
        raise DCError("ไฟล์ที่ผู้อนุมัติเปิดดูไม่ตรงกับไฟล์ในคิว (sha256) หยุดและแจ้งผู้ดูแล", 3)
    stamp = now()
    record = {"result": decision, "approver": approver, "at": stamp, "evidence": evidence,
              "notes": notes or "", "recordedBy": actor}
    if decision == "REJECT":
        dst = os.path.join(root, REV, file_name(rec["project"], rec["videoId"], rec["contentName"], verrec["version"],
                                                "REVISION", os.path.splitext(q)[1]))
        fb = os.path.join(root, REV, file_name(rec["project"], rec["videoId"], rec["contentName"], verrec["version"],
                                               "FEEDBACK", ".md"))
        if os.path.exists(fb):
            raise DCError(f"มี {rel(root, fb)} อยู่แล้ว ห้ามเขียนทับ หยุดและแจ้งผู้ดูแล", 3)
        with open(fb, "w", encoding="utf-8") as fh:  # เขียนก่อนย้ายไฟล์: ถ้าเขียนไม่ได้ ไม่มีอะไรถูกย้าย
            fh.write(f"# Feedback {rec['videoId']} V{verrec['version']:02d} · {rec.get('videoName')}\n\n"
                     f"- ผลการพิจารณา: ไม่อนุมัติ / ต้องแก้ไข\n- ผู้อนุมัติ: {approver}\n- วันเวลา: {stamp}\n"
                     f"- หลักฐาน: {evidence}\n\n## สิ่งที่ต้องแก้\n\n{notes}\n\n"
                     f"ส่งไฟล์แก้ไขด้วย: `doc_control.py resubmit {rec['videoId']} <ไฟล์ใหม่> --changes \"แก้อะไรไป\"`\n")
        try:
            move_verified(q, dst, digest)
        except DCError:
            os.remove(fb)  # ลบไฟล์ feedback ที่เพิ่งเขียนเอง เพราะการย้ายไม่สำเร็จ
            raise
        verrec["decision"] = record
        qs = os.path.splitext(q)[0] + ".srt"
        if os.path.exists(qs):
            os.replace(qs, os.path.splitext(dst)[0] + ".srt")
        verrec["revisionFile"], verrec["feedbackFile"] = rel(root, dst), rel(root, fb)
        rec["revisionNotes"].append({"version": verrec["version"], "at": stamp, "approver": approver, "notes": notes})
        rec["revisionRound"] = rec.get("revisionRound", 0) + 1
        set_status(rec, verrec, "REVISION_REQUIRED")
        log(root, "REJECTED", rec["videoId"], verrec["version"], actor, approver=approver, notes=notes,
            evidence=evidence, file=verrec["revisionFile"])
        notify(root, rec, verrec, [f"ไม่อนุมัติ: {notes}"], who="ทีมผู้ผลิต (Video Producer)")
        print(f"✔ บันทึก: {rec['videoId']} V{verrec['version']:02d} ไม่อนุมัติ → 03_REVISION + feedback ส่งกลับทีมผู้ผลิต")
        return 0
    dst = os.path.join(root, APP, file_name(rec["project"], rec["videoId"], rec["contentName"], verrec["version"],
                                            "APPROVED", os.path.splitext(q)[1]))
    move_verified(q, dst, digest)
    verrec["decision"] = record
    qs = os.path.splitext(q)[0] + ".srt"
    if os.path.exists(qs):
        os.replace(qs, os.path.splitext(dst)[0] + ".srt")
    verrec["approvedFile"] = rel(root, dst)
    rec["approval"] = {"approver": approver, "approvedAt": stamp, "version": verrec["version"], "evidence": evidence,
                       "notes": notes or ""}
    set_status(rec, verrec, "APPROVED")
    log(root, "APPROVED", rec["videoId"], verrec["version"], actor, approver=approver, evidence=evidence,
        file=verrec["approvedFile"])
    print(f"✔ บันทึก: {rec['videoId']} V{verrec['version']:02d} อนุมัติโดย {approver} → 04_APPROVED")
    if archive_after:
        try:
            archive(root, rec, actor, cfg)
        except DCError as e:  # อนุมัติบันทึกแล้ว แต่ยังไม่ได้จัดเก็บ: ห้ามรายงานว่าสำเร็จ
            print(f"✖ อนุมัติแล้วแต่จัดเก็บเข้า FINAL ARCHIVE ไม่สำเร็จ: {e}", file=sys.stderr)
            return 4
    return 0


def archive(root, rec, actor, cfg):
    if rec["status"] != "APPROVED":
        raise DCError(f"{rec['videoId']} สถานะ {rec['status']} จัดเก็บเข้า FINAL ARCHIVE ได้เฉพาะ APPROVED", 3)
    ap = rec.get("approval") or {}
    if not ap.get("approver") or not ap.get("evidence"):
        raise DCError(f"{rec['videoId']} ไม่มีหลักฐานการอนุมัติ ห้ามจัดเก็บ", 3)
    if ap.get("version") != rec["currentVersion"]:
        raise DCError("เวอร์ชันที่อนุมัติไม่ใช่เวอร์ชันล่าสุด หยุดและแจ้งผู้ดูแล", 3)
    verrec = cur_ver(rec)
    src = ab(root, verrec.get("approvedFile", ""))
    if not os.path.exists(src):
        raise DCError(f"ไม่พบไฟล์ที่อนุมัติ {verrec.get('approvedFile')} ยังไม่ได้จัดเก็บ", 4)
    if sha256(src) != verrec["sha256"]:
        raise DCError("ไฟล์ใน 04_APPROVED ไม่ตรงกับฉบับที่อนุมัติ (sha256) ยังไม่ได้จัดเก็บ หยุดและแจ้งผู้ดูแล", 4)
    dst_dir = os.path.join(root, FINAL, rec["project"])
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    if os.path.exists(dst):
        raise DCError(f"มีไฟล์ Final {rel(root, dst)} อยู่แล้ว ห้ามเขียนทับ หยุดและแจ้งผู้ดูแล", 3)
    try:
        copy_verified(src, dst, verrec["sha256"])
    except DCError as e:
        rec["archiveError"] = str(e)
        log(root, "ARCHIVE_FAILED", rec["videoId"], verrec["version"], actor, error=str(e))
        raise
    p = probe(dst, deep=False)
    if not p.get("ok") or os.path.getsize(dst) != os.path.getsize(src):
        os.remove(dst)  # สำเนาที่เพิ่งสร้างและตรวจไม่ผ่าน (ไม่ใช่ต้นฉบับ)
        rec["archiveError"] = "ไฟล์ปลายทางเปิดไม่ได้หรือขนาดไม่ตรง"
        log(root, "ARCHIVE_FAILED", rec["videoId"], verrec["version"], actor, error=rec["archiveError"])
        raise DCError(f"จัดเก็บ {rec['videoId']} ไม่สำเร็จ: {rec['archiveError']}", 4)
    s = os.path.splitext(src)[0] + ".srt"
    if os.path.exists(s) and not os.path.exists(os.path.splitext(dst)[0] + ".srt"):
        shutil.copy2(s, os.path.splitext(dst)[0] + ".srt")
    rec.pop("archiveError", None)
    verrec["finalFile"] = rec["finalLocation"] = rel(root, dst)
    rec["archivedAt"] = now()
    set_status(rec, verrec, "ARCHIVED")
    log(root, "ARCHIVED", rec["videoId"], verrec["version"], actor, file=rec["finalLocation"], sha256=verrec["sha256"])
    path = os.path.join(root, DOC, "reports", f"archive_{today()}.md")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new:
            fh.write(f"# รายงานการจัดเก็บ {today()}\n\n| เวลา | VIDEO ID | ชื่อคลิป | เวอร์ชัน | ผู้อนุมัติ | ตำแหน่งจัดเก็บ | sha256 |\n|---|---|---|---|---|---|---|\n")
        fh.write(f"| {rec['archivedAt'][11:16]} | {rec['videoId']} | {rec.get('videoName')} | V{verrec['version']:02d} | "
                 f"{ap['approver']} | {rec['finalLocation']} | {verrec['sha256'][:16]}… |\n")
    print(f"✔ จัดเก็บ {rec['videoId']} → {dst} (ตรวจแล้ว: มีไฟล์จริง เปิดได้ sha256 ตรง)")


def cmd_decide(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    with Lock(root):
        reg = load_reg(root)
        if a.from_decision:
            d = load_decision(a.from_decision)
            name = os.path.basename(a.from_decision)
            if name in reg.get("processedDecisions", []):
                raise DCError(f"ไฟล์ผลการตัดสินใจ {name} ดำเนินการไปแล้ว", 3)
            rec = get_video(reg, d["videoId"])
            evidence = f"ไฟล์ผลการตัดสินใจ {name} ({d.get('via', 'office-web')}, {d['decidedAt']})"
            code = decide(root, reg, rec, d["decision"], d["version"], d["approver"], evidence, d.get("notes", ""),
                          a.actor, cfg, d.get("sha256"), not a.no_archive)
            reg.setdefault("processedDecisions", []).append(name)
        else:
            if a.approve == a.reject:
                raise DCError("เลือกอย่างใดอย่างหนึ่ง: --approve หรือ --reject")
            rec = get_video(reg, a.video_id)
            code = decide(root, reg, rec, "APPROVE" if a.approve else "REJECT", a.version or rec["currentVersion"],
                          a.approver, a.evidence, a.notes, a.actor, cfg, None, not a.no_archive)
        save_reg(root, reg)
    return code


def cmd_process_decisions(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    files = sorted(glob.glob(os.path.join(root, DOC, "decisions", "*.json")))
    done, failed = 0, 0
    with Lock(root):
        reg = load_reg(root)
        seen = set(reg.setdefault("processedDecisions", []))
        for f in files:
            name = os.path.basename(f)
            if name in seen:
                continue
            try:
                d = load_decision(f)
                rec = get_video(reg, d["videoId"])
                evidence = f"ไฟล์ผลการตัดสินใจ {name} ({d.get('via', 'office-web')}, {d['decidedAt']})"
                code = decide(root, reg, rec, d["decision"], d["version"], d["approver"], evidence,
                              d.get("notes", ""), a.actor, cfg, d.get("sha256"), True)
                reg["processedDecisions"].append(name)
                done += 1
                failed += 1 if code else 0
            except DCError as e:
                failed += 1
                print(f"✖ {name}: {e}")
                log(root, "DECISION_ERROR", None, None, a.actor, file=name, error=str(e))
                if e.code == 3:  # ไฟล์ไม่ตรง/สถานะไม่ตรง: เก็บไว้ไม่ทำซ้ำ ให้ผู้ดูแลตรวจ
                    reg["processedDecisions"].append(name)
            save_reg(root, reg)
    print(f"ดำเนินการผลการตัดสินใจ {done} รายการ" + (f" · ล้มเหลว {failed} (ดูข้อความด้านบน)" if failed else ""))
    return 1 if failed else 0


def cmd_archive(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    with Lock(root):
        reg = load_reg(root)
        rec = get_video(reg, a.video_id)
        try:
            archive(root, rec, a.actor, cfg)
        finally:
            save_reg(root, reg)
    return 0


def cmd_status(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    reg = load_reg(root)
    if a.video_id:
        rec = get_video(reg, a.video_id)
        if a.json:
            print(json.dumps(rec, ensure_ascii=False, indent=1))
            return 0
        print(f"{rec['videoId']} · {rec['project']} · {rec.get('videoName')} · {STATUS_TH[rec['status']]} ({rec['status']})")
        print(f"  ผู้ผลิต {rec.get('producer') or '-'} · ผู้รวบรวม {rec.get('coordinator') or '-'} · ใบสั่ง {rec.get('orderId') or '-'}")
        for v in rec["versions"]:
            d = v.get("decision") or {}
            print(f"  V{v['version']:02d} {v['status']:<18} ส่ง {v['submittedAt'][:16]} · {v['fileName']}"
                  + (f" · {d['result']} โดย {d['approver']} {d['at'][:16]}" if d else ""))
            if d.get("notes"):
                print(f"      feedback: {d['notes']}")
        if rec.get("finalLocation"):
            print(f"  จัดเก็บที่: {ab(root, rec['finalLocation'])}")
        return 0
    counts = {}
    for r in reg["videos"].values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"ทะเบียน {len(reg['videos'])} คลิป · " + " · ".join(f"{STATUS_TH[k]} {v}" for k, v in sorted(counts.items())))
    for r in sorted(reg["videos"].values(), key=lambda r: r["videoId"]):
        print(f"  {r['videoId']} V{r['currentVersion']:02d} {r['status']:<18} {r['project']} · {r.get('videoName')}")
    return 0


def cmd_search(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    reg = load_reg(root)
    q = (a.text or "").lower()
    hits = []
    for r in sorted(reg["videos"].values(), key=lambda r: r["videoId"]):
        if a.project and r["project"] != a.project.upper():
            continue
        if a.status and r["status"] != a.status.upper():
            continue
        blob = json.dumps(r, ensure_ascii=False).lower()
        if q and q not in blob:
            continue
        hits.append(r)
    for r in hits:
        print(f"{r['videoId']} V{r['currentVersion']:02d} {r['status']:<18} {r['project']} · {r.get('videoName')} · "
              f"{r.get('producer') or '-'} · {r.get('finalLocation') or ''}")
    print(f"พบ {len(hits)} รายการ")
    return 0


def cmd_history(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    vid = a.video_id.upper()
    for e in read_history(root):
        if e.get("videoId") == vid:
            extra = {k: v for k, v in e.items() if k not in ("at", "actor", "action", "videoId", "version")}
            print(f"{e['at'][:19]} · {e['action']:<14} V{(e.get('version') or 0):02d} · {e['actor']} · "
                  + json.dumps(extra, ensure_ascii=False)[:200])
    return 0


def daily_summary(reg, history, day):
    ev = [e for e in history if str(e.get("at", "")).startswith(day)]

    def count(*acts):
        return len([e for e in ev if e["action"] in acts])

    vids = list(reg["videos"].values())
    backlog = [r for r in vids if r["status"] != "ARCHIVED"]
    return {"date": day, "received": count("RECEIVED", "RESUBMITTED"),
            "pendingReview": len([r for r in vids if r["status"] == "PENDING_REVIEW"]),
            "rejected": count("REJECTED"),
            "inRevision": len([r for r in vids if r["status"] in ("REVISION_REQUIRED", "INCOMPLETE")]),
            "approved": count("APPROVED"), "archived": count("ARCHIVED"),
            "archiveFailed": count("ARCHIVE_FAILED"),
            "backlog": [{"videoId": r["videoId"], "version": r["currentVersion"], "status": r["status"],
                         "videoName": r.get("videoName"), "since": r.get("updatedAt", "")} for r in backlog]}


def cmd_report(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    reg = load_reg(root)
    day = a.date or today()
    s = daily_summary(reg, read_history(root), day)
    lines = [f"# รายงานสรุปประจำวัน {day}", "",
             "| รายการ | จำนวน |", "|---|---|",
             f"| คลิปที่รับเข้ามา (รวมฉบับแก้) | {s['received']} |",
             f"| รออนุมัติ (ตอนนี้) | {s['pendingReview']} |",
             f"| ไม่ผ่าน (วันนี้) | {s['rejected']} |",
             f"| กำลังแก้ไข / ข้อมูลไม่ครบ (ตอนนี้) | {s['inRevision']} |",
             f"| อนุมัติแล้ว (วันนี้) | {s['approved']} |",
             f"| จัดเก็บสำเร็จ (วันนี้) | {s['archived']} |"]
    if s["archiveFailed"]:
        lines.append(f"| ⚠ จัดเก็บล้มเหลว (วันนี้) | {s['archiveFailed']} |")
    lines += ["", "## งานค้างดำเนินการ", ""]
    lines += [f"- {b['videoId']} V{b['version']:02d} · {b['videoName']} · {STATUS_TH[b['status']]} (ตั้งแต่ {b['since'][:16]})"
              for b in s["backlog"]] or ["- ไม่มี"]
    text = "\n".join(lines) + "\n"
    path = os.path.join(root, DOC, "reports", f"daily_{day}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text + f"\n✔ บันทึกรายงานที่ {path}")
    return 0


def cmd_export(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    export_csv(root, load_reg(root))
    print(f"✔ {os.path.join(root, DOC, 'register.csv')}")
    return 0


def cmd_verify(a, cfg):
    root = require_root(resolve_root(a.root, cfg))
    reg = load_reg(root)
    issues = []
    for r in reg["videos"].values():
        for v in r["versions"]:
            for key in ("incomingFile", "queueFile", "revisionFile", "approvedFile", "finalFile"):
                if key == "queueFile" and v["status"] != "PENDING_REVIEW":
                    continue
                if v.get(key) and not os.path.exists(ab(root, v[key])):
                    issues.append(f"{r['videoId']} V{v['version']:02d}: ไม่พบ {key} {v[key]}")
        if r["status"] == "ARCHIVED":
            f = ab(root, r.get("finalLocation", ""))
            if not os.path.exists(f):
                issues.append(f"{r['videoId']}: ไฟล์ Final หาย {r.get('finalLocation')}")
            elif sha256(f) != cur_ver(r)["sha256"]:
                issues.append(f"{r['videoId']}: ไฟล์ Final ถูกเปลี่ยน (sha256 ไม่ตรง)")
        if r["status"] in ("APPROVED", "ARCHIVED") and not (r.get("approval") or {}).get("evidence"):
            issues.append(f"{r['videoId']}: สถานะ {r['status']} แต่ไม่มีหลักฐานการอนุมัติ")
    for name in os.listdir(os.path.join(root, FINAL)):
        sub = os.path.join(root, FINAL, name)
        for f in (os.listdir(sub) if os.path.isdir(sub) else [name]):
            m = NAME_RE.match(f)
            if f.endswith(".srt"):
                continue
            if not m or m["status"] != "APPROVED" or m["vid"] not in reg["videos"] or \
                    reg["videos"][m["vid"]]["status"] != "ARCHIVED":
                issues.append(f"05_FINAL_ARCHIVE มีไฟล์ที่ไม่ได้ผ่านระบบอนุมัติ: {name}/{f}")
    for x in issues:
        print("✖", x)
    print("✔ ทะเบียนและไฟล์ตรงกันทั้งหมด" if not issues else f"พบปัญหา {len(issues)} รายการ แจ้งผู้ดูแล")
    return 1 if issues else 0


README_DOC = """# VIDEO_WORKFLOW (ระบบควบคุมเอกสารวิดีโอ)

| โฟลเดอร์ | ใช้ทำอะไร |
|---|---|
| 01_INCOMING | ต้นฉบับทุกเวอร์ชันที่รับเข้ามา (ห้ามลบ/แก้) |
| 02_REVIEW_QUEUE | คลิปที่ตรวจครบแล้ว รอ FINAL APPROVER |
| 03_REVISION | คลิปที่ไม่ผ่าน + ไฟล์ FEEDBACK.md ส่งกลับทีมผู้ผลิต |
| 04_APPROVED | ฉบับที่อนุมัติแล้ว |
| 05_FINAL_ARCHIVE | ฉบับสุดท้ายที่ตรวจสอบแล้ว แยกตาม PROJECT (ห้ามเขียนทับ) |
| 06_DOCUMENTATION | register.json / register.csv (ทะเบียน), history.jsonl (ประวัติ), reports, decisions, notices, orders |

ชื่อไฟล์: `[PROJECT]_[VIDEO-ID]_[CONTENT-NAME]_V[VERSION]_[STATUS].mp4` เช่น `HISTORY_V001_SAMURAI_V02_REVISION.mp4`
ทุกการย้าย/คัดลอกทำผ่าน `doc_control.py` เท่านั้น (ตรวจ sha256 ทุกครั้ง) อย่าย้ายไฟล์ด้วยมือ
"""


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="โฟลเดอร์ระบบ (ค่าเริ่มต้น: VIDEO_WORKFLOW_ROOT, production.config.json หรือ D:\\VIDEO_WORKFLOW บน Windows)")
    ap.add_argument("--config", help="production.config.json")
    ap.add_argument("--actor", default=ACTOR, help="ชื่อผู้ทำรายการ (บันทึกในประวัติ)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    r = sub.add_parser("receive")
    r.add_argument("file")
    r.add_argument("--project", required=True, help="เช่น HISTORY, NEWS, DOC (A-Z 0-9 -)")
    r.add_argument("--name", required=True, help="CONTENT-NAME เช่น SAMURAI (A-Z 0-9 -)")
    r.add_argument("--title", help="ชื่อคลิปภาษาไทย (Video Name)")
    r.add_argument("--producer")
    r.add_argument("--coordinator")
    r.add_argument("--order", help="เลขใบสั่งผลิต (ORD-...)")
    r.add_argument("--allow-same-name", action="store_true")
    rs = sub.add_parser("resubmit")
    rs.add_argument("video_id")
    rs.add_argument("file")
    rs.add_argument("--producer")
    rs.add_argument("--changes", help="แก้อะไรไปบ้างตาม feedback")
    up = sub.add_parser("update")
    up.add_argument("video_id")
    up.add_argument("--producer")
    up.add_argument("--coordinator")
    up.add_argument("--title")
    up.add_argument("--order")
    og = sub.add_parser("organize")
    og.add_argument("video_id")
    qu = sub.add_parser("queue")
    qu.add_argument("--json", action="store_true")
    de = sub.add_parser("decide")
    de.add_argument("video_id", nargs="?")
    de.add_argument("--approve", action="store_true")
    de.add_argument("--reject", action="store_true")
    de.add_argument("--version", type=int)
    de.add_argument("--approver", help="ชื่อ FINAL APPROVER (มนุษย์)")
    de.add_argument("--evidence", help="หลักฐาน เช่น ข้อความอนุมัติของผู้ใช้ในแชต พร้อมวันเวลา")
    de.add_argument("--notes", help="เหตุผล/ข้อเสนอแนะ (บังคับเมื่อไม่อนุมัติ)")
    de.add_argument("--from-decision", help="ไฟล์ผลการตัดสินใจจากหน้าเว็บ (06_DOCUMENTATION/decisions/*.json)")
    de.add_argument("--no-archive", action="store_true")
    sub.add_parser("process-decisions")
    ar = sub.add_parser("archive")
    ar.add_argument("video_id")
    stt = sub.add_parser("status")
    stt.add_argument("video_id", nargs="?")
    stt.add_argument("--json", action="store_true")
    se = sub.add_parser("search")
    se.add_argument("text", nargs="?")
    se.add_argument("--project")
    se.add_argument("--status")
    hi = sub.add_parser("history")
    hi.add_argument("video_id")
    rp = sub.add_parser("report")
    rp.add_argument("--date", help="YYYY-MM-DD (ค่าเริ่มต้นวันนี้)")
    sub.add_parser("export")
    sub.add_parser("verify")
    a = ap.parse_args(argv)
    cmds = {"init": cmd_init, "receive": cmd_receive, "resubmit": cmd_resubmit, "update": cmd_update,
            "organize": cmd_organize, "queue": cmd_queue, "decide": cmd_decide,
            "process-decisions": cmd_process_decisions, "archive": cmd_archive, "status": cmd_status,
            "search": cmd_search, "history": cmd_history, "report": cmd_report, "export": cmd_export,
            "verify": cmd_verify}
    try:
        return cmds[a.cmd](a, load_config(a.config))
    except DCError as e:
        print(f"✖ {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
