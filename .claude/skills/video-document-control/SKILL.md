---
name: video-document-control
description: ระบบควบคุมเอกสารและอนุมัติวิดีโอ (Document Control & Video Approval) บน D:\VIDEO_WORKFLOW — รับคลิปจากทีมผลิต ตั้ง VIDEO ID ตรวจว่าเปิดได้และข้อมูลครบ จัดเข้าคิวรออนุมัติ บันทึกผลอนุมัติ/ไม่อนุมัติของมนุษย์พร้อม feedback ติดตามรอบแก้ไข จัดเก็บเฉพาะฉบับที่อนุมัติเข้า FINAL ARCHIVE (ตรวจ sha256 ทุกขั้น) ทะเบียนค้นย้อนหลังได้ และรายงานประจำวัน. ใช้เมื่อต้องรับไฟล์วิดีโอเข้าระบบ ส่งคลิปให้อนุมัติ บันทึกผลอนุมัติ จัดเก็บลง Drive D ค้นทะเบียน หรือทำรายงานสรุป.
---

# Video Document Control (ควบคุมเอกสารและอนุมัติวิดีโอ)

สคริปต์เดียว `scripts/doc_control.py` (Python 3 + ffmpeg/ffprobe) ทำทุกการย้าย/คัดลอก/บันทึก ห้ามย้ายไฟล์ในโฟลเดอร์ระบบด้วยมือ
ข้อกำหนดเต็มจากเจ้าของโปรเจกต์: `../content-production/references/charter.md` (ส่วนที่ 2)

```
D:\VIDEO_WORKFLOW
  01_INCOMING        ต้นฉบับทุกเวอร์ชัน (ห้ามลบ/แก้)
  02_REVIEW_QUEUE    ตรวจครบแล้ว รอ FINAL APPROVER
  03_REVISION        ไม่ผ่าน + ไฟล์ ..._FEEDBACK.md
  04_APPROVED        ฉบับที่อนุมัติ
  05_FINAL_ARCHIVE   ฉบับสุดท้ายแยกตาม PROJECT (ห้ามเขียนทับ)
  06_DOCUMENTATION   register.json/.csv · history.jsonl · reports · decisions · notices · orders
```

ชื่อไฟล์ `[PROJECT]_[VIDEO-ID]_[CONTENT-NAME]_V[VERSION]_[STATUS].mp4` เช่น `HISTORY_V001_SAMURAI_V02_REVISION.mp4`
(PROJECT/CONTENT-NAME ใช้ A-Z 0-9 - เท่านั้น ชื่อไทยใส่ `--title`; คลิปหลายขนาดใช้ CONTENT-NAME ต่อท้าย `-9X16` / `-16X9`)

## คำสั่ง

```bash
DC=".claude/skills/video-document-control/scripts/doc_control.py"      # โฟลเดอร์ระบบจาก production.config.json (workflowRoot)
python3 $DC init                                                          # สร้าง/ตรวจโครงสร้าง + ทดสอบสิทธิ์เขียน
python3 $DC receive out/clip.mp4 --project HISTORY --name SAMURAI-9X16 --title "ซามูไรคนสุดท้าย" \
        --producer "ฝ่ายผลิต AI" --coordinator "AI Video Coordinator" --order ORD-20261121-01
python3 $DC queue                                                         # รายการรออนุมัติ
python3 $DC decide V001 --approve --approver "<ชื่อผู้ใช้>" --evidence "ข้อความ '<…>' เวลา <…>"
python3 $DC decide V001 --reject  --approver "<ชื่อผู้ใช้>" --evidence "…" --notes "<เหตุผล/สิ่งที่ต้องแก้>"
python3 $DC process-decisions                                             # ผลที่ผู้ใช้กดในหน้า Office (06_DOCUMENTATION/decisions)
python3 $DC resubmit V001 out/clip_v2.mp4 --changes "แก้อะไรไปตาม feedback"
python3 $DC update V002 --producer "…" --coordinator "…"   แล้ว  organize V002   # ข้อมูลไม่ครบ
python3 $DC status [V001] · search "คำ" --status ARCHIVED · history V001 · report [--date 2026-11-21] · export · verify
```

