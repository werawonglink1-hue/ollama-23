---
name: higgsfield-studio
description: ต่อ Higgsfield (MCP) เข้ากับ social-video-studio เพื่อยกระดับเสียงและภาพของคลิป — เสียงพากย์ไทย AI (qwen_audio_tts) ที่เว้นจังหวะตามสคริปต์และซับตรงเสียงด้วย Whisper, ภาพประกอบต่อฉาก (gpt_image_2_6) ตามสไตล์คลิป, ตัดพื้นหลังเป็นสติกเกอร์ในวงกลม, ขยายภาพ, เพลงประกอบ, ทำนายไวรัล และเตรียมโพสต์ TikTok โดยคุมเครดิตทุกครั้ง ใช้เมื่อผู้ใช้ขอ "ใช้ Higgsfield", "เสียงพากย์ AI", "สร้างภาพประกอบ AI", "ภาพ/เสียงให้ดีขึ้น", "โพสต์ลง TikTok".
---

# Higgsfield Studio (เสียงพากย์ + ภาพ AI สำหรับคลิป)

สคริปต์ช่วย: `scripts/hf_plan.py` (วางแผนคำขอจาก project.json และดึงผลกลับเข้า project.json)
ใช้คู่กับ `social-video-studio/scripts/voice_align.py`, `whisper_words.py`, `render.py`

## กฎเครดิต (สำคัญที่สุด)

1. เช็ก `balance` ก่อน แล้วประเมินราคาทุกรายการด้วย `estimate_audio_cost` / `estimate_image_cost` (`upscale_image`, `reframe` ใช้ `get_cost: true`)
2. บอกผู้ใช้ว่าจะสร้างอะไรกี่ชิ้น รวมกี่เครดิต และเหลือเท่าไร **รอผู้ใช้อนุมัติก่อนสร้าง** (ยกเว้นผู้ใช้ให้งบไว้แล้วและยังไม่เกินงบ)
3. งานล้มเหลวหรือหมดเวลา → รายงานผู้ใช้ **ห้ามสร้างซ้ำเอง** (`generate_image_batch` ที่ล้มบางรายการ ให้เก็บ job id เดิมไว้ ตรวจผลก่อน)
4. สร้างหลายภาพใช้ `generate_image_batch` (ครั้งละไม่เกิน 12) แล้ว `jobs_wait` ทีเดียว
5. ก่อนสร้างครั้งแรกเรียก `get_preferences` ไม่สร้าง project/folder ใน Higgsfield เว้นแต่ค่าที่ตั้งไว้หรือผู้ใช้ขอ
6. ของฟรีมาก่อน: เพลงสังเคราะห์ใน `render.py`, ภาพจริงถูกลิขสิทธิ์ (`web-image-research`), ภาพจาก ComfyUI บนเครื่องผู้ใช้ (`comfyui-scenes`) ใช้ Higgsfield กับจุดที่คุ้มที่สุด (เสียงพากย์ ภาพตัวละคร/ภาพเปิดเรื่อง)

ราคาที่วัดจริง (21 พ.ย. 2026, ราคาอาจเปลี่ยน ต้อง estimate ทุกครั้ง):

| รายการ | โมเดล | เครดิตโดยประมาณ |
|---|---|---|
| เสียงพากย์ไทย 1 คลิป (~50–60 วิ) | `qwen_audio_tts` | ≈ 0.2 |
| ภาพประกอบ 1 ภาพ / 1 ช็อต | `gpt_image_2_6` (1k) | ≈ 0.75 |
| character sheet 1 ตัว (ครั้งเดียวต่อซีรีส์) | `seedream_5_5` 2K | ≈ 3.5 |
| วิดีโอจากภาพ 3 วิ 480p / 5 วิ 720p | `grok_video_v15_lite` | ≈ 3 / 5 |
| วิดีโอ 5 วิ | `kling3_0_turbo` / `seedance_2_5` | ≈ 7.5 / 35 |
| เพลงประกอบ 60 วิ | `elevenlabs_music_v2_5` | ≈ 8.7 (แพง ใช้เมื่อผู้ใช้ขอเท่านั้น) |

