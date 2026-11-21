#!/usr/bin/env python3
"""เสียงพากย์จริง (Higgsfield TTS หรืออัดเอง) + จังหวะเว้นวรรคของสคริปต์ + ซับตรงเสียง

1) prepare  : สคริปต์ → ข้อความสำหรับ TTS + พารามิเตอร์ Higgsfield (qwen_audio_tts ภาษาไทย ปรับอารมณ์ตามผู้เล่า)
2) align    : เสียง + เวลาแต่ละคำจาก Whisper → เวลาเริ่ม/จบของทุกท่อนซับในไฟล์เสียงเดิม
3) assemble : ตัดเสียงตรง // และ /// แล้วใส่ความเงียบตามที่สคริปต์กำหนด (เสียง AI จะไม่เว้นจังหวะเอง)
              → ได้ไฟล์เสียงใหม่ + timings ที่ render.py และเว็บใช้ได้ทันที (ใส่ --project เพื่อเขียนลง project.json)

เวลาแต่ละคำ (--words) รับได้ทั้ง
  - faster-whisper:   [{"word": "...", "start": 1.2, "end": 1.5}, ...]  (วินาที)
  - auto-editor whisper --format json --split-words:  บรรทัดละ {"start": 1200, "end": 1500, "text": "..."} (มิลลิวินาที)

ตัวอย่าง:
  python3 voice_align.py prepare script.txt --narrator doc --speed normal > tts.json
  auto-editor whisper voice.wav ggml-large-v3.bin -l th --format json --split-words -o words.json
  python3 voice_align.py assemble script.txt --voice voice.wav --words words.json --out voice_paced.wav \\
          --speed normal --project project.json --clip 1
"""
from __future__ import annotations

import argparse
import array
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_subs as bs  # noqa: E402

INSTRUCTIONS = {  # ≤128 ตัวอักษร (ข้อจำกัดของ qwen_audio_tts)
    "doc": "เล่าแบบสารคดี น้ำเสียงหนักแน่น อบอุ่น เร้าใจ ชัดถ้อยชัดคำ ลงน้ำหนักคำสำคัญ",
    "lamun": "เล่าเรื่องนุ่มนวล อบอุ่น ช้า ๆ ชวนฝัน บางช่วงกระซิบเบา ๆ",
    "kru-nong": "คุณครูอนุบาลใจดีเล่านิทาน น้ำเสียงสดใส อ่อนโยน ยิ้มในเสียง",
    "mana": "อ่านแบบเรียนภาษาไทยสำหรับเด็ก ชัดเจน ช้า เรียบง่าย อบอุ่น",
    "mystery": "เล่าเรื่องลึกลับ เสียงต่ำ นุ่ม ระทึกเบา ๆ กระซิบบางช่วง",
    "funny": "เล่าแบบขำ ๆ อารมณ์ดี เป็นกันเอง สนุกสนาน",
}
RATE = {"slow": 0.9, "normal": 1.0, "fast": 1.1}
_KEEP = re.compile(r"[฀-๿A-Za-z0-9]")


def norm(s: str) -> str:
    """ตัดช่องว่าง เครื่องหมาย และ * ออก เหลือตัวอักษรไทย/อังกฤษ/ตัวเลข สำหรับเทียบข้อความ"""
    return "".join(ch for ch in s.replace("*", "") if _KEEP.match(ch)).lower()


def speakable(text: str) -> str:
    """เอาช่องว่างระหว่างคำไทยออก (ที่ใส่ไว้ทำซับคำต่อคำ) ไม่งั้นเสียงอ่านจะสะดุด"""
    return re.sub(r"([฀-๿])\s+(?=[฀-๿])", r"\1", text.replace("*", "")).strip()


# ---------------- prepare ----------------
def tts_text(chunks) -> str:
    out = []
    for c in chunks:
        out.append(speakable(c.text))
        out.append({"": " ", "/": " ", "//": "\n", "///": "\n\n"}.get(c.pause, " "))
    return "".join(out).strip()


