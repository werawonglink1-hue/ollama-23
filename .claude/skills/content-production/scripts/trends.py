#!/usr/bin/env python3
"""ดึงกระแสประจำวันของไทยจากแหล่งสาธารณะ รวมเป็นรายการหัวข้อพร้อมคะแนนตั้งต้น ให้ Trend Researcher คัด Top 10 ต่อ

แหล่ง (ไม่ต้องใช้คีย์):
  google-trends  คำค้นที่กำลังพุ่งวันนี้ (Google Trends RSS) พร้อมยอดค้นหาโดยประมาณ + ข่าวที่เกี่ยวข้อง
  google-news    ข่าวเด่นภาษาไทยตอนนี้ (Google News RSS)
  wikipedia      บทความวิกิพีเดียภาษาไทยที่คนอ่านมากที่สุดเมื่อวาน + เหตุการณ์ "วันนี้ในอดีต" (เหมาะกับแนวประวัติศาสตร์/บุคคล)

  python3 trends.py fetch --out work/ORD-20261121-01/trends.json --md work/ORD-20261121-01/trends.md
  python3 trends.py fetch --sources google-trends,wikipedia --limit 40

คะแนนเป็นแค่จุดตั้งต้น (กระแส + จำนวนแหล่งที่พูดถึง + ความใหม่) การเลือกหัวข้อจริงต้องผ่านการตรวจข้อเท็จจริงของ agent เสมอ
แหล่งไหนเข้าไม่ได้ สคริปต์จะบอกใน errors และทำงานต่อด้วยแหล่งที่เหลือ (ห้ามเดาข้อมูลแทน)
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "SocialVideoStudio-TrendResearch/1.0 (daily topic research)"
GT_NS = {"ht": "https://trends.google.com/trending/rss"}


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/json, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_date(s):
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def traffic_num(s):
    m = re.match(r"([\d,.]+)\s*([KkMm]?)", (s or "").replace("+", ""))
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1))


def google_trends(geo):
    root = ET.fromstring(get(f"https://trends.google.com/trending/rss?geo={geo}"))
    out = []
    for it in root.iter("item"):
        news = [{"title": clean(n.findtext("ht:news_item_title", "", GT_NS)),
                 "url": n.findtext("ht:news_item_url", "", GT_NS),
                 "source": clean(n.findtext("ht:news_item_source", "", GT_NS))}
                for n in it.findall("ht:news_item", GT_NS)]
        out.append({"title": clean(it.findtext("title")), "kind": "search", "source": "Google Trends",
                    "traffic": traffic_num(it.findtext("ht:approx_traffic", "", GT_NS)),
                    "published": (parse_date(it.findtext("pubDate")) or dt.datetime.now(dt.timezone.utc)).isoformat(),
                    "links": [n["url"] for n in news if n["url"]][:3], "news": news[:3]})
    return out


def google_news(lang, geo):
    url = f"https://news.google.com/rss?hl={lang}&gl={geo}&ceid={geo}:{lang}"
    root = ET.fromstring(get(url))
    out = []
    for it in root.iter("item"):
        title = clean(it.findtext("title"))
        src = clean(it.findtext("source")) or (title.rsplit(" - ", 1)[-1] if " - " in title else "")
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        pub = parse_date(it.findtext("pubDate"))
        out.append({"title": title, "kind": "news", "source": f"Google News · {src}".strip(" ·"), "traffic": 0,
                    "published": pub.isoformat() if pub else "", "links": [it.findtext("link") or ""]})
    return out


def wikipedia(lang, day):
    y, m, d = day.strftime("%Y"), day.strftime("%m"), day.strftime("%d")
    data = json.loads(get(f"https://api.wikimedia.org/feed/v1/wikipedia/{lang}/featured/{y}/{m}/{d}"))
    out = []
    for a in (data.get("mostread") or {}).get("articles", [])[:30]:
        title = (a.get("titles") or {}).get("normalized") or a.get("title", "")
        if title.startswith(("หน้าหลัก", "พิเศษ:", "Special:", "Main Page")):
            continue
        out.append({"title": title, "kind": "wiki", "source": "Wikipedia อ่านมากสุด", "traffic": 0,
                    "views": a.get("views", 0), "published": day.isoformat(), "summary": clean(a.get("extract", ""))[:240],
                    "links": [((a.get("content_urls") or {}).get("desktop") or {}).get("page", "")]})
    today = dt.date.today()
    events, ev_lang = [], lang
    for ev_lang in (lang, "en"):  # วิกิพีเดียไทยมักไม่มี "วันนี้ในอดีต" ใช้ภาษาอังกฤษแทน (agent แปลเอง)
        try:
            events = json.loads(get(f"https://api.wikimedia.org/feed/v1/wikipedia/{ev_lang}/onthisday/selected/"
                                    f"{today.strftime('%m')}/{today.strftime('%d')}")).get("selected") or []
        except Exception:  # noqa: BLE001 - ไม่มีข้อมูลวันนี้ในอดีตของภาษานั้น
            events = []
        if events:
            break
    for e in events[:15]:
        pages = e.get("pages") or []
        out.append({"title": clean(e.get("text", ""))[:160], "kind": "onthisday",
                    "source": f"วันนี้ในอดีต {e.get('year')} ({ev_lang})", "traffic": 0, "year": e.get("year"),
                    "published": today.isoformat(),
                    "links": [((p.get("content_urls") or {}).get("desktop") or {}).get("page", "") for p in pages[:2]]})
    return out


def tokens(s):
    s = s.lower()
    words = set(re.findall(r"[a-z0-9]{3,}", s))
    thai = re.sub(r"[^฀-๿]", "", s)
    words |= {thai[i:i + 4] for i in range(0, max(0, len(thai) - 3))}  # ตัดเป็นชิ้น 4 ตัวอักษร (ไทยไม่มีช่องว่างระหว่างคำ)
    return words


def merge(items):
    """รวมหัวข้อที่พูดถึงเรื่องเดียวกันจากหลายแหล่ง แล้วให้คะแนนตั้งต้น"""
    groups = []
    for it in items:
        tk = tokens(it["title"] + " " + " ".join(n["title"] for n in it.get("news", [])))
        best, best_sim = None, 0.0
        for g in groups:
            inter = len(tk & g["tk"])
            sim = inter / max(1, min(len(tk), len(g["tk"])))
            if sim > best_sim:
                best, best_sim = g, sim
        if best and best_sim >= 0.35:
            best["items"].append(it)
            best["tk"] |= tk
        else:
            groups.append({"tk": tk, "items": [it]})
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for g in groups:
        its = g["items"]
        lead = max(its, key=lambda x: (x["kind"] == "search", x.get("traffic", 0), x.get("views", 0)))
        traffic = max(x.get("traffic", 0) for x in its)
        views = max(x.get("views", 0) for x in its)
        sources = sorted({x["source"] for x in its})
        ages = []
        for x in its:
            try:
                ages.append((now - dt.datetime.fromisoformat(x["published"])).total_seconds() / 3600)
            except (KeyError, ValueError, TypeError):
                pass
        age = min(ages) if ages else 48
        score = (2.0 * math.log10(traffic + 1) + 1.2 * math.log10(views + 1) + 1.5 * (len(sources) - 1)
                 + (2 if age <= 24 else 1 if age <= 48 else 0) + (0.5 if lead["kind"] == "onthisday" else 0))
        links = []
        for x in its:
            for u in x.get("links", []):
                if u and u not in links:
                    links.append(u)
        out.append({"topic": lead["title"], "score": round(score, 2), "kinds": sorted({x["kind"] for x in its}),
                    "sources": sources, "traffic": traffic, "views": views, "ageHours": round(age, 1),
                    "related": [x["title"] for x in its if x is not lead][:4],
                    "summary": next((x.get("summary") for x in its if x.get("summary")), ""), "links": links[:5]})
    return sorted(out, key=lambda x: -x["score"])


def to_md(res):
    lines = [f"# กระแสประจำวัน {res['date']} ({res['geo']})", "",
             f"แหล่ง: {', '.join(res['sourcesOk']) or '-'}" + (f" · เข้าไม่ได้: {'; '.join(res['errors'])}" if res["errors"] else ""),
             "", "| # | หัวข้อ | คะแนน | ประเภท | ยอดค้นหา/อ่าน | อายุ (ชม.) | แหล่ง | ลิงก์ |", "|---|---|---|---|---|---|---|---|"]
    for i, t in enumerate(res["topics"], 1):
        vol = f"{t['traffic']:,}+" if t["traffic"] else (f"{t['views']:,} อ่าน" if t["views"] else "-")
        link = f"[ลิงก์]({t['links'][0]})" if t["links"] else ""
        lines.append(f"| {i} | {t['topic'].replace('|', '/')} | {t['score']} | {','.join(t['kinds'])} | {vol} | "
                     f"{t['ageHours']} | {'; '.join(t['sources'])[:60]} | {link} |")
    lines += ["", "คะแนนเป็นจุดตั้งต้นเท่านั้น ต้องตรวจข้อเท็จจริงและความเหมาะสมกับแนวคลิปก่อนเลือก"]
    return "\n".join(lines) + "\n"


def cmd_fetch(a):
    srcs = [s.strip() for s in a.sources.split(",") if s.strip()]
    items, ok, errors = [], [], []
    day = dt.date.today() - dt.timedelta(days=1)
    for s in srcs:
        try:
            if s == "google-trends":
                got = google_trends(a.geo)
            elif s == "google-news":
                got = google_news(a.lang, a.geo)
            elif s == "wikipedia":
                got = wikipedia(a.lang, day)
            else:
                raise ValueError(f"ไม่รู้จักแหล่ง {s}")
            items += got
            ok.append(f"{s} ({len(got)})")
        except Exception as e:  # noqa: BLE001 - แหล่งหนึ่งล้ม ไม่ให้ทั้งงานล้ม แต่ต้องรายงาน
            errors.append(f"{s}: {e}")
    res = {"date": dt.date.today().isoformat(), "geo": a.geo, "sourcesOk": ok, "errors": errors,
           "topics": merge(items)[: a.limit]}
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        open(a.out, "w", encoding="utf-8").write(text)
    if a.md:
        os.makedirs(os.path.dirname(os.path.abspath(a.md)) or ".", exist_ok=True)
        open(a.md, "w", encoding="utf-8").write(to_md(res))
    if not a.out:
        print(text)
    print(f"✔ {len(res['topics'])} หัวข้อ จาก {', '.join(ok) or 'ไม่มีแหล่งที่เข้าได้'}", file=sys.stderr)
    for e in errors:
        print(f"⚠ เข้าไม่ได้: {e}", file=sys.stderr)
    return 0 if ok else 1


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--geo", default="TH")
    f.add_argument("--lang", default="th")
    f.add_argument("--sources", default="google-trends,google-news,wikipedia")
    f.add_argument("--limit", type=int, default=30)
    f.add_argument("--out")
    f.add_argument("--md")
    a = ap.parse_args(argv)
    return cmd_fetch(a)


if __name__ == "__main__":
    sys.exit(main())
