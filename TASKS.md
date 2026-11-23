# TASKS.md — คิวงานเรียงลำดับ (สำหรับ Codex และ Claude Code)

หยิบงาน **บนสุดที่ยังว่าง** ที่ตัวเองทำได้ · ทำทีละงาน · เปลี่ยนสถานะในไฟล์นี้ใน PR เดียวกับงาน
สถานะ: `ว่าง` · `กำลังทำ (agent)` · `เสร็จ` · `รอผู้ใช้`  — อ่านกติกาใน `AGENTS.md` ก่อนเริ่ม

**สั่ง ChatGPT Codex** (environment ของ repo นี้ ตั้ง Setup script = `bash scripts/codex-setup.sh`) คัดลอกไปวางได้เลย:

```
อ่าน AGENTS.md แล้วทำงานถัดไปที่สถานะ "ว่าง" และ "ใครทำได้ = Codex" ใน TASKS.md (เริ่มที่ T02)
ทำตามหัวข้อ "เสร็จเมื่อ" ของงานนั้น เปลี่ยนสถานะใน TASKS.md แล้วเปิด PR เข้า branch claude/beautiful-goldberg-a1jt5q
พร้อมผลรัน pytest -q · ห้ามเรียกบริการที่เสียเงินและห้ามใส่ข้อมูลส่วนตัวลง repo
```

| # | งาน | ใครทำได้ | สถานะ |
|---|---|---|---|
| T01 | คลิป "มิ้นท์ ตอน 1" เวอร์ชันฟรี: ฉากที่เหลือด้วย engine local → ตัดต่อ 24 fps → QC | Claude (ใช้สื่อในบัญชีผู้ใช้) | เสร็จ (v3: กะพริบตา ปากตามเสียง รถไฟแล่น ฝน โทนสี เสียงบรรยากาศ · QC ผ่าน · รอผู้ใช้อนุมัติ Proof) |
| T02 | ชุดทดสอบอัตโนมัติ + CI | Codex | ว่าง |
| T03 | ฝ่ายผลิตใช้ทางฟรีเป็นค่าเริ่มต้นเมื่อไม่ได้อนุมัติเครดิตวิดีโอ | Codex | ว่าง |
| T04 | เร่งความเร็ว animate_still.py + โหมดพรีวิว | Codex | ว่าง |
| T05 | เว็บตัดต่อรองรับฉากวิดีโอ / `ซ้ำ:` / `เคลื่อนไหว:` / `localFx` | Codex | ว่าง |
| T06 | แก้ซับเร็วเกินอัตโนมัติ | Codex | ว่าง |
| T07 | ตรวจ path สื่อใน project.json ให้ปลอดภัย | Codex | ว่าง |
| T08 | ทดสอบ ComfyUI + Wan 2.2 กับ GPU จริง | ผู้ใช้ + Claude | รอผู้ใช้ |
| T09 | อัปเกรด 3 ช็อตเป็นวิดีโอ AI 720p (≈22 เครดิต Higgsfield) | ผู้ใช้อนุมัติ + Claude | รอผู้ใช้ |
| T10 | เชื่อม Drive D: เพื่ออนุมัติ/จัดเก็บจริง | ผู้ใช้ | รอผู้ใช้ |

---

