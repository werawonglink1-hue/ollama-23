#!/usr/bin/env python3
"""ambience.py — เสียงบรรยากาศต่อฉาก (สังเคราะห์เอง ไม่มีลิขสิทธิ์ ใช้เชิงพาณิชย์ได้) แล้วผูกกับคลิปใน project.json

ชั้นเสียงที่มี (ใส่ใน scenes[j].ambience เป็นลิสต์ หรือบรรทัดฉาก "| บรรยากาศ: ฝน, ลม, สถานี |"):
  ฝน/rain · ฝนพรำ/drizzle (ฝนบนกันสาด) · ลม/wind · เมือง/city (รถวิ่งไกล ๆ) · สถานี/station (เสียงหึ่งไฟฟ้า+ลม)
  รถไฟออก/train (รถไฟแล่นออก: ครางต่ำ + เสียงล้อกระทบราง ค่อย ๆ ไกลออกไป · train@1.2 = เริ่มหลังต้นฉาก 1.2 วิ)
  หม้อเดือด/boil · ช้อน/clink (ช้อนกระทบชามเป็นระยะ) · เงียบ/quiet (เสียงห้องเบา ๆ)
  ต่อท้าย :0.6 เพื่อปรับความดังเฉพาะชั้น เช่น "ฝน:0.5"
ฉากต่อกันเฟดข้ามกัน 0.6 วิ ตามช่วงเวลาจริงของฉาก (render.scene_windows) · เสียงเฉพาะจุด เช่นโทรศัพท์สั่น ใช้ {เสียง: ...} ในสคริปต์

ใช้:  python3 ambience.py project.json [--clip 1] [--out media/clip1-ambience.wav]
      แล้ว render.py จะผสม clips[i].ambience ให้เอง (ความดังรวม project.ambienceVolume ค่าเริ่มต้น 1.0)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import wave

import numpy as np

SR = 44100
ALIAS = {"ฝน": "rain", "ฝนพรำ": "drizzle", "ลม": "wind", "เมือง": "city", "สถานี": "station", "รถไฟออก": "train",
         "รถไฟ": "train", "หม้อเดือด": "boil", "ช้อน": "clink", "เงียบ": "quiet"}


def db(x):
    return 10 ** (x / 20)


def band_noise(n, lo, hi, rng, tilt=0.0):
    """noise กรองช่วงความถี่ด้วย FFT (ขอบนุ่ม) · tilt < 0 = เอียงไปทางเสียงต่ำ (pink/brown)"""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    gain = 1 / (1 + (lo / np.maximum(f, 1)) ** 4) / (1 + (f / hi) ** 4)
    if tilt:
        gain *= np.maximum(f, 20) ** (tilt / 2)
    y = np.fft.irfft(spec * gain, n)
    return (y / (np.sqrt(np.mean(y ** 2)) + 1e-12)).astype(np.float32)


def slow_env(n, rate, depth, rng):
    """ความดังขึ้นลงช้า ๆ (ลมกระโชก ฝนหนักเบา)"""
    k = max(4, int(n / SR * rate) + 4)
    pts = 1 - depth * rng.random(k)
    return np.interp(np.linspace(0, k - 1, n), np.arange(k), pts).astype(np.float32)


def burst(freqs, dur, decay, rng, amp=1.0):
    t = np.arange(int(dur * SR)) / SR
    y = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / (decay * (1 + 0.3 * i)))
            for i, f in enumerate(freqs))
    return (amp * y / len(freqs)).astype(np.float32)


def add(buf, snd, at):
    i = int(at * SR)
    if i >= len(buf) or i + len(snd) <= 0:
        return
    s0 = max(0, -i)
    e = min(len(snd), len(buf) - i)
    buf[i + s0:i + e] += snd[s0:e]


def layer(kind, n, rng, opt=0.0):
    if kind == "rain":
        y = band_noise(n, 700, 9000, rng, -0.5) * slow_env(n, 0.3, 0.25, rng) * db(-33)
        for t in rng.uniform(0, n / SR, int(n / SR * 30)):
            add(y, burst([rng.uniform(2500, 6000)], 0.02, 0.004, rng, db(-38)), t)
        return y
    if kind == "drizzle":  # ฝนพรำบนกันสาด: ซ่าเบา + หยดน้ำกระทบผ้าใบเป็นระยะ
        y = band_noise(n, 900, 8000, rng, -0.5) * slow_env(n, 0.25, 0.3, rng) * db(-38)
        for t in rng.uniform(0, n / SR, int(n / SR * 9)):
            add(y, burst([rng.uniform(700, 1600), rng.uniform(1800, 2600)], 0.06, 0.012, rng, db(-33)), t)
        return y
    if kind == "wind":
        return band_noise(n, 120, 1100, rng, -1.0) * slow_env(n, 0.25, 0.75, rng) * db(-36)
    if kind == "city":
        return (band_noise(n, 30, 220, rng, -1.5) * db(-35) + band_noise(n, 2000, 7000, rng) * db(-52)) * slow_env(n, 0.1, 0.3, rng)
    if kind == "station":
        t = np.arange(n) / SR
        hum = (np.sin(2 * np.pi * 50 * t) + 0.5 * np.sin(2 * np.pi * 100 * t) + 0.25 * np.sin(2 * np.pi * 150 * t)) * db(-46)
        return (hum + band_noise(n, 80, 600, rng, -1.0) * db(-42)).astype(np.float32)
    if kind == "quiet":
        return band_noise(n, 40, 400, rng, -1.0) * db(-50)
    if kind == "boil":  # หม้อเดือด: ฟองแตกเป็นจังหวะ + เสียงไฟต่ำ ๆ
        y = band_noise(n, 60, 500, rng, -1.0) * db(-46)
        for t in rng.uniform(0, n / SR, int(n / SR * 7)):
            f0 = rng.uniform(160, 380)
            tt = np.arange(int(0.07 * SR)) / SR
            blub = np.sin(2 * np.pi * (f0 * tt + 900 * tt * tt)) * np.exp(-tt / 0.02) * db(-34)
            add(y, blub.astype(np.float32), t)
        return y
    if kind == "clink":  # ช้อนกระทบชามเป็นระยะ (ความถี่ไม่ลงตัวแบบโลหะ/กระเบื้อง)
        y = np.zeros(n, np.float32)
        t = rng.uniform(0.8, 2.0)
        while t < n / SR:
            add(y, burst([2093, 3410, 5180, 7020], 0.5, 0.09, rng, db(-28)), t)
            t += rng.uniform(3.0, 6.0)
        return y
    if kind == "train":  # รถไฟแล่นออก: ครางต่ำ + ล้อกระทบราง ถี่ขึ้นแต่เบาลงเมื่อไกลออกไป
        y = np.zeros(n, np.float32)
        start, dur = opt, 8.5
        m = int(dur * SR)
        tt = np.arange(m) / SR
        env = np.minimum(1.0, tt / 0.8) * np.exp(-tt / 3.2)
        low = band_noise(m, 35, 180, rng, -1.5) * db(-24)
        mid = band_noise(m, 180, 1400, rng, -0.5) * db(-32) * np.exp(-tt / 1.6)  # เสียงสูงหายก่อน = ไกลออกไป
        add(y, ((low + mid) * env).astype(np.float32), start)
        t, gap = 0.4, 0.42
        while t < dur - 0.5:
            a = db(-27) * np.exp(-t / 2.6)
            for k in (0.0, 0.11):  # กึก-กัก
                click = band_noise(int(0.05 * SR), 400, 3500, rng) * np.exp(-np.arange(int(0.05 * SR)) / SR / 0.012) * a
                add(y, click.astype(np.float32), start + t + k)
            t += gap
            gap = max(0.22, gap * 0.93)
        return y
    raise ValueError(kind)


def parse_layers(items):
    out = []
    for it in items:
        it = str(it).strip()
        if not it:
            continue
        name, _, vol = it.partition(":")
        name, _, at = name.partition("@")
        kind = ALIAS.get(name.strip(), name.strip())
        out.append((kind, float(vol) if vol else 1.0, float(at) if at else 0.0))
    return out


def build(project, ci=1):
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import build_subs as bs
    import render
    clip = project["clips"][ci - 1]
    scenes, _, total = bs.build(clip["script"], project.get("speed", "normal"), clip.get("timings"))
    _, _, starts, durs = render.scene_windows(scenes, project.get("visualStyle", "collage"), int(project.get("fps") or 30))
    metas = clip.get("scenes") or []
    n = int((total + 1.0) * SR)
    mix = np.zeros(n, np.float32)
    fade = 0.6
    for j, sc in enumerate(scenes):
        m = metas[j] if j < len(metas) and isinstance(metas[j], dict) else {}
        items = m.get("ambience") or [x for x in str((sc.meta or {}).get("ambience", "")).split(",")]
        layers = parse_layers(items)
        if not layers:
            continue
        t0, t1 = starts[j], starts[j] + durs[j]
        a, b = int(max(0, t0 - fade / 2) * SR), int(min(n / SR, t1 + fade / 2) * SR)
        seg_n = b - a
        if seg_n <= 0:
            continue
        rng = np.random.default_rng(1000 + j)
        seg = np.zeros(seg_n, np.float32)
        for kind, vol, at in layers:
            seg += layer(kind, seg_n, rng, opt=at + (t0 - a / SR)) * vol
        ramp = np.ones(seg_n, np.float32)
        k = int(fade * SR)
        if k and seg_n > 2 * k:
            ramp[:k] = np.linspace(0, 1, k)
            ramp[-k:] = np.linspace(1, 0, k)
        mix[a:b] += seg * ramp
    return np.clip(mix, -1, 1)


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--clip", type=int, default=1)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    p = json.load(open(a.project, encoding="utf-8"))
    pdir = os.path.dirname(os.path.abspath(a.project))
    out_rel = a.out or f"media/clip{a.clip}-ambience.wav"
    out = out_rel if os.path.isabs(out_rel) else os.path.join(pdir, out_rel)
    mix = build(p, a.clip)
    if not np.any(mix):
        print("ไม่มีฉากที่กำหนดบรรยากาศ (scenes[j].ambience หรือ | บรรยากาศ: ... | ในบรรทัดฉาก)")
        return 0
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with wave.open(out, "wb") as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(SR)
        wv.writeframes((mix * 32000).astype("<i2").tobytes())
    p["clips"][a.clip - 1]["ambience"] = os.path.relpath(out, pdir) if not os.path.isabs(out_rel) else out
    json.dump(p, open(a.project, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    peak = 20 * np.log10(np.max(np.abs(mix)) + 1e-9)
    rms = 20 * np.log10(np.sqrt(np.mean(mix ** 2)) + 1e-9)
    print(f"✔ {out_rel}  {len(mix) / SR:.1f} วิ · RMS {rms:.1f} dBFS · peak {peak:.1f} dBFS → clips[{a.clip - 1}].ambience")
    return 0


if __name__ == "__main__":
    sys.exit(main())
