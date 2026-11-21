---
name: auto-editor
description: ตัดต่ออัตโนมัติด้วย auto-editor (CLI ฟรี โอเพนซอร์ส) สำหรับงานคลิปของ social-video-studio — ตัดช่วงเงียบยาว/คำผิดจากเสียงพากย์ที่ผู้ใช้อัดเอง โดยไม่กินจังหวะเว้นวรรคที่ตั้งใจ, ถอดเสียงไทยเป็นเวลาแต่ละคำ (whisper) ให้ voice_align.py ทำซับตรงเสียง, ตัดคลิปคนพูดหน้ากล้อง, ปรับความดังมาตรฐาน และส่งงานเข้า DaVinci Resolve / Premiere / Final Cut. ใช้เมื่อผู้ใช้ขอ "ตัดช่วงเงียบ", "ตัดเสียงพากย์ที่อัดเอง", "ถอดเสียงเป็นซับ", "ตัดคลิปพูดหน้ากล้อง", "ส่งไฟล์ไปตัดต่อต่อใน Resolve/Premiere".
---

# auto-editor สำหรับสตูดิโอคลิป

auto-editor วิเคราะห์ไฟล์เป็นช่วง ๆ ว่า "มีเสียง/มีการเคลื่อนไหว" หรือไม่ แล้วตัดช่วงที่ไม่มีทิ้ง (ค่าเริ่มต้น) หรือเร่ง/ซูม/ทำอย่างอื่นตามสั่ง
สัญญาอนุญาต: Unlicense (สาธารณสมบัติ) ใช้เชิงพาณิชย์ได้ · คู่มือต้นฉบับ 5 ชุดอยู่ใน `references/upstream-*.md`

ติดตั้ง: `pip install auto-editor` (หรือดาวน์โหลดไฟล์โปรแกรมจากหน้า Releases ของ auto-editor บน GitHub) แล้วลอง `auto-editor --help`
ใช้ `--preview` ดูว่าจะตัดอะไรก่อนเรนเดอร์จริงทุกครั้ง

## งานที่ 1: ทำความสะอาดเสียงพากย์ที่ผู้ใช้อัดเอง (ไม่กินจังหวะเว้นวรรค)

สคริปต์ของเราตั้งใจเว้นจังหวะ (`//` ≈ 0.6–0.8 วิ, `///` ≈ 1–1.4 วิ) ห้ามตัดช่วงเงียบแบบค่าเริ่มต้น ให้ตัดเฉพาะช่วงเงียบยาวผิดปกติ (อัดพลาด หายใจยาว) เท่านั้น:

```bash
# ตัดเฉพาะช่วงเงียบที่ยาวเกิน 1.6 วิ เหลือขอบ 0.3 วิ ก่อน/หลังเสียง
auto-editor raw_voice.wav --edit audio:-38dB --smooth 1.6s,0.2s --margin 0.3s,0.3s -o media/clip1-voice.wav
auto-editor raw_voice.wav --edit audio:-38dB --smooth 1.6s,0.2s --margin 0.3s,0.3s --preview   # ดูก่อน
```

แล้วทำเวลาแต่ละคำ + เว้นจังหวะใหม่ให้ตรงสคริปต์ด้วย `voice_align.py assemble` (งานที่ 2) ความยาวช่วงเว้นจะถูกตั้งใหม่ตามเครื่องหมายในสคริปต์เสมอ

อัดเสียงด้วยไมค์ผ่าน auto-editor ได้เลย (กด Ctrl-C เพื่อหยุด): `auto-editor :mic --edit audio:-38dB --smooth 1.6s,0.2s -o take1.wav`

## งานที่ 2: เวลาแต่ละคำของเสียงไทย → ซับตรงเสียง

```bash
# ใช้โมเดลหลายภาษา (ggml-medium.bin, ggml-large-v3.bin, ggml-large-v3-turbo.bin) ห้ามใช้รุ่น .en
auto-editor whisper media/clip1-voice.wav ggml-large-v3-turbo.bin -l th --format json --split-words -o media/clip1-words.json
python3 .claude/skills/social-video-studio/scripts/voice_align.py assemble script.txt --voice media/clip1-voice.wav \
        --words media/clip1-words.json --out media/clip1-voice-paced.wav --speed normal --project project.json --clip 1
```

ผลของ auto-editor เป็น JSON ทีละบรรทัด หน่วยมิลลิวินาที `voice_align.py` อ่านได้เองและแปลงเป็นวินาที
ถ้าไม่มี auto-editor ใช้ `social-video-studio/scripts/whisper_words.py` (faster-whisper) แทนได้ ผลเหมือนกัน

## งานที่ 3: คลิปคนพูดหน้ากล้อง / ฟุตเทจที่ผู้ใช้ถ่ายเอง

```bash
auto-editor talk.mp4 --margin 0.2s,0.4s -o media/talk-cut.mp4                  # ตัดช่วงเงียบ
auto-editor talk.mp4 --edit "(or audio:0.03 motion:0.06)" -o media/broll.mp4   # เก็บช่วงที่มีเสียงหรือมีการเคลื่อนไหว
auto-editor talk.mp4 --edit audio:-30dB --edit:2 audio:-12dB --when:2 speed:1.15   # เร่งช่วงที่พูดดังเล็กน้อย
```

ไฟล์ที่ตัดแล้วใส่เป็นสื่อของฉากใน project.json ได้ (`render.py` รับ .mp4 .mov .webm .mkv .m4v) แล้วใช้เสียงพากย์เป็นเสียงหลักตามปกติ
ถ้าคลิปผู้ใช้เป็นแนวนอนแต่ต้องการแนวตั้ง ให้ `render.py` วางในการ์ด/ครอปให้ หรือใช้ `reframe` ของ Higgsfield (มีค่าเครดิต)

## งานที่ 4: ความดังมาตรฐานก่อนโพสต์

```bash
auto-editor out/clip.mp4 --edit 1 -anorm ebu -o out/clip-loud.mp4   # --edit 1 = ไม่ตัดอะไร แค่ปรับความดังแบบ EBU R128
```

ตรวจความดังด้วย ffmpeg `ebur128` (Video Optimization Specialist) ก่อนและหลัง

## งานที่ 5: ส่งต่อให้โปรแกรมตัดต่อ

```bash
auto-editor talk.mp4 --export resolve        # DaVinci Resolve (.fcpxml)
auto-editor talk.mp4 --export premiere       # Premiere Pro (.xml)
auto-editor talk.mp4 --export final-cut-pro  # Final Cut Pro
auto-editor talk.mp4 --export clip-sequence  # แยกเป็นไฟล์ละช่วงที่เก็บไว้
```

ใช้เมื่อผู้ใช้อยากแต่งต่อเองในโปรแกรมตัดต่อ (เอฟเฟกต์ ทรานซิชัน ดู `references/upstream-auto-editor-effects.md` และ `upstream-auto-editor-transitions.md`)

## ข้อควรระวัง

- เส้นทางไฟล์บน Windows ที่มีภาษาไทย/ช่องว่างให้ใส่เครื่องหมายคำพูดเสมอ เช่น `"D:\คลิป\เสียง 1.wav"`
- งานที่ 1 ห้ามใช้ `--margin` น้อยกว่า 0.25 วิ กับเสียงพากย์ (หางเสียงคำไทยจะขาด)
- auto-editor ไม่แก้สคริปต์ ไม่สร้างซับภาษาไทยที่จัดคำเอง ซับของคลิปให้สร้างจากสคริปต์ด้วย `build_subs.py` / `render.py` เสมอ ใช้ whisper เพื่อ "เวลา" เท่านั้น