### T02 · ชุดทดสอบอัตโนมัติ + CI (ทำก่อน เพราะงานถัดไปทุกงานต้องพึ่ง)
- สร้าง `tests/` (pytest) ครอบคลุม:
  - `build_subs.parse_script` / `build`: คีย์บรรทัดฉาก (`ตัวละคร:` `ช็อต:` `ท่าทาง:` `เคลื่อนไหว:` `ซ้ำ:` → meta `cast/shot/action/motion/repeat`), บรรทัด `@ชื่อ:`, จังหวะ `/ // ///`
  - `qc_check.py`: ภาพซ้ำมี `ซ้ำ:` แล้วไม่ตีกลับ, ไม่มีเหตุผลแล้วตีกลับ (ใช้วิดีโอสั้นที่สร้างด้วย ffmpeg)
  - `hf_plan.py plan`: ฉาก `ซ้ำ:` เป็นรายการ `reuse` ไม่คิดเงิน, `--motion marked` แนบ sheet เป็น `image_references` เมื่อโมเดลรองรับ, ความยาว = ceil(ฉาก/1.35) ไม่เกินเพดาน, `estimatedCredits` ถูก · `fetch` (ใช้ `file://` URL)
  - `i2v_prompt.build`: สภาพแวดล้อมใส่เฉพาะคำที่อยู่ในฉาก (ฉากร้านข้าวต้มต้องไม่มี train), ภาษาอังกฤษใน `เคลื่อนไหว:` ถูกใช้ตรง ๆ
  - `check_i2v.py`: คลิปลื่น = ผ่าน, คลิปตัดฉาก = ตกที่วินาทีถูก, คลิปค้าง = ตก
  - `animate_still.animate`: 540x960 1 วินาที ได้ไฟล์ 24 fps ถูกขนาด; twinkle ไม่ทำให้พื้นที่สว่างกว้างกะพริบ (std ≈ 0)
  - `comfy_i2v.run_one` กับ mock server (http.server): อัปโหลด, แทนค่า, length 4k+1, แปลง webp → mp4
  - `render.py`: โปรเจกต์ 2 ฉากสั้น ๆ ที่ตั้ง `"fps": 24` ได้ 24 fps · ฉากวิดีโอเล่นได้
  - `doc_control.py`: init → receive → decide (APPROVE/REJECT) → archive ในโฟลเดอร์ tmp (ห้ามแตะ `D:\`)
- `.github/workflows/tests.yml`: ubuntu + `apt-get install ffmpeg` + `pip install numpy pillow pytest` + `pytest -q`
- เสร็จเมื่อ: `pytest -q` ผ่านทั้งในเครื่องและใน CI โดยไม่ใช้อินเทอร์เน็ตและไม่ใช้เครดิต

### T03 · ฝ่ายผลิตใช้ทางฟรีเป็นค่าเริ่มต้น
- ใน `content-production/SKILL.md` ขั้นวิดีโอ: ถ้า `budget.allowVideoGeneration` เป็น `false` → ช็อตที่มี `เคลื่อนไหว:` ทำด้วย
  `i2v_free.py --engine local` อัตโนมัติ (ฟรี) แล้วแจ้งราคาอัปเกรดเป็น AI (จาก `hf_plan.py --motion marked`) ให้ผู้ใช้ตัดสินใจ
- เพิ่ม `motion.freeEngine` (`local` | `comfyui` | `none`) ใน `production.config.json` และให้ `i2v_free.py` อ่านค่านี้เมื่อไม่ระบุ `--engine`
- เสร็จเมื่อ: ทดสอบกับ `templates/project.toon3d.example.json` (ใส่ภาพทดสอบเอง) ได้วิดีโอทุกฉากที่ marked โดยไม่เรียก Higgsfield

### T04 · เร่งความเร็ว animate_still.py
- ตอนนี้ ~0.85 วินาที/เฟรม ที่ 1080x1920 เมื่อไม่มี OpenCV · เป้า: เร็วขึ้นอย่างน้อย 2 เท่า (คำนวณ grid/mask ล่วงหน้า, ทำงานเฉพาะกรอบ bounding box ของ breath/ripple/glow, วาด particle แบบ vectorized, `--workers` แบ่งช่วงเฟรมหลาย process)
- เพิ่ม `--preview` (540x960, crf สูง) ให้ดูตัวอย่างเร็ว
- เสร็จเมื่อ: ผลลัพธ์ต่างจากเดิมไม่เกินสายตาเห็น (เทียบเฟรม) และมีตัวเลขเวลาก่อน/หลังใน PR

### T05 · เว็บตัดต่อรองรับฉากวิดีโอ
- `video-studio-web/editor.html`: อ่านคีย์ `ซ้ำ:` `เคลื่อนไหว:` ในบรรทัดฉาก, แสดงป้าย "วิดีโอ/ภาพนิ่ง" ต่อฉาก, ถ้า `scenes[j].video` มีไฟล์ให้พรีวิวเป็นวิดีโอ, ส่งออก/นำเข้า project.json คง `localFx` `motionPrompt` `still` ไว้
- เสร็จเมื่อ: นำเข้า `templates/project.toon3d.example.json` แล้วส่งออกได้ค่าครบ ไม่หาย (ทดสอบด้วย Playwright)

### T06 · แก้ซับเร็วเกินอัตโนมัติ
- QC เตือนท่อนที่เร็วเกิน ~12 ตัวอักษร/วินาที (เช่น 'เป็น วัน ที่ เหนื่อย' 12.8) · เพิ่มตัวเลือกใน `build_subs.py` ให้แบ่งท่อน/ยืดเวลาแสดงอัตโนมัติ โดยไม่ทำให้ซับทับกัน และให้ `editor.html` ทำเหมือนกัน
- เสร็จเมื่อ: มีทดสอบ + คลิปตัวอย่างไม่มีคำเตือนนี้

### T07 · ความปลอดภัยของ path สื่อ
- `render.py`, `i2v_free.py`, `hf_plan.py fetch`, `check_i2v.py`: path ใน project.json ต้องอยู่ในโฟลเดอร์โปรเจกต์ (กัน `../` และ path นอกโปรเจกต์) ยกเว้นผู้ใช้ส่ง `--allow-outside`
- เสร็จเมื่อ: มีทดสอบกรณี `../../etc/passwd` ถูกปฏิเสธพร้อมข้อความไทย

### T08–T10 · ต้องใช้เครื่องหรือบัญชีของผู้ใช้ (agent ทำแทนไม่ได้)
- T08: เปิด ComfyUI บนเครื่องที่มี GPU (≥ 8–12 GB) โหลดโมเดล Wan 2.2 TI2V-5B แล้วรัน
  `python3 .claude/skills/cinematic-image-to-video/scripts/i2v_free.py project.json --engine comfyui`
  ถ้าชื่อโหนด/ไฟล์โมเดลไม่ตรง ให้ Export workflow ของตัวเอง (API) แล้วใส่ `--workflow`
- T09: เติมเครดิต Higgsfield แล้วสั่ง Claude ทำ 3 ช็อต 720p (≈22 เครดิต) ตามแผนในสกิล cinematic-image-to-video
- T10: ให้ Claude เข้าถึงโฟลเดอร์บนเครื่อง (Remote Control) หรือเปิดหน้า office บนเครื่องตัวเองเพื่ออนุมัติ/จัดเก็บลง `D:\VIDEO_WORKFLOW`
