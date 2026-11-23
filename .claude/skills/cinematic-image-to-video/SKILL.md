---
name: cinematic-image-to-video
description: ทำวิดีโอแอนิเมชัน 3D แบบภาพยนตร์จากภาพนิ่งของแต่ละช็อต (image-to-video) ตามมาตรฐาน "CINEMATIC 3D ANIMATION — IMAGE TO VIDEO" ของช่อง — ตัวละครหน้าตา ทรงผม เสื้อผ้าเหมือนเดิมทุกเฟรม (แนบ character sheet) การแสดงเป็นธรรมชาติ (หายใจ กะพริบตา สีหน้า) กล้องแบบภาพยนตร์ สภาพแวดล้อมขยับเฉพาะที่มีในฉาก ห้ามภาพกระโดด/นิ้วเกิน/ตัวหนังสือ แล้วตรวจคลิปด้วย check_i2v.py ก่อนตัดต่อที่ 24 fps · มีทางเลือกฟรีไม่ใช้ Higgsfield (i2v_free.py: engine local ภาพนิ่งมีชีวิต 2.5D ทุกเครื่อง, engine comfyui วิดีโอ AI Wan 2.2 บน GPU ของผู้ใช้). ใช้เมื่อผู้ใช้ขอ "Gen วิดีโอจากภาพ", "ทำให้ภาพขยับ", "image to video", "ให้ตัวละครเคลื่อนไหว", "CINEMATIC 3D ANIMATION" หรือขั้น "วิดีโอ" ของฝ่ายผลิต.
---

# Cinematic 3D Animation — Image to Video

เปลี่ยนภาพช็อตที่สร้างไว้ (ระยะ 2 ของ `higgsfield-studio`) ให้เป็นวิดีโอแอนิเมชัน 3D ระดับภาพยนตร์ โดยยึด
มาตรฐานของช่องใน `references/prompt-standard.md` (ต้นฉบับครบทุกข้อ) ทุกช็อตได้ prompt 7 ส่วนจาก
`scripts/i2v_prompt.py`: เปิด → ความต่อเนื่องของตัวละคร → การกระทำ → การแสดง → กล้อง → สภาพแวดล้อม → คุณภาพ + ข้อห้าม

## ก่อนเริ่ม

- ต้องมี character sheet (`characters[].sheet.job_id`) และภาพช็อต (`scenes[j].job_id`) แล้ว
  ยังไม่มี → ทำระยะ 1–2 ใน `higgsfield-studio` ก่อน
- เลือกช็อตที่จะทำวิดีโอ: ใส่ `เคลื่อนไหว:` ในบรรทัดฉาก (เขียนเป็น **ภาษาอังกฤษ** จะแม่นที่สุด) เช่น
  `| เคลื่อนไหว: a tear slowly rolls down her cheek, then a small trembling smile spreads across her face |`
  หรือเขียนลง `scenes[j].motionPrompt` ภายหลัง · ฉากที่มี `ซ้ำ:` ใช้ภาพนิ่งกับกล้องใหม่ ไม่ต้องทำวิดีโอ
- วิดีโอใช้เครดิตเสมอ (`production.config.json` › `budget.allowVideoGeneration: false`) → **ต้องขออนุมัติพร้อมตัวเลขทุกครั้ง**

## ขั้นตอน

```bash
H=.claude/skills/higgsfield-studio/scripts/hf_plan.py
P=.claude/skills/cinematic-image-to-video/scripts
python3 $P/i2v_prompt.py work/<โปรเจกต์>/project.json --scene 4          # ดู prompt ที่จะส่ง (ทุกฉาก: ไม่ใส่ --scene)
python3 $H plan work/<โปรเจกต์>/project.json --motion marked > plan_motion.json   # marked | key | all
```

1. ดู `estimatedCredits` ในแผน แล้ว `estimate_video_cost` ทุกรายการ → ขออนุมัติผู้ใช้ (บอกจำนวนช็อต วินาที ความละเอียด และยอดรวม)
2. `generate_video_batch` (ครั้งละ ≤ 12) ด้วย `params` จากแผนตรง ๆ → `jobs_wait` → เก็บ `{"index": {"url", "job_id"}}` → `hf_plan.py fetch`
   (ฉากได้ `video` + `video_job_id` ภาพนิ่งเดิมเก็บใน `still`)
