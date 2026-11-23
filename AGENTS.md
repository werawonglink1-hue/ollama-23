# AGENTS.md — คู่มือสำหรับ AI coding agent (Codex, Claude Code และ agent อื่น)

ไฟล์นี้คือคำสั่งประจำ repo: agent ทุกตัวอ่านก่อนเริ่มงาน แล้วหยิบงานจาก **`TASKS.md` ตามลำดับ** (บนสุดที่ยังไม่มีเจ้าของ)

## โปรเจกต์นี้คืออะไร

สตูดิโอผลิตคลิปโซเชียลภาษาไทย (TikTok / Reels / Shorts / YouTube) แบบมีทีม agent: ผู้ใช้สั่ง "แนวคลิป + จำนวน"
แล้วระบบทำต่อเอง — หากระแส → สคริปต์มีจังหวะเว้น → ตัวละคร + ภาพต่อช็อต → วิดีโอจากภาพ → เสียงพากย์ → ซับไทยตรงเสียง
→ ตัดต่อ 9:16/16:9 → QC → ส่งเข้าระบบอนุมัติ (มนุษย์อนุมัติเท่านั้น) → จัดเก็บ `D:\VIDEO_WORKFLOW`

| ที่อยู่ | คืออะไร |
|---|---|
| `.claude/skills/social-video-studio/` | แกนกลาง: `build_subs.py` (แยกสคริปต์/ซับ), `render.py` (ffmpeg), `voice_align.py` + `whisper_words.py` (ซับตรงเสียง), `templates/` (ตัวอย่างโปรเจกต์), `references/` (กติกาสคริปต์ สไตล์) |
| `.claude/skills/cinematic-image-to-video/` | วิดีโอจากภาพ: มาตรฐาน prompt (`i2v_prompt.py`), ตรวจคลิป AI (`check_i2v.py`), **ทางฟรี** `i2v_free.py` (engine `local` = `animate_still.py` 2.5D, engine `comfyui` = `comfy_i2v.py` + Wan 2.2) |
| `.claude/skills/higgsfield-studio/` | แผนคำขอ Higgsfield (เสียง ภาพ วิดีโอ เพลง) `hf_plan.py` plan/fetch — **ใช้เครดิตจริง** |
| `.claude/skills/content-production/` | ฝ่ายผลิตอัตโนมัติ: `board.py` (ใบงาน), `trends.py` (กระแส), `qc_check.py` (QC + ส่งกลับแผนก) |
| `.claude/skills/video-document-control/` | ระบบเอกสาร/อนุมัติ `doc_control.py` (ทะเบียน sha256 ประวัติ archive) |
| `.claude/skills/*` อื่น ๆ | comfyui-scenes, web-image-research, auto-editor, audiocraft-music, agent-reach, trading-agent-architecture (คนละโปรเจกต์) |
| `.claude/agents/` | บทบาท agent ของทีม (Claude Code subagents) |
| `video-studio-web/` | `index.html` หน้าสำนักงาน (แผนก ใบงาน ห้องอนุมัติ) · `editor.html` เว็บตัดต่อในเบราว์เซอร์ (ต้องให้ผลตรงกับ render.py) |
| `production.config.json` | ค่ากลาง: งบเครดิต QC แนวคลิป motion ฯลฯ |

## ติดตั้งและทดสอบ

```bash
sudo apt-get install -y ffmpeg            # จำเป็น (ฟอนต์ Kanit แนบมากับ skill แล้ว)
pip install numpy pillow pytest           # opencv-python ไม่บังคับ (ทำให้ animate_still เร็วขึ้น 3–4 เท่า)
python3 -m py_compile .claude/skills/*/scripts/*.py
python3 .claude/skills/social-video-studio/scripts/render.py .claude/skills/social-video-studio/templates/project.example.json --out /tmp/out
python3 .claude/skills/cinematic-image-to-video/scripts/animate_still.py <ภาพ.png> /tmp/a.mp4 --seconds 2 --size 540x960 --fx '{"twinkle":1,"particles":20}'
python3 .claude/skills/cinematic-image-to-video/scripts/check_i2v.py --video /tmp/a.mp4 --format 9x16
```

