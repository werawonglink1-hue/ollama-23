---
name: comfyui-scenes
description: สร้างภาพประกอบฉากฟรีด้วย ComfyUI ที่รันบนเครื่องผู้ใช้ (ใช้ GPU ของผู้ใช้ ไม่เสียเครดิต) ผ่าน HTTP API — สร้างภาพทุกฉากที่ยังไม่มีสื่อใน project.json ตามสไตล์คลิป ขนาดพอดีเลย์เอาต์ (หน้าต่างการ์ด วงกลม 9:16 16:9) หรือใช้ workflow ที่ผู้ใช้ Export เอง (SDXL, Flux ฯลฯ). ใช้เมื่อผู้ใช้มี ComfyUI/GPU และขอ "สร้างภาพประกอบฟรี", "ใช้ ComfyUI", "ไม่อยากเสียเครดิต", "ใช้โมเดลของเราเอง".
---

# ComfyUI Scenes (ภาพประกอบฟรีจาก ComfyUI บนเครื่องผู้ใช้)

สคริปต์: `scripts/comfy_generate.py` (Python 3 ล้วน คุยกับ ComfyUI ทาง `POST /prompt` → `GET /history/{id}` → `GET /view`)

## เตรียมเครื่อง (ครั้งเดียว)

1. ติดตั้ง ComfyUI ตามหน้า GitHub ของ ComfyUI (Windows มีแบบ portable หรือแอปเดสก์ท็อป) ต้องมี GPU ที่ VRAM พอ (SDXL ≥ 8 GB แนะนำ)
2. วาง checkpoint ใน `ComfyUI/models/checkpoints/` เช่น `sd_xl_base_1.0.safetensors`
3. เปิดแบบรับเฉพาะเครื่องตัวเอง: `python main.py --listen 127.0.0.1 --port 8188`

สัญญาอนุญาต: ComfyUI เป็น GPL-3.0 (เราแค่เรียกผ่าน HTTP ไม่ได้รวมโค้ด) ส่วน **โมเดลแต่ละตัวมีเงื่อนไขของตัวเอง** ตรวจก่อนใช้กับช่องที่หารายได้
(เช่น SDXL base ใช้ CreativeML Open RAIL++-M ใช้เชิงพาณิชย์ได้ภายใต้ข้อห้ามการใช้งานในสัญญา; FLUX.1 [dev] ตัวโมเดลเป็นสัญญาแบบไม่ใช่เชิงพาณิชย์
ต้องอ่านเงื่อนไขเรื่องภาพที่สร้างให้ละเอียด) จด `checkpoint + license` ไว้ใน project.json ให้ Brand Guardian ตรวจ

## ใช้งาน

```bash
C=.claude/skills/comfyui-scenes/scripts/comfy_generate.py
python3 $C one "Thai village at dawn, editorial documentary photo" --size 1024x1024 --out work/<โปรเจกต์>/media/test.png
python3 $C project work/<โปรเจกต์>/project.json --clip 1 --ckpt sd_xl_base_1.0.safetensors     # ทุกฉากที่ยังไม่มีภาพ
python3 $C project work/<โปรเจกต์>/project.json --workflow my_flux_api.json --steps 24          # workflow ของผู้ใช้
python3 $C --server http://127.0.0.1:8188 project project.json --overwrite --seed 42             # สร้างใหม่ทับทั้งหมด
```

- ขนาดภาพอัตโนมัติ: คอลลาจแนวตั้ง/วงกลม 1024×1024, คอลลาจแนวนอน 1216×832, สไตล์อื่น 832×1472 (9:16) หรือ 1472×832 (16:9)
- prompt = บรรทัดฉาก (หรือ `scenes[j].prompt` ที่ Image Prompt Engineer เขียนไว้) + คำต่อท้ายตามสไตล์ + ตัวละครจาก brief
  ฉากวงกลมเติม "single person portrait, centered, plain light background" ไว้ตัดพื้นหลังทีหลัง
- seed คงที่ต่อฉาก (`seed + คลิป×100 + ฉาก`) สร้างซ้ำได้ภาพเดิม; บันทึก project.json ทุกภาพเผื่อหยุดกลางทาง
- workflow ของผู้ใช้: ใน ComfyUI กด Workflow → Export (API) แล้วแทนค่าด้วย `{{PROMPT}}` `{{NEGATIVE}}` `"{{SEED}}"` `"{{WIDTH}}"` `"{{HEIGHT}}"` `"{{STEPS}}"`

## ตัดพื้นหลังเป็นสติกเกอร์ (ฉากวงกลม)

ภาพ PNG ที่มีพื้นโปร่งใสจะถูกวาดเป็นสติกเกอร์ขอบขาวในวงกลมโดย `render.py` และเว็บ ทางเลือกฟรีบนเครื่องผู้ใช้:
`pip install "rembg[cli]"` แล้ว `rembg i media/clip1-scene2.png media/clip1-scene2-cut.png` (แก้ `media` ของฉากเป็นไฟล์ -cut)
หรือใช้ `remove_background` ของ Higgsfield (มีค่าเครดิต)

## ความปลอดภัย

- เปิด ComfyUI ที่ `127.0.0.1` เท่านั้น ห้าม `--listen 0.0.0.0` บนเครือข่ายสาธารณะ (ใครก็สั่งรันงานบนเครื่องได้)
- custom node คือโค้ดที่รันบนเครื่องผู้ใช้ ติดตั้งเฉพาะที่เชื่อถือได้และผู้ใช้อนุญาต
- ภาพคนที่ดูเหมือนจริงให้ใส่ `เครดิต: ภาพสร้างด้วย AI` และห้ามสร้างภาพเลียนแบบคนจริงที่ระบุตัวได้