3. ตรวจทุกคลิป: `python3 $P/check_i2v.py work/<โปรเจกต์>/project.json` — ภาพกระโดด/ตัดฉาก จอดำ ภาพค้าง สัดส่วน
   แล้ว **เปิดดูภาพเทียบ** `qc/clip1-sceneN-i2v.jpg` (เฟรมแรก กลาง ท้าย + หน้าตรงจาก sheet) ว่าหน้า ทรงผม ชุด สี
   ตรงเดิม ไม่มีนิ้วเกิน แขนขาซ้ำ หน้าบิด หรือตัวหนังสือ — ไม่ผ่าน: รายงานผู้ใช้ สร้างใหม่ได้เมื่อผู้ใช้อนุมัติเครดิตเท่านั้น
4. ตัดต่อแบบภาพยนตร์ 24 fps: ใส่ `"fps": 24` ใน project.json (หรือ `render.py --fps 24`) แล้ว `qc_check.py` ตามปกติ
   render.py เล่นวิดีโอช้าลงได้ถึง 1.35 เท่าแล้วค้างเฟรมท้าย แผนจึงขอความยาว ≈ ความยาวฉาก ÷ 1.35 (เพดาน `motion.seconds`)

## โมเดลและราคา (วัดจริง 21 พ.ย. 2026 · 9:16 ไม่มีเสียง · เช็ก `estimate_video_cost` ทุกครั้ง)

| โมเดล | แนบ sheet | ราคา | ใช้เมื่อ |
|---|---|---|---|
| `seedance_2_0_mini` 720p | ✔ | 1 เครดิต/วินาที (5 วิ = 5) | **ค่าเริ่มต้น** คุ้มที่สุดที่ล็อกตัวละครด้วย sheet ได้ |
| `seedance_2_0_mini` 480p | ✔ | 0.5/วินาที | ร่าง/ทดสอบช็อต |
| `grok_video_v15_lite` 720p | ✘ | 1/วินาที | ไม่ต้องแนบ sheet (ยึดภาพแรกอย่างเดียว) |
| `kling3_0` pro (sound off) | ✘ | 1.75/วินาที | การขยับละเอียดขึ้น |
| `grok_video_v15` 720p | ✔ | 4.5/วินาที | ฟิสิกส์/กล้องซับซ้อน |
| `kling3_0` 4k | ✘ | 6/วินาที (5 วิ = 30) | ต้องการ 4K จริง |
| `seedance_2_0` 1080p / 4k | ✔ | 12 / 22 ต่อวินาที (5 วิ 4K = 110) | งานมาสเตอร์คุณภาพสูงสุด |

ตั้งค่าใน `production.config.json` › `motion` (model, resolution, seconds) หรือ `project.json` › `motion`

**เรื่อง 4K:** TikTok / Reels / Shorts แสดงผลสูงสุดราว 1080p และ render.py ส่งออก 1080x1920 อยู่แล้ว 4K จึงคุ้มเฉพาะงาน
YouTube แนวนอนหรือมาสเตอร์เก็บไว้ (แพงกว่า 6–22 เท่า) ค่าเริ่มต้นใช้ 720p แล้วขยายเป็น 1080p ตอนตัดต่อ

## ทางเลือกเสริม: ไม่ใช้ Higgsfield (ฟรี)

ใช้เมื่อเครดิตหมด ผู้ใช้ไม่อนุมัติเครดิตวิดีโอ หรืออยากพรีวิวก่อนจ่าย — สคริปต์เดียว `i2v_free.py` เลือก engine ได้ 2 แบบ

