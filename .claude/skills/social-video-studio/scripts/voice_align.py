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
    s_chars, s_owner = [], []
    for i, c in enumerate(chunks):
        n = norm(c.text)
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
    first, last = {}, {}
    for si, ti in sorted(hit.items()):
        i = s_owner[si]
        first.setdefault(i, ti)
        last[i] = ti
    n = len(chunks)
    starts, ends = [None] * n, [None] * n
    end_time = words[-1]["end"]
    for i in range(n):
        if i in first:
            starts[i] = t_time[first[i]]
            li = last[i]
            nxt_word_end = next((w["end"] for w in words if w["start"] <= t_time[li] <= w["end"] + 1e-6), t_time[li])
            ends[i] = max(nxt_word_end, t_time[li])
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


def cmd_assemble(a):
    sr = 44100
    scenes, chunks = bs.parse_script(open(a.script, encoding="utf-8").read())
    spans = align(chunks, load_words(a.words))
    audio = read_audio(a.voice, sr)
    dur = len(audio) / sr
    pscale = bs.PAUSE_SCALE.get(a.speed, 1.0)
    # กลุ่มเสียงต่อเนื่อง: ตัดเฉพาะตรง // และ /// (ตรง / ปล่อยให้พูดต่อเนื่องเป็นธรรมชาติ)
    groups, cur = [], []
    for i, c in enumerate(chunks):
        cur.append(i)
        if len(c.pause) >= 2 or i == len(chunks) - 1:
            groups.append(cur)
            cur = []
    out = array.array("h", [0] * int(a.lead * sr))
    timings = [None] * len(chunks)
    for gi, g in enumerate(groups):
        g0 = max(0.0, spans[g[0]][0] - 0.06)
        g1 = min(dur, spans[g[-1]][1] + 0.12)
        if gi + 1 < len(groups):  # อย่ากินเสียงของกลุ่มถัดไป
            g1 = min(g1, max(spans[groups[gi + 1][0]][0] - 0.03, spans[g[-1]][1]))
        seg = fade(audio[int(g0 * sr):int(g1 * sr)], int(0.012 * sr))
        offset = len(out) / sr
        for i in g:
            timings[i] = {"start": round(offset + spans[i][0] - g0, 3), "end": round(offset + spans[i][1] - g0, 3)}
        out.extend(seg)
        if gi + 1 < len(groups):
            mark = chunks[g[-1]].pause
            out.extend([0] * int(max(0.25, bs.PAUSE[mark] * pscale) * sr))
    out.extend([0] * int(a.tail * sr))
    write_wav(a.out, out, sr)
    _dump(timings, a.timings)
    total = len(out) / sr
    print(f"✔ {a.out}  ยาว {total:.1f} วิ (เดิม {dur:.1f} วิ) · {len(chunks)} ท่อน · {len(groups)} ช่วงเว้นจังหวะ", file=sys.stderr)
    if a.project:
        p = json.load(open(a.project, encoding="utf-8"))
        clip = p["clips"][a.clip - 1]
        clip["voice"] = os.path.relpath(os.path.abspath(a.out), os.path.dirname(os.path.abspath(a.project)))
        clip["timings"] = timings
        json.dump(p, open(a.project, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"✔ เขียน voice + timings ลง {a.project} คลิป {a.clip}", file=sys.stderr)
    return 0


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
    a = ap.parse_args(argv)
    return {"prepare": cmd_prepare, "align": cmd_align, "assemble": cmd_assemble}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
