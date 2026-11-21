# Real Workflow – ต้นทางถึงปลายทาง
**ตัวอย่าง: XAUUSD**

---

## Flow แบบละเอียด (จากต้นทาง → ปลายทาง)

```
1. Market Data Agent
   └─ ดึงราคา M5 / M15 / H1 + ATR + Spread
   └─ Validate data quality
   └─ ส่ง Market Snapshot

2. Market Analyst
   └─ วิเคราะห์โครงสร้าง + Regime
   └─ ส่ง Market Context

3. Strategy Agent
   └─ เช็คเงื่อนไข Entry
   └─ สร้าง Trade Proposal (BUY/SELL/HOLD)
   └─ ส่ง Proposal ไปที่ Risk Manager

4. Risk Manager (Hard Gate)
   ├─ คำนวณ Lot Size จาก Risk % + SL distance
   ├─ ตรวจ Max Risk / Daily Loss / Drawdown
   ├─ ตรวจ Max Open Positions
   ├─ ตรวจ Spread / News / Data freshness
   │
   ├─ ถ้าผ่าน → APPROVED + Final Parameters
   └─ ถ้าไม่ผ่าน → VETOED + Reason (จบที่นี่)

5. Execution Agent (เฉพาะที่ Approved)
   └─ ส่งคำสั่งไป MT5
   └─ รอผล Fill

6. Trade Monitor
   └─ ยืนยันว่า Position เปิดสำเร็จ
   └─ ติดตาม Slippage และสถานะ

7. Journal Agent
   └─ บันทึกทุกอย่างแบบ Immutable
   └─ (Proposal → Risk Decision → Execution → Result)

8. 3D Office
   └─ อัปเดตสถานะ Agent ทุกตัวแบบ Real-time
   └─ แสดง Veto / Approved / Error ชัดเจน
```

---

## State Machine สั้นๆ

```
IDLE
  → DATA_COLLECTING
  → ANALYZING
  → STRATEGY_PROPOSING
  → RISK_REVIEWING
       ├─ VETOED → LOGGED → IDLE
       └─ APPROVED → EXECUTING
            → MONITORING
            → LOGGED
            → IDLE
```

---

## กรณีพิเศษที่ต้องรองรับ

1. **Data Stale / Broker Disconnect**  
   → Orchestrator เรียก Soft Pause ทันที

2. **Max Daily Loss ถึง**  
   → Hard Flatten + Full Pause จนถึงวันถัดไป

3. **Risk Manager Veto ติดต่อกันหลายครั้ง**  
   → แจ้งเตือน + ลดความถี่การวิเคราะห์

4. **Manual Kill Switch**  
   → หยุดทุกอย่างทันที + ปิด position (ถ้าตั้งค่า)