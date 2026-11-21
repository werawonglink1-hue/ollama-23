# Message Schemas ระหว่าง Agent

## 1. Market Snapshot (จาก Market Data)

```json
{
  "timestamp": "2026-11-19T16:15:00+07:00",
  "symbol": "XAUUSD",
  "timeframes": {
    "M5": { "close": 3721.45, "atr": 4.2 },
    "M15": { "close": 3721.30, "atr": 7.8 },
    "H1": { "close": 3719.80, "atr": 18.5 }
  },
  "spread": 0.28,
  "data_quality": "GOOD"
}
```

## 2. Trade Proposal (จาก Strategy Agent)

```json
{
  "proposal_id": "prop_20261119_001",
  "symbol": "XAUUSD",
  "action": "BUY",
  "entry_zone": [3720.5, 3722.0],
  "suggested_sl": 3714.0,
  "suggested_tp": 3738.0,
  "confidence": 0.68,
  "strategy_id": "ema_rsi_structure_v1",
  "reason": "Bullish structure break + RSI reclaim 50 + EMA cross",
  "market_context_ref": "ctx_20261119_001"
}
```

## 3. Risk Decision (จาก Risk Manager)

```json
{
  "proposal_id": "prop_20261119_001",
  "decision": "APPROVED",
  "final_lot": 0.12,
  "final_sl": 3714.0,
  "final_tp": 3735.0,
  "risk_pct_used": 0.68,
  "checks": {
    "max_risk": "PASS",
    "daily_loss": "PASS",
    "open_positions": "PASS",
    "spread": "PASS",
    "data_freshness": "PASS"
  },
  "reason": "All hard rules passed. Lot sized to 0.68% risk."
}
```

หรือกรณี Veto:

```json
{
  "proposal_id": "prop_20261119_001",
  "decision": "VETOED",
  "reason": "Would exceed max open positions (current 3/3)",
  "checks": {
    "open_positions": "FAIL"
  }
}
```