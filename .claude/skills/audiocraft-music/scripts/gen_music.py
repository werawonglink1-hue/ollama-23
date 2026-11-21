#!/usr/bin/env python3
"""สร้างเพลงประกอบ (MusicGen) และเสียงประกอบ (AudioGen) ด้วย AudioCraft ในเครื่องตัวเอง

⚠ สัญญาอนุญาต: โค้ด AudioCraft เป็น MIT แต่ "น้ำหนักโมเดล" MusicGen/AudioGen เป็น CC BY-NC 4.0
   = ใช้ได้เฉพาะงานที่ไม่หารายได้ (ฝึก ทดลอง ทำตัวอย่างให้ลูกค้าดู) ช่องที่หารายได้/โฆษณา ห้ามใช้เสียงจากโมเดลนี้
   ต้องใส่ --noncommercial-ok เพื่อยืนยันทุกครั้ง; งานเชิงพาณิชย์ใช้เพลงสังเคราะห์ใน render.py หรือ Higgsfield แทน

  music    เพลงยาวเท่าคลิป จากอารมณ์ (doc, musicbox, lofi, dream, playful) หรือ --prompt เอง
  sfx      เสียงประกอบสั้นจากคำบรรยาย (ลม ฝน กระดิ่ง วูบ ...)
  project  ทำเพลง + เสียงประกอบทุกชนิดที่สคริปต์ใช้ แล้วเขียน musicFile / sfxFiles ลง project.json
  prompts  แสดง prompt ที่จะใช้ (ไม่ต้องติดตั้ง AudioCraft)

ติดตั้ง (ครั้งเดียว ต้องมี PyTorch; มี GPU NVIDIA จะเร็วกว่ามาก):
  pip install torch torchaudio  &&  pip install audiocraft
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "social-video-studio", "scripts"))

MUSIC_PROMPTS = {  # ตรงกับค่า music ใน references/styles.md
    "doc": "cinematic documentary underscore, soft piano ostinato in A minor, gentle heartbeat pulse, warm low strings, inspiring build, no vocals",
    "musicbox": "gentle music box lullaby, warm soft pad, slow arpeggio, dreamy and tender, no vocals",
    "lofi": "warm lofi hip hop, mellow seventh chords, soft vinyl crackle, relaxed tempo, no vocals",
    "dream": "ambient dreamy night pad, distant soft bells, slow evolving textures, mysterious and calm, no vocals",
    "playful": "playful pizzicato strings and marimba, light bouncy rhythm, cheerful children story, no vocals",
}
SFX_PROMPTS = {
    "wind": "soft wind blowing through trees",
    "rain": "gentle rain falling on a tin roof",
    "chime": "small wind chime bells ringing softly",
    "whoosh": "quick soft whoosh transition",
    "paper": "paper sheet sliding fast, short paper swish",
    "pop": "small cartoon pop",
}


def sfx_kind(text):
    if "ลม" in text:
        return "wind"
    if "ฝน" in text:
        return "rain"
    if any(k in text for k in ("วูบ", "ปลิว", "หวือ")):
        return "whoosh"
    return "chime"


def _need_ack(a):
    if not a.noncommercial_ok:
        raise SystemExit("ต้องยืนยัน --noncommercial-ok: น้ำหนักโมเดล MusicGen/AudioGen เป็น CC BY-NC 4.0 ห้ามใช้กับงานหารายได้")


def _write(model, wav, out):
    from audiocraft.data.audio import audio_write
    stem = os.path.splitext(out)[0]
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    audio_write(stem, wav.cpu(), model.sample_rate, strategy="loudness", loudness_compressor=True)
    return stem + ".wav"


def gen_music(prompt, seconds, out, model_name):
    from audiocraft.models import MusicGen
    model = MusicGen.get_pretrained(model_name)
    chunk = min(30.0, seconds)  # MusicGen สร้างได้ทีละ ~30 วิ แล้วต่อด้วย extend (continuation)
    model.set_generation_params(duration=chunk)
    wav = model.generate([prompt])[0]
    while wav.shape[-1] / model.sample_rate < seconds - 0.5:
        tail = wav[..., -int(10 * model.sample_rate):]
        model.set_generation_params(duration=min(30.0, 10 + seconds - wav.shape[-1] / model.sample_rate))
        more = model.generate_continuation(tail[None], model.sample_rate, [prompt])[0]
        import torch
        wav = torch.cat([wav, more[..., tail.shape[-1]:]], dim=-1)
    return _write(model, wav[..., :int(seconds * model.sample_rate)], out)


def gen_sfx(prompt, seconds, out, model_name):
    from audiocraft.models import AudioGen
    model = AudioGen.get_pretrained(model_name)
    model.set_generation_params(duration=seconds)
    return _write(model, model.generate([prompt])[0], out)


def cmd_prompts(a):
    print(json.dumps({"music": MUSIC_PROMPTS, "sfx": SFX_PROMPTS}, ensure_ascii=False, indent=1))
    return 0


def cmd_music(a):
    _need_ack(a)
    print("✔", gen_music(a.prompt or MUSIC_PROMPTS[a.kind], a.seconds, a.out, a.model))
    return 0


def cmd_sfx(a):
    _need_ack(a)
    print("✔", gen_sfx(SFX_PROMPTS.get(a.kind, a.kind), a.seconds, a.out, a.sfx_model))
    return 0


def cmd_project(a):
    _need_ack(a)
    import build_subs as bs
    p = json.load(open(a.project, encoding="utf-8"))
    pdir = os.path.dirname(os.path.abspath(a.project))
    longest, kinds = 0.0, {"paper" if p.get("visualStyle") == "collage" else "whoosh"}
    for clip in p["clips"]:
        scenes, chunks, total = bs.build(clip["script"], p.get("speed", "normal"), clip.get("timings"))
        longest = max(longest, total)
        kinds |= {sfx_kind(x) for c in chunks for x in c.sfx}
    music_rel = os.path.join("audio", f"music-{p.get('music', 'doc')}.wav")
    gen_music(MUSIC_PROMPTS.get(p.get("music", "doc"), MUSIC_PROMPTS["doc"]), longest + 1, os.path.join(pdir, music_rel), a.model)
    p["musicFile"] = music_rel
    p.setdefault("sfxFiles", {})
    for k in sorted(kinds):
        rel = os.path.join("audio", f"sfx-{k}.wav")
        gen_sfx(SFX_PROMPTS[k], 3.0 if k in ("wind", "rain") else 1.0, os.path.join(pdir, rel), a.sfx_model)
        p["sfxFiles"][k] = rel
    p["audioLicense"] = "MusicGen/AudioGen weights CC BY-NC 4.0: non-commercial use only"
    json.dump(p, open(a.project, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✔ เพลง {music_rel} ({longest + 1:.0f} วิ) + เสียงประกอบ {sorted(kinds)} → {a.project}")
    return 0


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="facebook/musicgen-small", help="musicgen-small/medium/large หรือ musicgen-melody")
    ap.add_argument("--sfx-model", default="facebook/audiogen-medium")
    ap.add_argument("--noncommercial-ok", action="store_true", help="ยืนยันว่างานนี้ไม่หารายได้ (สัญญาอนุญาต CC BY-NC)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prompts")
    m = sub.add_parser("music")
    m.add_argument("--kind", default="doc", choices=list(MUSIC_PROMPTS))
    m.add_argument("--prompt")
    m.add_argument("--seconds", type=float, default=60)
    m.add_argument("--out", required=True)
    s = sub.add_parser("sfx")
    s.add_argument("kind", help="wind, rain, chime, whoosh, paper, pop หรือคำบรรยายภาษาอังกฤษ")
    s.add_argument("--seconds", type=float, default=2)
    s.add_argument("--out", required=True)
    pr = sub.add_parser("project")
    pr.add_argument("project")
    a = ap.parse_args(argv)
    try:
        return {"prompts": cmd_prompts, "music": cmd_music, "sfx": cmd_sfx, "project": cmd_project}[a.cmd](a)
    except ImportError:
        raise SystemExit("ยังไม่ได้ติดตั้ง AudioCraft: pip install torch torchaudio && pip install audiocraft")


if __name__ == "__main__":
    sys.exit(main())
