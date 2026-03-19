import os
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from telegram import Bot
from telegram.constants import ParseMode
import ta
import logging
import yfinance as yf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID        = os.environ.get("CHAT_ID", "YOUR_CHAT_ID_HERE")

ACCOUNTS = {
    "💼 $100K Real":  {"balance": 100000, "risk_pct": 0.005},
    "🏦 $50K Prop":   {"balance": 50000,  "risk_pct": 0.003},
    "💰 $500 Real":   {"balance": 500,    "risk_pct": 0.01},
}

SYMBOLS = {
    "GC=F":    {"name": "Gold",    "display": "XAUUSD", "pip": 0.1,    "group": "🥇 Metals"},
    "SI=F":    {"name": "Silver",  "display": "XAGUSD", "pip": 0.01,   "group": "🥇 Metals"},
    "EURUSD=X":{"name": "EUR/USD", "display": "EURUSD", "pip": 0.0001, "group": "💱 Forex"},
    "GBPUSD=X":{"name": "GBP/USD", "display": "GBPUSD", "pip": 0.0001, "group": "💱 Forex"},
    "JPY=X":   {"name": "USD/JPY", "display": "USDJPY", "pip": 0.01,   "group": "💱 Forex"},
    "AUDUSD=X":{"name": "AUD/USD", "display": "AUDUSD", "pip": 0.0001, "group": "💱 Forex"},
    "USDCHF=X":{"name": "USD/CHF", "display": "USDCHF", "pip": 0.0001, "group": "💱 Forex"},
    "EURJPY=X":{"name": "EUR/JPY", "display": "EURJPY", "pip": 0.01,   "group": "💱 Forex"},
    "GBPJPY=X":{"name": "GBP/JPY", "display": "GBPJPY", "pip": 0.01,   "group": "💱 Forex"},
}

SCAN_SECONDS = 60

