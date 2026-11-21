#!/usr/bin/env python3
"""ไฟล์เสียงพากย์ → เวลาแต่ละคำ (words.json) ด้วย faster-whisper สำหรับ voice_align.py

ติดตั้งครั้งเดียว:  pip install faster-whisper   (มี GPU NVIDIA จะเร็วกว่า ใส่ --device cuda)

  python3 whisper_words.py media/clip1-voice.wav --out media/clip1-words.json
  python3 whisper_words.py voice.wav --out words.json --model large-v3 --device cuda --compute-type float16

ใช้โมเดลหลายภาษา (medium, large-v3, large-v3-turbo) เท่านั้น ห้ามใช้รุ่น .en กับเสียงไทย
Whisper ฟังคำไทยเพี้ยนได้บ้าง (เช่น "โรงเรียน" → "Clear ven") ไม่เป็นไร voice_align.py เทียบตัวอักษรกับสคริปต์และเกลี่ยส่วนที่เพี้ยนให้
อย่าส่งสคริปต์เป็น initial prompt ให้ Whisper: ทดสอบแล้ว Whisper ข้ามคำพูด 13 วินาทีแรกไปทั้งหมด (ถือว่าถอดแล้ว) ทำให้ซับต้นคลิปคลาด
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="medium", help="medium (ค่าเริ่มต้น), large-v3, large-v3-turbo")
    ap.add_argument("--lang", default="th")
    ap.add_argument("--device", default="auto", help="auto, cpu, cuda")
    ap.add_argument("--compute-type", default="int8", help="int8 (เร็ว ใช้ได้ทั้ง CPU/GPU), float16 (GPU)")
    a = ap.parse_args(argv)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("ยังไม่ได้ติดตั้ง faster-whisper: pip install faster-whisper")
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type)
    segments, info = model.transcribe(a.audio, language=a.lang, word_timestamps=True)
    words = [{"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3)}
             for seg in segments for w in (seg.words or [])]
    if not words:
        raise SystemExit("Whisper ไม่ได้ยินคำพูดในไฟล์นี้ ตรวจว่าไฟล์มีเสียงพากย์")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(words, fh, ensure_ascii=False)
    print(f"✔ {a.out}  {len(words)} คำ · ยาว {words[-1]['end']:.1f} วิ · ภาษา {info.language}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