def cmd_prepare(a):
    scenes, chunks = bs.parse_script(open(a.script, encoding="utf-8").read())
    if a.cast:  # หลายเสียง: หนึ่งคำขอต่อช่วงผู้พูด
        p = json.load(open(a.cast, encoding="utf-8"))
        clip = p["clips"][a.clip - 1] if "clips" in p else {}
        cast = {**(p.get("cast") or {}), **(clip.get("cast") or {})}
        parts, missing = voice_parts(chunks, cast, p.get("narratorStyle", a.narrator), p.get("speed", a.speed), a.clip)
        json.dump({"parts": parts, "missingCast": missing,
                   "after": "whisper_words.py ทีละไฟล์ (<target>-words.json) แล้ว voice_align.py assemble-cast"},
                  sys.stdout, ensure_ascii=False, indent=1)
        print()
        if missing:
            print(f"⚠ ยังไม่ได้แคสต์เสียงให้: {', '.join(missing)} (ใส่ใน cast ของ project.json)", file=sys.stderr)
        return 0
    text = tts_text(chunks)
    params = {"model": "qwen_audio_tts", "prompt": text, "language": "th",
              "instruction": INSTRUCTIONS.get(a.narrator, INSTRUCTIONS["doc"])[:128],
              "voice_type": "preset", "voice_id": a.voice_id or "<เลือกจาก list_voices>",
              "format": "wav", "sample_rate": 44100, "speech_rate": RATE.get(a.speed, 1.0)}
    json.dump({"generate_audio_params": params, "chars": len(text), "chunks": [c.plain for c in chunks]},
              sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


# ---------------- words / align ----------------
def load_words(path):
    raw = open(path, encoding="utf-8").read().strip()
    if raw.startswith("["):
        items = json.loads(raw)
    elif raw.startswith("{") and "\n" not in raw:
        data = json.loads(raw)
        items = data.get("words") or [w for seg in data.get("segments", []) for w in seg.get("words", [])]
    else:  # JSON Lines (auto-editor)
        items = [json.loads(line) for line in raw.splitlines() if line.strip()]
    words = []
    for it in items:
        t = it.get("word", it.get("text", ""))
        if it.get("start") is None or it.get("end") is None:
            continue
        words.append({"text": str(t), "start": float(it["start"]), "end": float(it["end"])})
    if words and all(float(w["start"]).is_integer() for w in words) and max(w["end"] for w in words) > 600:
        for w in words:  # มิลลิวินาที → วินาที (auto-editor)
            w["start"] /= 1000.0
            w["end"] /= 1000.0
    return words


def align(chunks, words):
    """คืนรายการ (start, end) ของแต่ละท่อนในไฟล์เสียงเดิม ด้วยการเทียบตัวอักษรระหว่างสคริปต์กับคำที่ Whisper ได้ยิน"""
    s_chars, s_owner, s_range = [], [], []
    for i, c in enumerate(chunks):
        n = norm(c.text)
        s_range.append((len(s_chars), len(s_chars) + len(n)))
        s_chars.extend(n)
        s_owner.extend([i] * len(n))
    t_chars, t_time = [], []
    for w in words:
        n = norm(w["text"])
        if not n:
            continue
        span = max(0.0, w["end"] - w["start"])
        for k, ch in enumerate(n):
            t_chars.append(ch)
            t_time.append(w["start"] + span * k / len(n))
    if not s_chars or not t_chars:
        raise SystemExit("ไม่มีข้อความให้เทียบ (สคริปต์หรือไฟล์คำว่าง)")
    sm = difflib.SequenceMatcher(None, "".join(s_chars), "".join(t_chars), autojunk=False)
    hit = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            hit[blk.a + k] = blk.b + k
    first, last, first_s, last_s = {}, {}, {}, {}
    for si, ti in sorted(hit.items()):
        i = s_owner[si]
        if i not in first:
            first[i], first_s[i] = ti, si
        last[i], last_s[i] = ti, si
    n = len(chunks)
    starts, ends = [None] * n, [None] * n
    end_time = words[-1]["end"]

    def word_end_at(t):
        return max(t, next((w["end"] for w in words if w["start"] <= t <= w["end"] + 1e-6), t))

    for i in range(n):
        if i in first:
            starts[i] = t_time[first[i]]
            ends[i] = word_end_at(t_time[last[i]])
    # Whisper มักฟังคำไทยบางคำเพี้ยน (เช่น "โรงเรียน" → "Clear ven") ตัวอักษรตรงนั้นจึงจับคู่ไม่ได้
    # เสียงที่ไม่ได้จับคู่ระหว่างท่อน i กับ i+1 = หางที่หายไปของท่อน i และ/หรือหัวที่หายไปของท่อน i+1
    # แบ่งตามจำนวนตัวอักษรที่ยังไม่ได้จับคู่ ไม่งั้นซับท่อนนั้นจะหายเร็วกว่าเสียง หรือโผล่ช้ากว่าเสียง
    for i in range(n - 1):
        j = i + 1
        if i not in first or j not in first or first[j] - last[i] <= 1:
            continue
        tail = s_range[i][1] - 1 - last_s[i]
        head = first_s[j] - s_range[j][0]
        if tail + head == 0:
            continue
        gap = first[j] - last[i] - 1
        k = last[i] + 1 + round(gap * tail / (tail + head))  # ตัวอักษรแรกที่เป็นของท่อน j
        if tail:
            ends[i] = max(ends[i], word_end_at(t_time[k - 1]))
        if head:
            starts[j] = min(starts[j], t_time[k])
    # ท่อนที่ไม่เจอเลย: เกลี่ยตามความยาวระหว่างท่อนข้างเคียงที่เจอ
    known = [i for i in range(n) if starts[i] is not None]
    if not known:
        raise SystemExit("เทียบข้อความไม่ได้เลย ตรวจว่าไฟล์เสียงตรงกับสคริปต์")
    for i in range(n):
        if starts[i] is not None:
            continue
        prev = max([k for k in known if k < i], default=None)
        nxt = min([k for k in known if k > i], default=None)
        t0 = ends[prev] if prev is not None else 0.0
        t1 = starts[nxt] if nxt is not None else end_time
        span_ids = list(range((prev + 1) if prev is not None else 0, nxt if nxt is not None else n))
        tot = sum(max(1, bs.base_len(chunks[k].text)) for k in span_ids) or 1
        acc = sum(max(1, bs.base_len(chunks[k].text)) for k in span_ids if k < i)
        starts[i] = t0 + (t1 - t0) * acc / tot
        ends[i] = t0 + (t1 - t0) * (acc + max(1, bs.base_len(chunks[i].text))) / tot
    for i in range(n):  # เรียงเวลาให้เดินหน้าเสมอ
        if i and starts[i] < starts[i - 1]:
            starts[i] = starts[i - 1] + 0.05
        if ends[i] < starts[i] + 0.2:
            ends[i] = starts[i] + 0.2
        if i + 1 < n and starts[i + 1] is not None and ends[i] > starts[i + 1] and starts[i + 1] > starts[i]:
            ends[i] = max(starts[i] + 0.1, starts[i + 1] - 0.02)
    return list(zip(starts, ends))


def cmd_align(a):
    scenes, chunks = bs.parse_script(open(a.script, encoding="utf-8").read())
    spans = align(chunks, load_words(a.words))
    out = [{"start": round(s, 3), "end": round(e, 3), "text": c.plain} for (s, e), c in zip(spans, chunks)]
    _dump(out, a.out)
    return 0


# ---------------- audio i/o ----------------
def read_audio(path, sr):
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "v.wav")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", wav],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("อ่านไฟล์เสียงไม่ได้: " + r.stderr[-400:])
        with wave.open(wav, "rb") as w:
            data = array.array("h")
            data.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        data.byteswap()
    return data