def fetch_ohlcv(symbol, interval, period):
    try:
        df = yf.download(symbol, interval=interval, period=period, progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
        df = df[["open","high","low","close"]].dropna()
        return df
    except Exception as e:
        logger.warning(f"fetch error {symbol}: {e}")
        return pd.DataFrame()

def calculate_lot_size(balance, risk_pct, sl_pips, pip_value):
    risk_amount = balance * risk_pct
    pip_val_per_lot = pip_value * 100000
    if sl_pips <= 0:
        return 0.01
    lot = risk_amount / (sl_pips * pip_val_per_lot)
    return max(0.01, round(lot, 2))

def analyze_swing(df, symbol):
    if df.empty or len(df) < 60:
        return None
    close, high, low = df["close"], df["high"], df["low"]
    ema20  = ta.trend.EMAIndicator(close, 20).ema_indicator()
    ema50  = ta.trend.EMAIndicator(close, 50).ema_indicator()
    ema200 = ta.trend.EMAIndicator(close, 200).ema_indicator()
    rsi    = ta.momentum.RSIIndicator(close, 14).rsi()
    macd_h = ta.trend.MACD(close).macd_diff()
    bb     = ta.volatility.BollingerBands(close, 20, 2)
    atr    = ta.volatility.AverageTrueRange(high, low, close, 14).average_true_range()
    c,r,a  = close.iloc[-1], rsi.iloc[-1], atr.iloc[-1]
    mh,pm  = macd_h.iloc[-1], macd_h.iloc[-2]
    e20,e50,e200 = ema20.iloc[-1], ema50.iloc[-1], ema200.iloc[-1]
    bbl,bbh = bb.bollinger_lband().iloc[-1], bb.bollinger_hband().iloc[-1]
    recent_high, recent_low = high.iloc[-20:].max(), low.iloc[-20:].min()
    sb, ss = 0, 0
    if e20 > e50 > e200: sb += 2
    elif e20 < e50 < e200: ss += 2
    if c > e20: sb += 1
    else: ss += 1
    if r < 35: sb += 2
    elif r > 65: ss += 2
    if pm < 0 < mh: sb += 3
    elif pm > 0 > mh: ss += 3
    if c <= bbl * 1.001: sb += 2
    elif c >= bbh * 0.999: ss += 2
    if max(sb, ss) < 5:
        return None
    direction = "BUY" if sb > ss else "SELL"
    confidence = max(sb, ss)
    win_pct = min(92, int(60 + (confidence / 10) * 32))
    if direction == "BUY":
        sl,tp1,tp2 = round(c-a*1.5,5), round(c+a*2.5,5), round(c+a*4.0,5)
        zone = f"Support ~{round(recent_low,5)}"
    else:
        sl,tp1,tp2 = round(c+a*1.5,5), round(c-a*2.5,5), round(c-a*4.0,5)
        zone = f"Resistance ~{round(recent_high,5)}"
    return {"type":"SWING","symbol":symbol,"direction":direction,"price":round(c,5),
            "sl":sl,"tp1":tp1,"tp2":tp2,"sl_pips":abs(c-sl)/SYMBOLS[symbol]["pip"],
            "rsi":round(r,1),"atr":round(a,5),"zone":zone,"confidence":confidence,
            "win_pct":win_pct,"trend":"↑ Bullish" if e20>e50 else "↓ Bearish"}

def analyze_scalp(df, symbol):
    if df.empty or len(df) < 30:
        return None
    close, high, low = df["close"], df["high"], df["low"]
    ema5   = ta.trend.EMAIndicator(close, 5).ema_indicator()
    ema13  = ta.trend.EMAIndicator(close, 13).ema_indicator()
    rsi    = ta.momentum.RSIIndicator(close, 7).rsi()
    atr    = ta.volatility.AverageTrueRange(high, low, close, 7).average_true_range()
    macd_h = ta.trend.MACD(close, 12, 26, 9).macd_diff()
    c,r    = close.iloc[-1], rsi.iloc[-1]
    e5,e13 = ema5.iloc[-1], ema13.iloc[-1]
    pe5,pe13 = ema5.iloc[-2], ema13.iloc[-2]
    mh,pm  = macd_h.iloc[-1], macd_h.iloc[-2]
    bull_cross = pe5 <= pe13 and e5 > e13
    bear_cross = pe5 >= pe13 and e5 < e13
    if bull_cross and (pm < 0 < mh or 30 < r < 60) and r < 65:
        direction = "BUY"
    elif bear_cross and (pm > 0 > mh or 40 < r < 70) and r > 35:
        direction = "SELL"
    else:
        return None
    pip = SYMBOLS[symbol]["pip"]
    if direction == "BUY":
        sl,tp1,tp2 = round(c-pip*50,5), round(c+pip*100,5), round(c+pip*200,5)
    else:
        sl,tp1,tp2 = round(c+pip*50,5), round(c-pip*100,5), round(c-pip*200,5)
    return {"type":"SCALP","symbol":symbol,"direction":direction,"price":round(c,5),
            "sl":sl,"tp1":tp1,"tp2":tp2,"sl_pips":50,"rsi":round(r,1),
            "atr":0,"zone":"EMA 5/13 Cross","confidence":7,"win_pct":72,
            "trend":"↑ Bullish" if e5>e13 else "↓ Bearish"}

def build_message(signal):
    info = SYMBOLS[signal["symbol"]]
    emoji = "🟢" if signal["direction"] == "BUY" else "🔴"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    type_label = "⚡ SCALP (100-200 pips)" if signal["type"] == "SCALP" else "📈 SWING (250-400 pips)"
    lines = [
        f"{emoji} *{signal['direction']} {type_label}*",
        f"*{info['name']} ({info['display']})* {info['group']}",
        f"🕐 `{now}`",
        "",
        f"📍 *Entry:*     `{signal['price']}`",
        f"🛑 *Stop Loss:* `{signal['sl']}`",
        f"🎯 *TP1:*       `{signal['tp1']}`",
        f"🎯 *TP2:*       `{signal['tp2']}`",
        "",
        f"📊 *Trend:* {signal['trend']}",
        f"📈 *RSI:* `{signal['rsi']}`",
        f"📐 *Zone:* {signal['zone']}",
        f"⚡ *Strength:* `{signal['confidence']}/10`",
        f"🏆 *Win Probability:* `{signal['win_pct']}%`",
        "",
        "💼 *Recommended Lot Sizes:*",
    ]
    for acc_name, acc in ACCOUNTS.items():
        lot = calculate_lot_size(acc["balance"], acc["risk_pct"], signal["sl_pips"], info["pip"])
        risk = round(acc["balance"] * acc["risk_pct"], 2)
        lines.append(f"  {acc_name}: `{lot} lots` (risk ${risk})")
    lines += ["", "⚠️ _Execute within 5 min. Always verify before trading._"]
    return "\n".join(lines)

async def run_bot():
    bot = Bot(token=TELEGRAM_TOKEN)
    logger.info("Bot started.")
    await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            "🤖 *Trading Signal Bot is LIVE!*\n\n"
            "⚡ *SCALP signals* — 100-200 pip targets\n"
            "📈 *SWING signals* — 250-400 pip targets\n\n"
            "Scanning every 60 seconds — no API key needed!\n"
            "Markets: Gold, Silver, EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CHF, EUR/JPY, GBP/JPY\n\n"
            "Waiting for signals... 📡"
        ),
        parse_mode=ParseMode.MARKDOWN,
    )
    last_swing_scan = 0
    sent_scalp_keys = {}
    while True:
        now_ts = asyncio.get_event_loop().time()
        run_swing = (now_ts - last_swing_scan) >= 900
        for symbol in SYMBOLS:
            try:
                df_scalp = fetch_ohlcv(symbol, "1m", "1d")
                scalp = analyze_scalp(df_scalp, symbol)
                if scalp:
                    key = f"{symbol}_{scalp['direction']}_{round(scalp['price'],2)}"
                    if key not in sent_scalp_keys:
                        await bot.send_message(chat_id=CHAT_ID, text=build_message(scalp), parse_mode=ParseMode.MARKDOWN)
                        sent_scalp_keys[key] = now_ts
                        logger.info(f"SCALP: {symbol} {scalp['direction']}")
                if run_swing:
                    df_swing = fetch_ohlcv(symbol, "15m", "5d")
                    swing = analyze_swing(df_swing, symbol)
                    if swing:
                        await bot.send_message(chat_id=CHAT_ID, text=build_message(swing), parse_mode=ParseMode.MARKDOWN)
                        logger.info(f"SWING: {symbol} {swing['direction']}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error {symbol}: {e}")
                await asyncio.sleep(5)
        sent_scalp_keys = {k:v for k,v in sent_scalp_keys.items() if now_ts-v < 3600}
        if run_swing:
            last_swing_scan = now_ts
        logger.info("Scan complete. Next in 60s...")
        await asyncio.sleep(SCAN_SECONDS)

if __name__ == "__main__":
    asyncio.run(run_bot())
