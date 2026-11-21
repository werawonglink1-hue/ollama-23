# Risk Manager – Hard Rules (Deterministic)

**หลักการ**: LLM ห้ามเป็นคนตัดสินใจสุดท้าย  
Risk Engine ต้องเป็น Pure Function ที่ทดสอบได้

---

## กฎหลักที่แนะนำเริ่มต้น

| กฎ | ค่าเริ่มต้น (ปรับได้) | Action ถ้าละเมิด |
|----|------------------------|------------------|
| Risk ต่อ Trade | ≤ 0.75% ของ Equity | Veto หรือลด Lot |
| Max Daily Loss | 2.5% ของ Equity | Hard Pause + Flatten |
| Max Drawdown (จาก Peak) | 6% | Full Shutdown |
| Max Open Positions | 3 | Veto ใหม่ |
| Max Correlation Exposure | ตามที่กำหนด | ลด Lot หรือ Veto |
| Spread Threshold | > 2.5x average | Veto |
| Data Stale | > 5 วินาที | Veto + Alert |
| News Blackout | 15 นาทีก่อน-หลัง High Impact | Veto |
| Min RR Ratio | 1 : 1.5 | Veto หรือปรับ TP |

---

## ตัวอย่างการคำนวณ Lot (Simplified)

```python
def calculate_lot(equity, risk_pct, entry, sl, point_value):
    risk_amount = equity * (risk_pct / 100)
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return 0
    lot = risk_amount / (sl_distance * point_value)
    return round(lot, 2)
```

---

## Kill Switch Levels

1. **SOFT_PAUSE**  
   - หยุดเปิดออเดอร์ใหม่  
   - Position เดิมยังถือได้

2. **HARD_FLATTEN**  
   - ปิดทุก Position ทันที  
   - หยุดเปิดใหม่

3. **FULL_SHUTDOWN**  
   - หยุดระบบทั้งหมด  
   - ต้องมี human override ถึงจะเปิดใหม่ได้