## ภาพเนื้อเรื่องจริง: ตัวละคร → ภาพทุกช็อต → วิดีโอ (3 ระยะ)

ระยะหลังใช้ job_id ของระยะก่อน จึงต้องทำทีละระยะ: plan → estimate → สร้าง → jobs_wait → fetch (เก็บ job_id) → ระยะถัดไป

```bash
H=.claude/skills/higgsfield-studio/scripts/hf_plan.py
python3 $H plan project.json --characters > plan1.json     # 1) character sheet ต่อตัว (ใช้ซ้ำทั้งซีรีส์)
python3 $H plan project.json --voice --images all > plan2.json   # 2) ภาพทุกช็อต + เสียงพากย์ (แนบ sheet ของตัวละครในช็อต)
python3 $H plan project.json --motion marked > plan3.json   # 3) วิดีโอจากภาพช็อตที่มี "เคลื่อนไหว:" (key = + ช็อตแรก, all = ทุกช็อต)
python3 $H fetch planN.json resultsN.json                    # ผลรูปแบบ {"0": {"url": "...", "job_id": "..."}}
```

1. **ตัวละคร**: `project.characters` = `[{name, role, look, outfit}]` → ทำตามเวิร์กโฟลว์ `character-sheet` ของ Higgsfield
   (`get_workflow_instructions`) ด้วย `entry` และ `sheetStyle` ในแผน (การ์ตูน 3D = Classic 3D, สมจริง = Realism)
   ค่าเริ่มต้น seedream_5_5 2K 16:9 ≈ 3.5 เครดิต/ตัว; โหมดประหยัด `budgetParams` (gpt_image_2_6 ≈ 0.75) ใช้เมื่อผู้ใช้เลือก
   ดู sheet ทุกภาพก่อนไปต่อ: ตัวละครเดียว หน้าตา/ชุดตรงคำบรรยาย · ห้ามเลียนแบบคนจริงหรือตัวละครที่มีลิขสิทธิ์
2. **ภาพทุกช็อต**: prompt = ช็อต + ฉาก + ท่าทาง + ตัวละครในช็อต (รูปลักษณ์คงที่) + สไตล์ · `medias` แนบ sheet ของตัวละครในช็อต
   (gpt_image_2_6 ≈ 0.75/ช็อต) fetch ใส่ `media` + `job_id` ให้แต่ละฉาก และติด `เครดิต: ภาพสร้างด้วย AI (Higgsfield)` ให้เอง
   ฉากที่มี `ซ้ำ: เหตุผล` เป็นรายการ `reuse` (ไม่ส่งให้ Higgsfield ไม่เสียเครดิต) fetch ใช้ภาพของฉากก่อนหน้าให้ มุมกล้องใหม่ตาม `กล้อง:`
   ภาพ 9:16 ที่ได้ขนาด 752x1344 render.py ขยายเป็น 1080x1920 ให้เอง · ตัวอย่างครบ 3 ระยะ: `social-video-studio/templates/project.toon3d.example.json`
3. **วิดีโอ**: `generate_video` grok_video_v15_lite (start_image = ภาพช็อต) ≈ 1 เครดิต/วินาที (3 วิ 480p = 3)
   ค่าใน `production.config.json` → `motion` · render.py เล่นช้าลง/ค้างเฟรมสุดท้ายเมื่อวิดีโอสั้นกว่าฉาก
   ทำเฉพาะช็อตสำคัญ: คลิป 60 วิ 8 ช็อตถ้าทำวิดีโอทุกช็อต 5 วิ ≈ 40 เครดิต

ราคาตัวอย่างต่อคลิป 60 วิ (8 ช็อต): ภาพ 8 × 0.75 = 6 · วิดีโอ 2 ช็อต × 3 วิ = 6 · เสียง 0.2 → ≈ 12 เครดิต (+ sheet 3.5/ตัว ครั้งแรกของซีรีส์)

## สายงานเต็ม

