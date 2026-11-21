#!/usr/bin/env python3
"""กระดานงานฝ่ายผลิต: ใบสั่งผลิต (แนวคลิป + จำนวน) และสถานะของแต่ละแผนกต่อคลิป

เก็บใน <VIDEO_WORKFLOW>/06_DOCUMENTATION/orders/ORD-YYYYMMDD-NN.json (หน้า Office อ่านไฟล์เหล่านี้แสดงสถานะสด)

  new   --genre "ประวัติศาสตร์" --count 3      เปิดใบสั่งผลิต (ผู้ใช้ให้แค่แนวคลิปกับจำนวน)
  set   ORD --clip 2 --dept visual --status working --note "..."   อัปเดตสถานะแผนก (ทุกแผนกเรียกเมื่อเริ่ม/เสร็จ/ส่งกลับ)
        ตั้งข้อมูลคลิปได้ด้วย --topic --title --project --content --video-id --style
  show  [ORD]    ดูใบสั่ง (ไม่ใส่ = ใบล่าสุด)
  list           ใบสั่งทั้งหมด

แผนก: trend · creative · visual · voice · edit · qc · doc     สถานะ: waiting · working · done · returned · blocked
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "video-document-control", "scripts"))
import doc_control as dc  # noqa: E402

DEPTS = ["trend", "creative", "visual", "voice", "edit", "qc", "doc"]
DEPT_TH = {"trend": "วิจัยกระแส", "creative": "ครีเอทีฟ", "visual": "ผลิตภาพ", "voice": "เสียง/ดนตรี",
           "edit": "ตัดต่อ", "qc": "ตรวจคุณภาพ", "doc": "ควบคุมเอกสาร"}
DEPT_SHORT = {"trend": "กระแส", "creative": "บท", "visual": "ภาพ", "voice": "เสียง", "edit": "ตัดต่อ", "qc": "QC",
              "doc": "เอกสาร"}
STATES = ["waiting", "working", "done", "returned", "blocked"]
ICON = {"waiting": "○", "working": "●", "done": "✓", "returned": "↩", "blocked": "✖"}


def orders_dir(root):
    d = os.path.join(root, dc.DOC, "orders")
    os.makedirs(d, exist_ok=True)
    return d


def load(root, oid):
    p = os.path.join(orders_dir(root), f"{oid}.json")
    if not os.path.exists(p):
        raise dc.DCError(f"ไม่พบใบสั่ง {oid}")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save(root, order):
    order["updatedAt"] = dc.now()
    order["status"] = overall(order)
    p = os.path.join(orders_dir(root), f"{order['orderId']}.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(order, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def overall(order):
    clips = order["clips"]
    st = [c["depts"][d]["status"] for c in clips for d in DEPTS]
    if all(c["depts"]["doc"]["status"] == "done" for c in clips):
        return "DONE"
    if any(s == "blocked" for s in st):
        return "BLOCKED"
    if all(s == "waiting" for s in st):
        return "NEW"
    if all(c["depts"]["qc"]["status"] == "done" for c in clips):
        return "IN_REVIEW"
    return "IN_PROGRESS"


def latest(root):
    files = sorted(glob.glob(os.path.join(orders_dir(root), "ORD-*.json")))
    if not files:
        raise dc.DCError("ยังไม่มีใบสั่งผลิต")
    return os.path.splitext(os.path.basename(files[-1]))[0]


def cmd_new(a, cfg):
    root = dc.require_root(dc.resolve_root(a.root, cfg))
    if not 1 <= a.count <= int(cfg.get("maxClipsPerOrder", 10)):
        raise dc.DCError(f"จำนวนคลิปต้องอยู่ระหว่าง 1–{cfg.get('maxClipsPerOrder', 10)}")
    with dc.Lock(root):
        day = dc.today().replace("-", "")
        n = len(glob.glob(os.path.join(orders_dir(root), f"ORD-{day}-*.json"))) + 1
        oid = f"ORD-{day}-{n:02d}"
        order = {"orderId": oid, "genre": a.genre.strip(), "count": a.count, "style": a.style or "",
                 "formats": (a.formats or "9x16,16x9").split(","), "note": a.note or "", "createdAt": dc.now(),
                 "requestedBy": a.by or "Creative Director",
                 "clips": [{"n": i + 1, "topic": "", "title": "", "project": "", "contentName": "", "videoId": "",
                            "depts": {d: {"status": "waiting", "note": "", "at": ""} for d in DEPTS}}
                           for i in range(a.count)]}
        save(root, order)
        dc.log(root, "ORDER_NEW", actor=a.actor, order=oid, genre=order["genre"], count=a.count)
    print(f"✔ เปิดใบสั่ง {oid}: {order['genre']} × {a.count} คลิป")
    print(f"   ไฟล์: {os.path.join(orders_dir(root), oid + '.json')}")
    return 0


def cmd_set(a, cfg):
    root = dc.require_root(dc.resolve_root(a.root, cfg))
    with dc.Lock(root):
        order = load(root, a.order)
        if not 1 <= a.clip <= len(order["clips"]):
            raise dc.DCError(f"ใบสั่ง {a.order} มี {len(order['clips'])} คลิป")
        clip = order["clips"][a.clip - 1]
        for key, val in (("topic", a.topic), ("title", a.title), ("project", a.project),
                         ("contentName", a.content), ("videoId", a.video_id), ("style", a.style)):
            if val is not None:
                clip[key] = val
        if a.dept:
            if a.dept not in DEPTS:
                raise dc.DCError(f"แผนกต้องเป็น {', '.join(DEPTS)}")
            if a.status not in STATES:
                raise dc.DCError(f"สถานะต้องเป็น {', '.join(STATES)}")
            d = clip["depts"][a.dept]
            if a.status == "returned" and not (a.note or "").strip():
                raise dc.DCError("ส่งงานกลับต้องบอกเหตุผล (--note) ให้ทีมที่รับผิดชอบแก้ได้ตรงจุด")
            d.update({"status": a.status, "note": a.note or d.get("note", ""), "at": dc.now(), "by": a.actor})
            if a.status == "returned":
                d["rounds"] = d.get("rounds", 0) + 1
        save(root, order)
        dc.log(root, "ORDER_UPDATE", actor=a.actor, order=a.order, clip=a.clip, dept=a.dept, status=a.status,
               note=a.note)
    dept = f" · {DEPT_TH.get(a.dept, a.dept)} → {a.status}" if a.dept else ""
    print(f"✔ {a.order} คลิป {a.clip}{dept}" + (f" · {a.note}" if a.note else ""))
    return 0


def render(order):
    lines = [f"{order['orderId']} · {order['genre']} × {order['count']} · {order['status']} · สร้าง {order['createdAt'][:16]}"]
    head = "      " + " ".join(f"{DEPT_SHORT[d]:<7}" for d in DEPTS)
    lines.append(head)
    for c in order["clips"]:
        row = " ".join(f"{ICON[c['depts'][d]['status']]:<7}" for d in DEPTS)
        name = c.get("title") or c.get("topic") or "(ยังไม่มีหัวข้อ)"
        lines.append(f"  #{c['n']:<2} {row} {name}" + (f" [{c['videoId']}]" if c.get("videoId") else ""))
        for d in DEPTS:
            x = c["depts"][d]
            if x["status"] in ("returned", "blocked") and x.get("note"):
                lines.append(f"       {ICON[x['status']]} {DEPT_TH[d]}: {x['note']}")
    return "\n".join(lines)


def cmd_show(a, cfg):
    root = dc.require_root(dc.resolve_root(a.root, cfg))
    order = load(root, a.order or latest(root))
    print(json.dumps(order, ensure_ascii=False, indent=1) if a.json else render(order))
    return 0


def cmd_list(a, cfg):
    root = dc.require_root(dc.resolve_root(a.root, cfg))
    files = sorted(glob.glob(os.path.join(orders_dir(root), "ORD-*.json")))
    if not files:
        print("ยังไม่มีใบสั่งผลิต")
    for f in files:
        with open(f, encoding="utf-8") as fh:
            o = json.load(fh)
        print(f"{o['orderId']} · {o['status']:<11} · {o['genre']} × {o['count']} · {o['createdAt'][:16]}")
    return 0


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    ap.add_argument("--config")
    ap.add_argument("--actor", default="AI Production Office")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--genre", required=True)
    n.add_argument("--count", type=int, required=True)
    n.add_argument("--style", help="visualStyle เช่น cinematic, collage")
    n.add_argument("--formats", help="9x16,16x9")
    n.add_argument("--note")
    n.add_argument("--by", help="ผู้สั่ง (ค่าเริ่มต้น Creative Director)")
    s = sub.add_parser("set")
    s.add_argument("order")
    s.add_argument("--clip", type=int, required=True)
    s.add_argument("--dept")
    s.add_argument("--status", default="working")
    s.add_argument("--note")
    s.add_argument("--topic")
    s.add_argument("--title")
    s.add_argument("--project")
    s.add_argument("--content")
    s.add_argument("--video-id")
    s.add_argument("--style")
    sh = sub.add_parser("show")
    sh.add_argument("order", nargs="?")
    sh.add_argument("--json", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    try:
        cfg = dc.load_config(a.config)
        return {"new": cmd_new, "set": cmd_set, "show": cmd_show, "list": cmd_list}[a.cmd](a, cfg)
    except dc.DCError as e:
        print(f"✖ {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
