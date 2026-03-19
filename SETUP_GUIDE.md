# 🤖 Forex Signal Bot — Full Setup Guide

## STEP 1 — Create Your Telegram Bot (BotFather)

1. Open Telegram → search `@BotFather` → press **START**
2. Type `/newbot`
3. Enter a name: e.g. `MyForexSignals`
4. Enter a username ending in `bot`: e.g. `myforex_signals_bot`
5. Copy your **TOKEN** (looks like: `7341829456:AAF_xyzABC...`)

## STEP 2 — Get Your Chat ID

1. Open Telegram → search `@userinfobot` → press **START**
2. It shows your **Chat ID** (a number like `928374651`)
3. Copy it

## STEP 3 — Get Free Market Data API Key

1. Go to: https://twelvedata.com
2. Click **Get Free API Key**
3. Sign up (free)
4. Copy your API key from the dashboard

## STEP 4 — Deploy on Railway (FREE, runs 24/7)

1. Go to: https://railway.app
2. Sign up with GitHub (free)
3. Click **New Project** → **Deploy from GitHub repo**
4. Upload the bot files OR use GitHub Desktop to push them
5. In Railway dashboard → click your project → **Variables** tab
6. Add these 3 environment variables:
   ```
   TELEGRAM_TOKEN = your_bot_token_here
   CHAT_ID        = your_chat_id_here
   TWELVEDATA_KEY = your_api_key_here
   ```
7. Click **Deploy** → bot starts running 24/7!

## STEP 5 — What Signals Look Like on Telegram

```
🟢 BUY SIGNAL — Gold (XAUUSD)
🕐 2024-03-15 14:30 UTC

📍 Entry:    2318.45
🛑 Stop Loss: 2305.20
🎯 TP1:      2335.00
🎯 TP2:      2352.80

📊 Trend: ↑ Bullish
📈 RSI: 38.2
📐 Zone: Support: 2301.10
⚡ Signal Strength: 8/10
🏆 Est. Win Probability: 78%

💼 Recommended Lot Sizes:
  💼 $100K Real: 0.45 lots  (risk: $500)
  🏦 $50K Prop:  0.22 lots  (risk: $150)
  💰 $500 Real:  0.01 lots  (risk: $5)
```

## Account Risk Settings

| Account      | Balance  | Risk/Trade | Max Loss/Trade |
|-------------|----------|------------|----------------|
| $100K Real  | $100,000 | 0.5%       | $500           |
| $50K Prop   | $50,000  | 0.3%       | $150           |
| $500 Real   | $500     | 1.0%       | $5             |

## Markets Scanned (Every 15 Minutes)

- XAUUSD — Gold
- XAGUSD — Silver
- EURUSD — Euro/Dollar
- GBPUSD — Pound/Dollar
- USDJPY — Dollar/Yen
- USDCHF — Dollar/Franc
- AUDUSD — Aussie/Dollar
- EURJPY — Euro/Yen
- GBPJPY — Pound/Yen

## Analysis Used (Multi-Confluence)

- ✅ EMA 20/50/200 — Trend direction
- ✅ RSI 14 — Overbought/Oversold
- ✅ MACD — Momentum crossover
- ✅ Bollinger Bands — Squeeze breakout
- ✅ ATR — Volatility-based SL/TP
- ✅ Support & Resistance zones

**A signal is only sent when 5+ out of 10 confluence points align.**

## MT5 (XM Broker) — How to Execute

1. Open MT5 on phone/PC
2. When signal arrives on Telegram:
   - Open the pair (e.g. XAUUSD)
   - Set direction (Buy/Sell)
   - Set lot size as shown in signal
   - Set Stop Loss price from signal
   - Set Take Profit (TP1 or TP2) from signal
   - Click OK to execute

## Notes

- The bot scans every 15 minutes
- Only high-confluence signals are sent (not every candle)
- Expect 2-6 signals per day across all pairs
- Always check the signal yourself before trading
- Never risk money you cannot afford to lose