```
project.json ──hf_plan.py plan──► รายการคำขอ (เสียง/ภาพ/เพลง) ──estimate──► ขออนุมัติ
   │
   ├─ เสียง:  generate_audio(qwen_audio_tts) → jobs_wait → ดาวน์โหลด voice_raw.wav
   │          → whisper_words.py (เวลาแต่ละคำ) → voice_align.py assemble (ตัดเสียงตรง // /// ใส่ความเงียบตามสคริปต์)
   │          → ได้ voice + timings ใน project.json (ซับตรงเสียงจริง)
   ├─ ภาพ:    generate_image_batch(gpt_image_2_6) → jobs_wait → ฉากวงกลม: remove_background → PNG สติกเกอร์
   │          → hf_plan.py fetch (ดาวน์โหลด + ใส่ media ลงฉาก)
   └─ เพลง:   (ถ้าผู้ใช้ขอ) generate_audio(elevenlabs_music_v2_5, force_instrumental) → musicFile
   ▼
render.py → เปิดดูเฟรม → (ถ้าต้องการ) media_upload ไฟล์ MP4 → virality_predictor / tiktok_prepare_publish
```

### 1) วางแผนคำขอ

```bash
python3 .claude/skills/higgsfield-studio/scripts/hf_plan.py plan work/<โปรเจกต์>/project.json --voice --images missing > work/<โปรเจกต์>/hf_plan.json
#   --images missing (เฉพาะฉากที่ยังไม่มีภาพ) | all | hero (ฉากแรกเท่านั้น) | none ; --music ถ้าผู้ใช้ขอเพลง ; --clip 2 เฉพาะคลิปเดียว
```

ทุกรายการมี `params` ที่ส่งให้เครื่องมือ Higgsfield ได้ทันที:
- เสียง: ข้อความพูดที่ลบช่องว่างระหว่างคำไทยแล้ว (`//` → ขึ้นบรรทัด, `///` → เว้นบรรทัด), `language: th`,
  `instruction` ตามผู้เล่า (สารคดี ละมุน ครูหน่อง มานะ ลึกลับ ขำ ≤128 ตัวอักษร), `speech_rate` ตามความเร็ว (ช้า 0.9 · ปกติ 1.0 · เร็ว 1.1)
- ภาพ: prompt จากบรรทัดฉาก + คำต่อท้ายตามสไตล์ภาพ + ตัวละครจาก brief, สัดส่วนพอดีหน้าต่างภาพ
  (คอลลาจแนวตั้ง/วงกลม 1:1, คอลลาจแนวนอน 3:2, สไตล์อื่น 9:16 หรือ 16:9) ฉากวงกลมมี `cutout: true`

### 2) เสียงพากย์

- เลือกเสียงด้วย `list_voices` (ทดสอบแล้วว่าเสียง preset "Marcus" พูดไทยได้ชัด) ใส่ `voice_id` ลงในแผน (`--voice-id`)
- ไม่ใช้เสียงโคลนของคนจริง เว้นแต่เจ้าของเสียงยินยอม (`create_voice` ใช้กับเสียงของผู้ใช้เองเท่านั้น)
- TTS จะอ่านต่อเนื่อง ไม่หยุดตาม `/ // ///` ต้องผ่าน `voice_align.py assemble` เสมอ:

```bash
python3 .claude/skills/social-video-studio/scripts/whisper_words.py media/clip1-voice.wav --out media/clip1-words.json
python3 .claude/skills/social-video-studio/scripts/voice_align.py assemble script.txt --voice media/clip1-voice.wav \
        --words media/clip1-words.json --out media/clip1-voice-paced.wav --speed normal --project project.json --clip 1
```

`assemble` ตัดเสียงเป็นกลุ่มตาม `//` และ `///` ใส่ความเงียบตามความยาวที่สคริปต์กำหนด แล้วเขียน `voice` + `timings` ลง project.json
(ทดสอบจริง: เสียง 47.8 วิ → 60.3 วิ มี 24 ช่วงเว้นจังหวะ ซับ 44 ท่อนไม่ทับกัน) ถ้า `render.py` เตือน `TOO FAST` ที่ท่อนใด
ให้แบ่งท่อนด้วย `/` หรือลด `speech_rate` แล้วสร้างเสียงใหม่ (ถามผู้ใช้ก่อน เพราะใช้เครดิต)