def write_wav(path, data, sr):
    if sys.byteorder == "big":
        data = array.array("h", data)
        data.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def fade(seg, n):
    n = min(n, len(seg) // 2)
    for k in range(n):
        g = k / n
        seg[k] = int(seg[k] * g)
        seg[-1 - k] = int(seg[-1 - k] * g)
    return seg


def pace_part(chunks, idxs, spans, audio, sr, pscale, out, timings, last_part=True):
    """ต่อเสียงของชุดท่อน idxs (ดัชนีในสคริปต์ทั้งเรื่อง; spans = เวลาในไฟล์เสียงของชุดนี้) ลง out
    ตัดเฉพาะตรง // และ /// (ตรง / ปล่อยให้พูดต่อเนื่องเป็นธรรมชาติ) แล้วใส่ความเงียบตามสคริปต์ คืนจำนวนกลุ่ม"""
    dur = len(audio) / sr
    groups, cur = [], []
    for k, i in enumerate(idxs):
        cur.append(k)
        if len(chunks[i].pause) >= 2 or k == len(idxs) - 1:
            groups.append(cur)
            cur = []
    for gi, g in enumerate(groups):
        g0 = max(0.0, spans[g[0]][0] - 0.06)
        g1 = min(dur, spans[g[-1]][1] + 0.12)
        if gi + 1 < len(groups):  # อย่ากินเสียงของกลุ่มถัดไป
            g1 = min(g1, max(spans[groups[gi + 1][0]][0] - 0.03, spans[g[-1]][1]))
        seg = fade(audio[int(g0 * sr):int(g1 * sr)], int(0.012 * sr))
        offset = len(out) / sr
        for k in g:
            timings[idxs[k]] = {"start": round(offset + spans[k][0] - g0, 3), "end": round(offset + spans[k][1] - g0, 3)}
        out.extend(seg)
        if gi + 1 < len(groups) or not last_part:  # เปลี่ยนผู้พูดก็เว้นอย่างน้อย 0.25 วิ
            out.extend([0] * int(max(0.25, bs.PAUSE[chunks[idxs[g[-1]]].pause] * pscale) * sr))
    return len(groups)


def _finish(a, out, timings, sr, chunks, n_groups, src_desc, extra=None):
    out.extend([0] * int(a.tail * sr))
    write_wav(a.out, out, sr)
    _dump(timings, getattr(a, "timings", None))
    total = len(out) / sr
    print(f"✔ {a.out}  ยาว {total:.1f} วิ ({src_desc}) · {len(chunks)} ท่อน · {n_groups} ช่วงเว้นจังหวะ", file=sys.stderr)
    if a.project:
        p = json.load(open(a.project, encoding="utf-8"))
        clip = p["clips"][a.clip - 1]
        clip["voice"] = os.path.relpath(os.path.abspath(a.out), os.path.dirname(os.path.abspath(a.project)))
        clip["timings"] = timings
        clip.update(extra or {})
        json.dump(p, open(a.project, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"✔ เขียน voice + timings ลง {a.project} คลิป {a.clip}", file=sys.stderr)
    return 0


def cmd_assemble(a):
    sr = 44100
    scenes, chunks = bs.parse_script(open(a.script, encoding="utf-8").read())
    spans = align(chunks, load_words(a.words))
    audio = read_audio(a.voice, sr)
    pscale = bs.PAUSE_SCALE.get(a.speed, 1.0)
    out = array.array("h", [0] * int(a.lead * sr))
    timings = [None] * len(chunks)
    n = pace_part(chunks, list(range(len(chunks))), spans, audio, sr, pscale, out, timings)
    return _finish(a, out, timings, sr, chunks, n, f"เดิม {len(audio) / sr:.1f} วิ")


# ---------------- หลายเสียง (บทพูดตัวละคร @ชื่อ:) ----------------
NARRATOR_KEYS = ("ผู้บรรยาย", "narrator", "")


def voice_parts(chunks, cast=None, narrator="doc", speed="normal", clip_no=1):
    """แบ่งสคริปต์เป็นช่วงต่อเนื่องของผู้พูดคนเดียวกัน → คำขอ TTS ทีละช่วง (เสียง/คำสั่งอารมณ์ตาม cast)"""
    cast = cast or {}
    parts, a = [], 0
    for i in range(1, len(chunks) + 1):
        if i == len(chunks) or chunks[i].speaker != chunks[a].speaker:
            who = chunks[a].speaker or "ผู้บรรยาย"
            conf = cast.get(who) or (next((cast[k] for k in NARRATOR_KEYS if k in cast), {}) if not chunks[a].speaker else {})
            instr = conf.get("instruction") or INSTRUCTIONS.get(narrator, INSTRUCTIONS["doc"])
            n = len(parts) + 1
            parts.append({"part": n, "speaker": who, "chunks": [a, i - 1],
                          "target": f"media/clip{clip_no}-voice-p{n:02d}.wav",
                          "params": {"model": "qwen_audio_tts", "prompt": tts_text(chunks[a:i]), "language": "th",
                                     "instruction": instr[:128], "voice_type": "preset",
                                     "voice_id": conf.get("voice_id") or "<เลือกจาก list_voices>",
                                     "format": "wav", "sample_rate": 44100, "speech_rate": RATE.get(speed, 1.0)}})
            a = i
    missing = sorted({p["speaker"] for p in parts if p["speaker"] != "ผู้บรรยาย" and p["speaker"] not in cast})
    return parts, missing


def cmd_assemble_cast(a):
    """ต่อเสียงหลายไฟล์ (หนึ่งไฟล์ต่อช่วงผู้พูด) ตามลำดับสคริปต์ + เว้นจังหวะ + timings ของทุกท่อน"""
    sr = 44100
    scenes, chunks = bs.parse_script(open(a.script, encoding="utf-8").read())
    if a.parts:
        parts = json.load(open(a.parts, encoding="utf-8"))
        parts = parts.get("parts", parts)
        base = os.path.dirname(os.path.abspath(a.parts))
    else:
        p = json.load(open(a.project, encoding="utf-8"))
        parts = p["clips"][a.clip - 1].get("voiceParts") or []
        base = os.path.dirname(os.path.abspath(a.project))
    if not parts:
        raise SystemExit("ไม่มีรายการเสียงแต่ละช่วง (voiceParts) ใช้ prepare --cast ก่อน")
    pscale = bs.PAUSE_SCALE.get(a.speed, 1.0)
    out = array.array("h", [0] * int(a.lead * sr))
    timings = [None] * len(chunks)
    covered, groups = 0, 0
    for k, part in enumerate(parts):
        lo, hi = part["chunks"]
        if lo != covered or hi >= len(chunks):
            raise SystemExit(f"ช่วงที่ {k + 1} ({lo}-{hi}) ไม่ต่อเนื่องกับสคริปต์ปัจจุบัน สคริปต์ถูกแก้หลัง prepare? ให้ prepare --cast ใหม่")
        wav = part["target"] if os.path.isabs(part["target"]) else os.path.join(base, part["target"])
        words = part.get("words") or os.path.splitext(wav)[0] + "-words.json"
        words = words if os.path.isabs(words) else os.path.join(base, words)
        if not (os.path.exists(wav) and os.path.exists(words)):
            raise SystemExit(f"ช่วงที่ {k + 1} ({part.get('speaker')}): ไม่พบ {wav if not os.path.exists(wav) else words}")
        idxs = list(range(lo, hi + 1))
        spans = align([chunks[i] for i in idxs], load_words(words))
        groups += pace_part(chunks, idxs, spans, read_audio(wav, sr), sr, pscale, out, timings, k == len(parts) - 1)
        covered = hi + 1
    if covered != len(chunks):
        raise SystemExit(f"เสียงครอบคลุมแค่ {covered}/{len(chunks)} ท่อน")
    speakers = sorted({p.get("speaker", "") for p in parts})
    return _finish(a, out, timings, sr, chunks, groups, f"{len(parts)} ช่วง {len(speakers)} เสียง: {', '.join(speakers)}")


def _dump(obj, path):
    s = json.dumps(obj, ensure_ascii=False, indent=1)
    if path:
        open(path, "w", encoding="utf-8").write(s)
    else:
        print(s)


def main(argv=None):
    bs.utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="สคริปต์ → ข้อความและพารามิเตอร์ TTS")
    p.add_argument("script")
    p.add_argument("--narrator", default="doc", choices=list(INSTRUCTIONS))
    p.add_argument("--speed", default="normal", choices=list(RATE))
    p.add_argument("--voice-id")
    p.add_argument("--cast", help="project.json ที่มี cast (หลายเสียงตามบทบาท @ชื่อ:)")
    p.add_argument("--clip", type=int, default=1)
    p = sub.add_parser("align", help="เวลาแต่ละท่อนในไฟล์เสียงเดิม")
    p.add_argument("script")
    p.add_argument("--words", required=True)
    p.add_argument("--out")
    p = sub.add_parser("assemble", help="ใส่จังหวะเว้นตามสคริปต์ + timings ใหม่")
    p.add_argument("script")
    p.add_argument("--voice", required=True)
    p.add_argument("--words", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--timings")
    p.add_argument("--speed", default="normal", choices=list(RATE))
    p.add_argument("--lead", type=float, default=0.35, help="ความเงียบก่อนเริ่มพูด (วินาที)")
    p.add_argument("--tail", type=float, default=1.2, help="ความเงียบท้ายคลิป (วินาที)")
    p.add_argument("--project")
    p.add_argument("--clip", type=int, default=1)
    p = sub.add_parser("assemble-cast", help="ต่อเสียงหลายผู้พูดตามลำดับสคริปต์ + เว้นจังหวะ + timings")
    p.add_argument("script")
    p.add_argument("--parts", help="ผลของ prepare --cast (ไม่ใส่ = อ่าน voiceParts จาก --project)")
    p.add_argument("--out", required=True)
    p.add_argument("--timings")
    p.add_argument("--speed", default="normal", choices=list(RATE))
    p.add_argument("--lead", type=float, default=0.35)
    p.add_argument("--tail", type=float, default=1.2)
    p.add_argument("--project")
    p.add_argument("--clip", type=int, default=1)
    a = ap.parse_args(argv)
    if a.cmd == "assemble-cast" and not (a.parts or a.project):
        ap.error("assemble-cast ต้องใส่ --parts หรือ --project")
    return {"prepare": cmd_prepare, "align": cmd_align, "assemble": cmd_assemble,
            "assemble-cast": cmd_assemble_cast}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
