#!/usr/bin/env python3
"""หาภาพประกอบจากเว็บที่ "ใช้ได้ถูกลิขสิทธิ์" พร้อมเครดิต: Wikimedia Commons + Openverse

  search   ค้นภาพ แสดงผู้สร้าง สัญญาอนุญาต ขนาด และลิงก์ (บันทึกผลไว้ใน --save เพื่อเลือกต่อ)
  download ดาวน์โหลดภาพที่เลือก บันทึกเครดิตลง credits.json และ (ถ้าระบุ) ใส่ไฟล์ + เครดิตลงฉากใน project.json

ตัวอย่าง:
  python3 find_images.py search "Mekong river village dawn" --limit 8 --save work/runner/candidates.json
  python3 find_images.py download work/runner/candidates.json 2 --out work/runner/media/clip1-scene3.jpg \\
          --credits work/runner/credits.json --project work/runner/project.json --clip 1 --scene 3

ค่าเริ่มต้นรับเฉพาะสัญญาอนุญาตที่ใช้เชิงพาณิชย์และดัดแปลงได้ (CC0, Public domain, CC BY, CC BY-SA)
เพราะช่องโซเชียลที่สร้างรายได้ถือเป็นการใช้เชิงพาณิชย์; --allow-nc เปิดรับ NC/ND สำหรับงานที่ไม่หารายได้เท่านั้น
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

UA = "SocialVideoStudio-ImageResearch/1.0 (licensed stock lookup)"
COMMONS = "https://commons.wikimedia.org/w/api.php"
OPENVERSE = "https://api.openverse.org/v1/images/"


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def license_ok(lic, allow_nc=False):
    lic_l = (lic or "").lower()
    if not lic_l or "fair use" in lic_l or "copyright" in lic_l and "free" not in lic_l:
        return False
    if not allow_nc and re.search(r"(^|[\s\-])(nc|nd)([\s\-]|$)|noncommercial|noderiv", lic_l):
        return False
    return any(k in lic_l for k in ("cc0", "public domain", "pdm", "cc by", "cc-by", "by-sa", "by ", "attribution")) or lic_l in ("by", "by-sa", "cc0", "pdm")


def search_commons(q, limit, allow_nc):
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{q} filetype:bitmap",
              "gsrnamespace": "6", "gsrlimit": str(limit * 2), "prop": "imageinfo",
              "iiprop": "url|extmetadata|size|mime", "iiurlwidth": "1600"}
    data = json.loads(_get(COMMONS + "?" + urllib.parse.urlencode(params)))
    out = []
    for page in sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        ii = (page.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = _clean((meta.get("LicenseShortName") or {}).get("value"))
        if not license_ok(lic, allow_nc) or not ii.get("url"):
            continue
        out.append({"source": "Wikimedia Commons", "title": page.get("title", "").replace("File:", ""),
                    "author": _clean((meta.get("Artist") or {}).get("value")) or "ไม่ระบุ",
                    "license": lic, "license_url": (meta.get("LicenseUrl") or {}).get("value", ""),
                    "width": ii.get("width"), "height": ii.get("height"),
                    "file_url": ii.get("thumburl") or ii.get("url"), "original_url": ii.get("url"),
                    "page_url": ii.get("descriptionurl", "")})
    return out[:limit]


def search_openverse(q, limit, allow_nc):
    params = {"q": q, "page_size": str(min(20, limit * 2))}
    if not allow_nc:
        params["license_type"] = "commercial,modification"
    data = json.loads(_get(OPENVERSE + "?" + urllib.parse.urlencode(params)))
    out = []
    for it in data.get("results", []):
        lic = f"CC {it.get('license', '').upper()} {it.get('license_version') or ''}".strip()
        if it.get("license") in ("cc0", "pdm"):
            lic = "CC0" if it.get("license") == "cc0" else "Public domain"
        if not license_ok(lic, allow_nc):
            continue
        out.append({"source": f"Openverse/{it.get('source') or it.get('provider') or ''}".rstrip("/"),
                    "title": it.get("title") or "", "author": it.get("creator") or "ไม่ระบุ", "license": lic,
                    "license_url": it.get("license_url") or "", "width": it.get("width"), "height": it.get("height"),
                    "file_url": it.get("url"), "original_url": it.get("url"), "page_url": it.get("foreign_landing_url") or ""})
    return out[:limit]


def credit_line(c):
    """บรรทัดเครดิตสั้นสำหรับ `เครดิต:` ในบรรทัดฉาก (แสดงมุมขวาบนของการ์ด)"""
    author = c["author"] if len(c["author"]) <= 40 else c["author"][:37] + "..."
    return f"{author} / {c['source'].split('/')[0]} ({c['license']})"


def cmd_search(a):
    srcs = [s.strip() for s in a.source.split(",")]
    results, errors = [], []
    for s in srcs:
        try:
            results += search_commons(a.query, a.limit, a.allow_nc) if s == "commons" else search_openverse(a.query, a.limit, a.allow_nc)
        except Exception as e:  # noqa: BLE001 - รายงานแหล่งที่ใช้ไม่ได้ แต่ยังแสดงแหล่งอื่น
            errors.append(f"{s}: {e}")
    for i, c in enumerate(results):
        print(f"[{i}] {c['source']} · {c['license']} · {c['width']}×{c['height']} · {c['author'][:50]}\n    {c['title'][:90]}\n    {c['page_url']}")
    for e in errors:
        print("⚠ ค้นไม่ได้:", e, file=sys.stderr)
    if not results:
        print("ไม่พบภาพที่สัญญาอนุญาตใช้ได้ ลองคำค้นภาษาอังกฤษ/ชื่อสถานที่ หรือคำที่กว้างขึ้น", file=sys.stderr)
    if a.save:
        os.makedirs(os.path.dirname(os.path.abspath(a.save)), exist_ok=True)
        json.dump({"query": a.query, "results": results}, open(a.save, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0 if results else 1


def _patch_scene(project_path, clip_no, scene_no, media_rel, credit):
    """ใส่ไฟล์ภาพลง clips[i].scenes[j].media และเติม `| เครดิต: ...` ในบรรทัดฉากที่ j ของสคริปต์"""
    p = json.load(open(project_path, encoding="utf-8"))
    clip = p["clips"][clip_no - 1]
    scenes = clip.setdefault("scenes", [])
    while len(scenes) < scene_no:
        scenes.append({})
    scenes[scene_no - 1]["media"] = media_rel
    lines, k = clip["script"].splitlines(), 0
    for idx, line in enumerate(lines):
        if re.match(r"^\s*\[\s*ฉาก\s*[:：]", line):
            k += 1
            if k == scene_no:
                body = line.strip()[1:-1]
                body = re.sub(r"\s*\|\s*เครดิต\s*[:：][^|]*", "", body)
                lines[idx] = f"[{body} | เครดิต: {credit}]"
                break
    clip["script"] = "\n".join(lines)
    json.dump(p, open(project_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def cmd_download(a):
    data = json.load(open(a.candidates, encoding="utf-8"))
    c = data["results"][a.index]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    blob = _get(c["file_url"], timeout=60)
    with open(a.out, "wb") as fh:
        fh.write(blob)
    rec = dict(c, file=os.path.abspath(a.out), credit=credit_line(c), query=data.get("query"))
    if a.credits:
        allc = json.load(open(a.credits, encoding="utf-8")) if os.path.exists(a.credits) else []
        allc = [x for x in allc if x.get("file") != rec["file"]] + [rec]
        json.dump(allc, open(a.credits, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.project:
        rel = os.path.relpath(os.path.abspath(a.out), os.path.dirname(os.path.abspath(a.project)))
        _patch_scene(a.project, a.clip, a.scene, rel, rec["credit"])
    print(f"✔ {a.out} ({len(blob) // 1024} KB)\n  เครดิต: {rec['credit']}\n  ที่มา: {c['page_url']}")
    return 0


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--source", default="commons,openverse")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--allow-nc", action="store_true", help="รับ NC/ND (ห้ามใช้กับช่องที่หารายได้)")
    s.add_argument("--save")
    d = sub.add_parser("download")
    d.add_argument("candidates")
    d.add_argument("index", type=int)
    d.add_argument("--out", required=True)
    d.add_argument("--credits")
    d.add_argument("--project")
    d.add_argument("--clip", type=int, default=1)
    d.add_argument("--scene", type=int, default=1)
    a = ap.parse_args(argv)
    return cmd_search(a) if a.cmd == "search" else cmd_download(a)


if __name__ == "__main__":
    sys.exit(main())