### 3) ภาพประกอบ

- ส่ง `generate_image_batch` ตามแผน (index = เลขรายการในแผน) → `jobs_wait` → `show_generation_by_ids` ครั้งเดียวให้ผู้ใช้ดู
- ฉาก `cutout: true`: `remove_background` (`media_type: image`) แล้วใช้ URL ของผล PNG แทน → `render.py` ทำเป็นสติกเกอร์ขอบขาวในวงกลม
- ภาพเล็กหรือแตก: `upscale_image` (ต้องใส่ width/height ของภาพเดิม, `get_cost: true` ก่อน)
- ภาพคนที่ดูเหมือนจริงให้ใส่ `เครดิต: ภาพสร้างด้วย AI` ในบรรทัดฉาก และห้ามสร้างภาพเลียนแบบคนจริงที่ระบุตัวได้
- เก็บผลเป็น `results.json` รูปแบบ `{"0": "https://...", "3": "https://..."}` แล้ว:

```bash
python3 .claude/skills/higgsfield-studio/scripts/hf_plan.py fetch work/<โปรเจกต์>/hf_plan.json work/<โปรเจกต์>/results.json
```

### 4) หลังเรนเดอร์ (ทำเมื่อผู้ใช้ขอ)

- อัปโหลด MP4: `media_upload` → `curl -f -X PUT -H 'Content-Type: video/mp4' --upload-file <ไฟล์> '<upload_url>'` → `media_confirm` (ได้ลิงก์ให้ผู้ใช้ดู)
- `virality_predictor` (`action: create`, `medias: [{role: video, id: <media_id>}]`) วิเคราะห์ hook/การดูจนจบ ส่งต่อให้ Growth Hacker และ Video Optimization Specialist
- `reframe` ใช้กับ **วิดีโอที่ผู้ใช้ถ่ายมาเอง** เท่านั้น (คลิปของเรา `render.py` ทำ 9:16 และ 16:9 ให้อยู่แล้ว) วิดีโอยาวสุด 60 วิ
- TikTok: `tiktok_accounts` → `tiktok_prepare_publish` (ไฟล์ต้องอยู่บน Higgsfield, MP4 3–600 วิ, 23–60 fps) ผู้ใช้ตรวจและกดโพสต์เองในฟอร์ม
  **ห้ามโพสต์แทนผู้ใช้** และใส่ `is_aigc` ตามจริงเมื่อผู้ใช้บอกแล้ว

## เมื่อเครื่องที่รันอยู่ดาวน์โหลดไฟล์จาก Higgsfield ไม่ได้

บางสภาพแวดล้อม (เช่น คอนเทนเนอร์คลาวด์ที่จำกัดเว็บ) เข้า CDN ของ Higgsfield หรือ Wikimedia ไม่ได้ ให้ทำงานใน Higgsfield sandbox แทน:

- `sandbox_exec` มี ffmpeg, Python + Pillow, faster-whisper และอินเทอร์เน็ต ไฟล์ใน `/home/user` อยู่ได้ 24 ชั่วโมง
- นำสคริปต์ของ skill เข้าไป (git clone ถ้า repo เข้าถึงได้ หรือส่งไฟล์ผ่าน heredoc) แล้ว `curl` ผลงานจาก URL ของ `jobs_wait`
- เรนเดอร์นานเกิน 2 นาทีใช้ `background: true` (และ `size: "xl"` สำหรับเรนเดอร์สุดท้าย) ดูเฟรมด้วย `image_paths`
- เสร็จแล้วอัปโหลด MP4 ด้วย `media_upload` + `curl PUT` ในคำสั่งเดียวกัน แล้ว `media_confirm` ส่งลิงก์ให้ผู้ใช้
