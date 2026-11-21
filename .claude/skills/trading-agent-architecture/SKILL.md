---
name: trading-agent-architecture
description: แพ็กเกจสถาปัตยกรรมบอทเทรดแบบหลาย Agent (Market Data → Market Analyst → Strategy → Risk Manager ที่มีสิทธิ์ veto → Execution → Trade Monitor → Journal → 3D Office แสดงผล) พร้อมกฎความเสี่ยงแบบ deterministic, workflow ตัวอย่าง XAUUSD และ JSON schema ระหว่าง Agent. ใช้เมื่อผู้ใช้จะออกแบบ รีวิว หรือเริ่มพัฒนาระบบเทรดอัตโนมัติ (MT5) — เป็นโปรเจกต์คนละเรื่องกับงานคลิป และไม่ใช่คำแนะนำการลงทุน.
---

# Trading Agent Architecture (เอกสารอ้างอิงบอทเทรดหลาย Agent)

เอกสารต้นฉบับของผู้ใช้ (v1.0, 19 พ.ย. 2026) อยู่ใน `references/`:

| ไฟล์ | เนื้อหา |
|---|---|
| `00_PACKAGE_README.md` | สรุปแพ็กเกจและลำดับการพัฒนา |
| `01_STRUCTURE_REVIEW.md` | รีวิวโครงสร้างก่อนเริ่ม (สิ่งที่ถูกปฏิเสธและเหตุผล) |
| `02_FINAL_ARCHITECTURE.md` | Agent แต่ละตัว หน้าที่ ข้อมูลเข้า-ออก |
| `03_WORKFLOW.md` | ลำดับงานจริงตั้งแต่ข้อมูลตลาดถึงบันทึกผล (ตัวอย่าง XAUUSD) |
| `04_RISK_RULES.md` | กฎ Risk Manager (ความเสี่ยงต่อไม้ ขาดทุนรายวัน drawdown kill switch) |
| `05_JSON_SCHEMAS.md` | รูปแบบข้อความระหว่าง Agent |
| `06_ORG_CHART_WORKFLOW.png` | ผังองค์กร + workflow |

อ่าน `02` → `03` → `04` ก่อนตอบหรือเขียนโค้ดเสมอ

## หลักที่ห้ามละเมิด (จากเอกสารของผู้ใช้)

1. **Risk Manager มีสิทธิ์ veto เด็ดขาด** และต้องเป็น pure function ที่ทดสอบได้ — LLM วิเคราะห์และเสนอได้ แต่ห้ามเป็นผู้ตัดสินใจสุดท้าย
2. Strategy Agent เสนอ Trade Proposal ได้เท่านั้น ห้ามส่งออเดอร์; Execution Agent รับเฉพาะคำสั่งที่ APPROVED
3. ทุกการตัดสินใจบันทึกแบบแก้ไขไม่ได้ (Proposal → Risk Decision → Execution → Result)
4. 3D Office เป็นชั้นแสดงผลอย่างเดียว ห้ามสั่งเทรด
5. ลำดับพัฒนา: Backend + Risk Engine + Audit Log → Orchestrator/State Machine → MT5 Execution → 3D Office → Journal/Dashboard (**อย่าเริ่มจาก 3D**)

## กติกาเพิ่มเติมเมื่อ Claude ช่วยพัฒนา

- เริ่มจาก backtest / บัญชีทดลอง (demo/paper) เสมอ **ห้ามเชื่อมบัญชีเงินจริงหรือส่งออเดอร์จริง** จนกว่าผู้ใช้สั่งชัดเจนเป็นครั้ง ๆ
- รหัส MT5 / API key เก็บใน environment variable หรือ secret store ห้ามใส่ในโค้ด ห้าม commit
- เขียนเทสต์ให้ Risk Engine ครบทุกกฎในตาราง `04_RISK_RULES.md` (ขอบล่าง/บน, SL = 0, ข้อมูลเก่าเกิน 5 วินาที, ช่วงข่าว) ก่อนต่อ Execution
- ค่าในตารางกฎเป็น "ค่าเริ่มต้นที่ปรับได้" ไม่ใช่คำแนะนำการลงทุน ผู้ใช้ต้องเป็นผู้กำหนดเอง
- เครื่องมืออ่านข้อมูลตลาด/บัญชีที่เชื่อมไว้ในเซสชัน (ถ้ามี) ใช้แบบอ่านอย่างเดียว ไม่ส่งคำสั่งซื้อขาย
- แยกโปรเจกต์นี้ออกจาก repo งานคลิป (โฟลเดอร์หรือ repo ใหม่) เมื่อเริ่มเขียนโค้ดจริง
