---
name: audiocraft-music
description: สร้างเพลงประกอบ (MusicGen) และเสียงประกอบ (AudioGen ลม ฝน กระดิ่ง วูบ กระดาษ) ด้วย AudioCraft บนเครื่องผู้ใช้ฟรี แล้วใส่ลง project.json ให้ render.py ใช้ — ใช้ได้เฉพาะงานที่ไม่หารายได้ เพราะน้ำหนักโมเดลเป็น CC BY-NC 4.0. ใช้เมื่อผู้ใช้ขอ "เพลงประกอบ AI ฟรี", "เสียงประกอบสมจริง", "MusicGen/AudioGen" สำหรับงานทดลอง ตัวอย่าง หรือช่องที่ไม่มีรายได้.
---

# AudioCraft Music (เพลง + เสียงประกอบ บนเครื่องตัวเอง)

สคริปต์: `scripts/gen_music.py`

## ⚠ สัญญาอนุญาต อ่านก่อนใช้ทุกครั้ง

- โค้ด AudioCraft เป็น MIT แต่ **น้ำหนักโมเดล MusicGen/AudioGen เป็น CC BY-NC 4.0 = ห้ามใช้เชิงพาณิชย์**
- ช่องที่เปิดสร้างรายได้ ติดโฆษณา รับงานลูกค้า หรือขายของ **ห้ามใช้เสียงจากสกิลนี้**
- สคริปต์บังคับใส่ `--noncommercial-ok` และเขียน `audioLicense` ลง project.json ไว้ให้ Brand Guardian ตรวจก่อนเผยแพร่
- งานเชิงพาณิชย์ใช้แทน: เพลงสังเคราะห์ใน `render.py` (ของเราเอง ใช้ได้ทุกกรณี), เพลงจาก `higgsfield-studio` (ElevenLabs, มีค่าเครดิต, ตรวจเงื่อนไขแผนของผู้ใช้), หรือคลังเพลงปลอดค่าลิขสิทธิ์ที่ระบุว่าใช้เชิงพาณิชย์ได้

## ติดตั้ง (ครั้งเดียว)

```bash
pip install torch torchaudio      # มี GPU NVIDIA ให้ติดตั้งรุ่น CUDA ตามหน้า pytorch.org
pip install audiocraft
```

ไม่มี GPU ก็ใช้ได้แต่ช้ามาก (เพลง 60 วิ อาจใช้หลายสิบนาที) ใช้ `--model facebook/musicgen-small` บน CPU

## ใช้งาน

```bash
S=.claude/skills/audiocraft-music/scripts/gen_music.py
python3 $S prompts                                            # ดู prompt ของแต่ละอารมณ์ (ไม่ต้องติดตั้ง AudioCraft)
python3 $S --noncommercial-ok music --kind doc --seconds 62 --out work/<โปรเจกต์>/audio/music-doc.wav
python3 $S --noncommercial-ok sfx wind --seconds 3 --out work/<โปรเจกต์>/audio/sfx-wind.wav
python3 $S --noncommercial-ok project work/<โปรเจกต์>/project.json   # เพลงยาวเท่าคลิปที่ยาวที่สุด + เสียงประกอบทุกชนิดที่สคริปต์ใช้
```

- อารมณ์เพลง (`--kind`) ตรงกับดรอปดาวน์เพลงของเว็บ: `doc` สารคดีเปียโน+ชีพจร, `musicbox`, `lofi`, `dream`, `playful` หรือเขียน `--prompt` เอง (ภาษาอังกฤษ ใส่ `no vocals`)
- `project` เขียน `musicFile` และ `sfxFiles` (`wind`, `rain`, `chime`, `whoosh`, `paper`, `pop`) ลง project.json → `render.py` ใช้ไฟล์เหล่านี้แทนเสียงสังเคราะห์
- MusicGen สร้างได้ทีละ ~30 วิ สคริปต์ต่อเพลงยาวด้วย continuation ให้เอง
- ความดังเพลงในคลิป `render.py` ลดให้อยู่ใต้เสียงพากย์อัตโนมัติ ฟังซ้ำทุกครั้งว่าไม่กลบเสียงพูด