สถานะ: `RECEIVED` → `PENDING_REVIEW` (หรือ `INCOMPLETE` แจ้งผู้รวบรวม) → `REVISION_REQUIRED` ⟲ resubmit → `APPROVED` → `ARCHIVED`
exit code: 0 สำเร็จ · 1 ผิดพลาด · 2 ข้อมูล/ไฟล์ไม่ครบ (INCOMPLETE) · 3 หยุดแจ้งผู้ดูแล (ไฟล์ซ้ำ ชื่อไม่ตรง จะเขียนทับ สถานะไม่ตรง) · 4 จัดเก็บ/ตรวจปลายทางล้มเหลว

## สิ่งที่สคริปต์ตรวจให้ทุกครั้ง

- **RECEIVE**: เปิดไฟล์ได้จริง (ffprobe + ถอดรหัสทั้งไฟล์) · sha256 ซ้ำกับไฟล์ใดในทะเบียน = หยุด · ชื่อไฟล์ตามรูปแบบแต่ไม่ตรงทะเบียน = หยุด
  · PROJECT+CONTENT-NAME ซ้ำ = หยุด (ให้ใช้ resubmit) · คัดลอกเข้า INCOMING แล้วตรวจ sha256
- **ORGANIZE**: ข้อมูลทะเบียนครบ ความยาว ความละเอียด มีเสียง (+ Coordinator/ไฟล์ซับ ถ้า config บังคับ) ไม่ครบ = `INCOMPLETE` + เขียน `notices/<วันที่>.md`
- **DECIDE**: ต้องมีชื่อผู้อนุมัติที่เป็นมนุษย์ (ชื่อที่ดูเป็น AI/บอทถูกปฏิเสธ) + หลักฐาน · คลิปต้อง `PENDING_REVIEW` และเวอร์ชันตรง
  · sha256 ไฟล์ในคิวต้องตรงทะเบียน และตรงกับไฟล์ที่ผู้อนุมัติเปิดดู (จากหน้าเว็บ) · ไม่อนุมัติต้องมีเหตุผล
- **ARCHIVE**: เฉพาะ `APPROVED` ที่มีหลักฐาน · เวอร์ชันที่อนุมัติ = เวอร์ชันล่าสุด · ปลายทางมีอยู่แล้ว = หยุด (ไม่เขียนทับ)
  · หลังคัดลอก: ตรวจมีไฟล์จริง ขนาดตรง sha256 ตรง เปิดได้ ไม่ผ่าน = ลบสำเนาเสีย บันทึก `ARCHIVE_FAILED` และแจ้ง ห้ามรายงานว่าสำเร็จ
- เข้า Drive D / โฟลเดอร์ระบบไม่ได้ = ล้มทันทีพร้อมข้อความ ไม่มีการทำงานต่อแบบแอบ ๆ
- ล็อกทะเบียนระหว่างเขียน (หลายทีมส่งพร้อมกันได้) · ทุกการกระทำต่อท้าย `history.jsonl` (ใคร ทำอะไร เมื่อไร กับไฟล์ไหน)

## หลักฐานการอนุมัติที่ยอมรับ

1. ไฟล์จากหน้า Office ห้องอนุมัติ (`06_DOCUMENTATION/decisions/*.json` มีชื่อผู้อนุมัติ เวลา และ sha256 ของไฟล์ที่เปิดดู) → `process-decisions`
2. ข้อความของผู้ใช้ในแชตที่ระบุ VIDEO ID ชัดเจน เช่น "อนุมัติ V001" → ใส่ข้อความเต็ม + วันเวลาใน `--evidence`
   ข้อความกำกวม ("โอเค", "ดีมาก" โดยไม่ระบุคลิป) ไม่ใช่หลักฐาน ให้ถามยืนยันว่าอนุมัติคลิปไหน
