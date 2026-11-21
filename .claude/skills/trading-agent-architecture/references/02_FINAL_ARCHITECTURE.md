# Final Architecture – Agent Bot Trading System
**Version 1.0 | ผ่านการ Review แล้ว**

---

## ภาพรวมระบบ

```
[Market Data] → [Market Analyst] → [Strategy Agent]
                                          ↓
                                   [Risk Manager]  ←── Veto Power (Hard Gate)
                                          ↓ (Approved only)
                                   [Execution Agent]
                                          ↓
                                   [Trade Monitor]
                                          ↓
                                   [Journal Agent]
                                          ↓
                                   [3D Office UI]  ←── Status only (read-only)
```

**Central Orchestrator** ควบคุมลำดับการทำงานทั้งหมด (State Machine)

---

## รายละเอียด Agent แต่ละตัว

### 1. Market Data Agent
**หน้าที่**
- ดึงราคา + Indicator จาก MT5 (M5, M15, H1, H4)
- ตรวจสอบ Data Quality:
  - Stale data?
  - Missing candles?
  - Abnormal spread?
  - Broker connection lag?
- ส่งข้อมูลที่ผ่าน validation เท่านั้น

**Output**: Validated Market Snapshot

---

### 2. Market Analyst Agent
**หน้าที่**
- วิเคราะห์โครงสร้างตลาด (Higher High / Lower Low)
- ระบุ Market Regime (Trending / Ranging / High Volatility)
- Support / Resistance สำคัญ
- Bias ภาพรวม (Bullish / Bearish / Neutral)

**Output**: Market Context Report (structured JSON)

---

### 3. Strategy Agent
**หน้าที่**
- รับ Market Context
- ตรวจสอบเงื่อนไข Entry ตามกลยุทธ์ที่กำหนด (EMA, RSI, ATR, Price Action ฯลฯ)
- สร้าง **Trade Proposal** เท่านั้น

**สำคัญ**: ห้ามมีสิทธิ์ส่งออเดอร์เด็ดขาด

**Output**: Trade Proposal  
```json
{
  "action": "BUY" | "SELL" | "HOLD",
  "symbol": "XAUUSD",
  "entry_zone": [3720.0, 3722.0],
  "suggested_sl": 3714.5,
  "suggested_tp": 3735.0,
  "confidence": 0.72,
  "reason": "...",
  "strategy_id": "EMA_RSI_ATR_v1"
}
```

---

### 4. Risk Manager Agent (หัวใจของระบบ)
**หน้าที่**
- รับ Trade Proposal
- คำนวณด้วย **Deterministic Rules** เท่านั้น:
  - Position size จาก Risk % และ ATR/SL distance
  - ตรวจ Max Risk per trade
  - ตรวจ Max Daily Loss / Max Drawdown
  - ตรวจ Max Open Positions
  - ตรวจ Correlation / Exposure
  - ตรวจ Spread / Slippage threshold
  - ตรวจ News blackout window
- **Veto ได้ทุกกรณี** แม้ Strategy จะมั่นใจ 100%

**Output**:
- `APPROVED` + Final Lot + Final SL/TP
- หรือ `VETOED` + เหตุผลชัดเจน

**กฎเหล็ก**: LLM ใช้ได้แค่ช่วยเขียนเหตุผลเท่านั้น ห้ามตัดสินใจ

---

### 5. Execution Agent
**หน้าที่**
- รับเฉพาะคำสั่งที่ Risk Manager อนุมัติแล้ว
- ส่งออเดอร์ผ่าน MT5 API
- จัดการ Retry / Partial Fill
- ห้ามแก้ไข Lot / SL / TP เอง

---

### 6. Trade Monitor Agent
**หน้าที่**
- ตรวจสอบว่าออเดอร์เปิดสำเร็จจริง
- ติดตาม Slippage, Fill quality
- ตรวจ Position ว่ายังตรงกับที่ตั้งใจไว้หรือไม่
- สามารถ Trigger Close / Partial Close ได้เมื่อผิดปกติ

---

### 7. Journal Agent
**หน้าที่**
- บันทึกทุกขั้นตอนแบบ Immutable:
  - Proposal
  - Risk Decision (รวมเหตุผล Veto)
  - Execution Result
  - P/L เมื่อปิด
  - Market Context ตอนเข้า
- ใช้สำหรับ Post-trade Analysis และ Audit

---

### 8. Orchestrator (Supervisor)
**หน้าที่**
- ควบคุม State Machine ของ workflow
- จัดการ Timeout / Retry
- เรียก Kill Switch ได้
- อัปเดตสถานะไปยัง 3D Office

---

## 3D Office Mapping

| Agent              | ตำแหน่งใน 3D Office          | สถานะที่แสดง          |
|--------------------|------------------------------|-----------------------|
| Market Data        | Server / Data Room           | Feeding / Error       |
| Market Analyst     | Analyst Desk                 | Analyzing / Idle      |
| Strategy Agent     | Strategy Desk                | Proposing / Waiting   |
| Risk Manager       | Risk Desk (ใกล้ Command)     | Reviewing / Vetoed    |
| Execution Agent    | Execution Desk               | Sending / Done        |
| Trade Monitor      | Monitor Desk                 | Watching / Alert      |
| Journal Agent      | Archive Room                 | Logging               |
| Orchestrator       | Command Center               | Running / Paused      |