ยังไม่มีชุดทดสอบอัตโนมัติ — เป็นงานแรกใน `TASKS.md` (T02) หลังมีแล้วให้รัน `pytest -q` ก่อนส่งงานทุกครั้ง

## กติกาที่ห้ามละเมิด

1. **ห้ามใช้เครดิต/บริการที่เสียเงิน** (Higgsfield generate_*, API ภายนอกที่คิดเงิน) โดยที่ผู้ใช้ยังไม่อนุมัติพร้อมตัวเลข และห้ามสร้างซ้ำเองเมื่องานล้มเหลว
2. **มนุษย์เท่านั้นที่อนุมัติคลิป** — AI ห้ามบันทึกผลอนุมัติแทน (doc_control.py ปฏิเสธชื่อผู้อนุมัติที่เป็น AI อยู่แล้ว ห้ามแก้ให้หลวม)
3. ห้ามโพสต์ลง TikTok/โซเชียลโดยไม่มีคำอนุมัติของผู้ใช้
4. ห้ามรายงานว่าจัดเก็บสำเร็จถ้าเข้าถึง `D:\` ไม่ได้ (`doc_control.py` ปฏิเสธ path `D:\` บนเครื่องที่ไม่ใช่ Windows — คงพฤติกรรมนี้ไว้)
5. ตัวละครต้องออกแบบเองทั้งหมด ห้ามเลียนแบบคนจริงหรือตัวละคร/ช่องที่มีลิขสิทธิ์ · ภาพ/วิดีโอ AI ต้องติดป้ายเครดิตเสมอ
6. ห้ามรวมหรือรีแบรนด์โค้ด "Agents Office" (สัญญาอนุญาต PolyForm Noncommercial) — หน้า office ของเราเขียนใหม่เองทั้งหมด
7. ห้ามใส่ข้อมูลส่วนตัวของผู้ใช้ (อีเมล ชื่อ ลิงก์สื่อในบัญชี) ลงไฟล์ใน repo หรือส่งให้บริการภายนอก — repo นี้เป็นสาธารณะ
8. ห้าม commit ความลับ (API key, token, `.env`)

## แนวทางเขียนโค้ด

- ข้อความที่ผู้ใช้เห็น (print, คำอธิบาย argparse, เอกสาร) เป็น **ภาษาไทย** · โค้ด/ชื่อตัวแปรเป็นอังกฤษ
- สคริปต์ทุกตัวรันเดี่ยวได้ (`argparse`, `python3 script.py --help`) ไม่พึ่ง package หนักเพิ่มถ้าไม่จำเป็น
- `editor.html` กับ `build_subs.py`/`render.py` ต้องให้ผลตรงกัน (คีย์บรรทัดฉาก จังหวะเว้น ซับ) — แก้ฝั่งหนึ่งต้องแก้อีกฝั่ง
- แก้ให้น้อยที่สุดที่ทำให้งานสำเร็จ ไม่จัดรูปแบบไฟล์ใหม่ทั้งไฟล์ ไม่เปลี่ยนชื่อฟังก์ชันที่ไฟล์อื่นเรียกใช้
- ทดสอบกับโปรเจกต์ชั่วคราวในโฟลเดอร์ tmp เสมอ ห้ามเขียนทับ `templates/` หรือ `production.config.json` โดยไม่จำเป็น

## ทำงานร่วมกัน (Codex ↔ Claude Code)

- branch หลักของงานตอนนี้คือ `claude/beautiful-goldberg-a1jt5q` (repo ยังไม่มี `main`)
- งานหนึ่งชิ้น = หนึ่ง branch (`codex/T02-tests`, `claude/T03-...`) = หนึ่ง PR เข้าหา branch หลัก
- เริ่มงาน: เปลี่ยนสถานะใน `TASKS.md` เป็น `กำลังทำ (ชื่อ agent)` · เสร็จ: `เสร็จ` + สรุปผลทดสอบใน PR
- งานที่ต้องใช้เครื่อง/บัญชีของผู้ใช้ (GPU, Drive D:, Higgsfield, โพสต์โซเชียล) agent ทำแทนไม่ได้ — ระบุไว้ใน TASKS.md ว่า "ผู้ใช้"