| engine | ต้องมี | ได้อะไร | ทำไม่ได้ |
|---|---|---|---|
| `local` (`animate_still.py`) | Python + numpy + Pillow + ffmpeg (มี `opencv-python-headless` เร็วขึ้น ~4 เท่า) ทุกเครื่อง ไม่ต่อเน็ต | ภาพนิ่ง "มีชีวิต" 2.5D: กล้อง dolly/แพน + ส่ายแบบถือกล้อง, ไฟเมือง/หลอดไฟระยิบ (เฉพาะจุดไฟเล็ก ๆ), ฝุ่นในแสง, ไอน้ำ, พื้นเปียกพลิ้ว, หายใจ, แสงจอเต้น | กะพริบตา สีหน้า มือขยับ น้ำตาไหล |
| `comfyui` (`comfy_i2v.py`) | ComfyUI บนเครื่องที่มี GPU ~8–12 GB+ และโมเดล Wan 2.2 TI2V-5B (Apache-2.0 ใช้เชิงพาณิชย์ได้) | วิดีโอ AI จริง 720p 24 fps ตาม prompt มาตรฐานเดียวกัน (การแสดงครบตามสเปก) | ไม่มี GPU = รันไม่ได้ |

```bash
P=.claude/skills/cinematic-image-to-video/scripts
python3 $P/i2v_free.py work/<โปรเจกต์>/project.json --engine local --scenes all     # ฉากที่ยังเป็นภาพนิ่งทุกฉาก
python3 $P/i2v_free.py work/<โปรเจกต์>/project.json --engine comfyui --server http://127.0.0.1:8188 [--workflow my_api.json]
python3 $P/check_i2v.py work/<โปรเจกต์>/project.json && python3 .claude/skills/social-video-studio/scripts/render.py work/<โปรเจกต์>/project.json
```

- **engine local ต้องวางเอฟเฟกต์ให้ตรงภาพ**: เปิดดูภาพช็อต (ทำกริด 10×10 ช่วยอ่านพิกัด) แล้วใส่ `scenes[j].localFx` เช่น
  `{"twinkle": [[0,0,1,0.5]], "particles": 30, "steam": [[0.64,0.43]], "breath": [[0.5,0.45,0.2]], "ripple": [[0,0.7,0.4,1]], "glow": [[0.5,0.55,0.2]], "focus": [0.5,0.3]}`
  พิกัดเป็นสัดส่วนภาพ 0–1 · ไอน้ำวางเหนือชาม/หม้อ · `ripple` เฉพาะพื้นสะท้อน ห้ามครอบตัวละคร · `twinkle` จำกัดกรอบให้พ้นหน้า
  ไม่ใส่ = เลือกให้จากคำในฉาก (กลางคืน/ไฟเมือง → twinkle, ทุกฉากมีฝุ่นในแสง)
- **engine comfyui**: workflow มาตรฐาน `references/comfyui_wan22_ti2v_5b_api.json` (ชื่อไฟล์โมเดลตามเทมเพลต Wan 2.2 ของ ComfyUI)
  ถ้าเครื่องผู้ใช้ตั้งชื่อต่างไป ให้ Export workflow ของตัวเอง (API) แล้วส่ง `--workflow` สคริปต์จะใส่ภาพ prompt seed ความยาว (4k+1 เฟรม) fps ขนาดให้เอง
- ผลทุก engine เขียน `video` + `generator` ลงฉาก ภาพนิ่งเดิมเก็บใน `still` · ภาพยังเป็นภาพ AI → คงป้ายเครดิตเดิมไว้

## กติกา

- ตัวละครต้องเป็นของช่องเอง (ออกแบบด้วย character-sheet) ห้ามเลียนแบบคนจริงหรือตัวละครที่มีลิขสิทธิ์
- สภาพแวดล้อมขยับเฉพาะสิ่งที่มีในภาพ ห้ามเติมของใหม่ · ไม่มีเสียงจากโมเดล (`generate_audio: false`) ใช้เสียงพากย์/เพลงของเราเอง
- งานล้มเหลวหรือ QC ไม่ผ่าน → รายงานพร้อมเหตุผล ห้ามสร้างซ้ำเองโดยไม่ถาม · ภาพ AI ติดป้ายเครดิตเสมอ (fetch ทำให้)
