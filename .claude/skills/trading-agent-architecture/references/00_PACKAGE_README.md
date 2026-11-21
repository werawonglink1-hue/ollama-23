# Agent Bot Trading Architecture Package
**Version 1.0 | Reviewed & Ready for Development**  
วันที่: 19 พฤศจิกายน 2026

---

## ไฟล์ในแพ็กเกจนี้

| ไฟล์ | คำอธิบาย |
|------|----------|
| `01_STRUCTURE_REVIEW.md` | ตรวจสอบ + รีเจคโครงสร้างก่อนเริ่มโปรเจค |
| `02_FINAL_ARCHITECTURE.md` | โครงสร้าง Agent สุดท้าย (ผ่าน Review) |
| `03_WORKFLOW.md` | Workflow จริง ต้นทาง → ปลายทาง |
| `04_RISK_RULES.md` | กฎ Risk Manager (Deterministic) |
| `05_JSON_SCHEMAS.md` | ตัวอย่าง Message Schema ระหว่าง Agent |
| `06_ORG_CHART_WORKFLOW.png` | ชาร์ตผังองค์กร + Workflow (ภาพ) |

---

## สรุปสั้นๆ

- **Risk Manager มีสิทธิ์ Veto เด็ดขาด** ทุกคำสั่ง
- Strategy Agent เสนอได้เท่านั้น ห้ามส่งออเดอร์
- LLM วิเคราะห์และเสนอแผนได้ แต่การอนุมัติและความเสี่ยงต้องผ่านกฎที่กำหนดไว้ชัดเจน
- 3D Office เป็น Visualization Layer เท่านั้น
- ทุกอย่างต้อง Audit ได้

---

## ลำดับการพัฒนาที่แนะนำ

1. Backend + Risk Engine + Audit Log (สำคัญที่สุด)
2. Orchestrator + State Machine
3. เชื่อม MT5 Execution
4. 3D Office แสดงสถานะจริง
5. Journal + Dashboard

**อย่าเริ่มจาก 3D ก่อน**