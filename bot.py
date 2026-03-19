import os
import asyncio
import aiohttp
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from telegram import Bot
from telegram.constants import ParseMode
import ta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID        = os.environ.get("CHAT_ID", "YOUR_CHAT_ID_HERE")
TWELVEDATA_KEY = os.environ.get("TWELVEDATA_KEY", "YOUR_TWELVEDATA_KEY_HERE")

ACCOUNTS = {
    "💼 $100K Real":  {"balance": 100000, "risk_pct": 0.005},   # 0.5%
    "🏦 $50K Prop":   {"balance": 50000,  "risk_pct": 0.003},   # 0.3%
    "💰 $500 Real":   {"balance": 500,    "risk_pct": 0.01},    # 1.0%
}

SYMBOLS = {
    "XAUUSD": {"name": "Gold",           "pip_value": 0.1,   "contract": 100},
    "EURUSD": {"name": "EUR/USD",        "pip_value": 0.0001,"contract": 100000},
    "GBPUSD": {"name": "GBP/USD",        "pip_value": 0.0001,"contract": 100000},
    "USDJPY": {"name": "USD/JPY",        "pip_value": 0.01,  "contract": 100000},
    "USDCHF": {"name": "USD/CHF",        "pip_value": 0.0001,"contract": 100000},
    "AUDUSD": {"name": "AUD/USD",        "pip_value": 0.0001,"contract": 100000},
    "XAGUSD": {"name": "Silver",         "pip_value": 0.01,  "contract": 5000},
    "EURJPY": {"name": "EUR/JPY",        "pip_value": 0.01,  "contract": 100000},
    "GBPJPY": {"name": "GBP/JPY",        "pip_value": 0.01,  "contract": 100000},
}

SCAN_INTERVAL_MINUTES = 15   # scan every 15 min
# ─────────────────────────────────────────────────────────────────────────────


def calculate_lot_size(balance: float, risk_pct: float, sl_pips: float,
                       pip_value: float, price: float) -> float:
    """Risk-based lot size calculator."""
    risk_amount = balance * risk_pct
    pip_value_per_lot = pip_value * 100000 / price if pip_value < 1 else pip_value
    if sl_pips <= 0:
        return 0.01
    lot = risk_amount / (sl_pips * pip_value_per_lot)
    lot = max(0.01, round(lot, 2))
    return lot


async def fetch_ohlcv(session: aiohttp.ClientSession, symbol: str,
                      interval: str = "15min", outputsize: int = 100) -> pd.DataFrame:
    """Fetch OHLCV data from Twelve Data."""
    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={symbol}&interval={interval}"
        f"&outputsize={outputsize}&apikey={TWELVEDATA_KEY}"
    )
    async with session.get(url) as resp:
        data = await resp.json()

    if "values" not in data:
        logger.warning(f"No data for {symbol}: {data.get('message','unknown error')}")
        return pd.DataFrame()

    df = pd.DataFrame(data["values"])
    df = df.rename(columns={"open":"open","high":"high","low":"low",
                             "close":"close","volume":"volume"})
    for col in ["open","high","low","close"]:
        df[col] = pd.to_numeric(df[col])
    df = df.iloc[::-1].reset_index(drop=True)   # oldest → newest
    return df


def analyze(df: pd.DataFrame, symbol: str) -> dict | None:
    """
    Multi-confluence technical analysis:
    - EMA 20/50/200 trend filter
    - RSI overbought/oversold
    - MACD crossover
    - Bollinger Band squeeze breakout
    - ATR-based SL & TP
    Returns signal dict or None.
    """
    if df.empty or len(df) < 60:
        return None

    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # ── Indicators ────────────────────────────────────────────────────────────
    ema20  = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    ema50  = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    ema200 = ta.trend.EMAIndicator(close, window=200).ema_indicator()

    rsi = ta.momentum.RSIIndicator(close, window=14).rsi()

    macd_obj  = ta.trend.MACD(close)
    macd_line = macd_obj.macd()
    macd_sig  = macd_obj.macd_signal()
    macd_hist = macd_obj.macd_diff()

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    bb_mid   = bb.bollinger_mavg()

    atr = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()

    # ── Support / Resistance zones (swing highs/lows last 20 bars) ────────────
    recent_high = high.iloc[-20:].max()
    recent_low  = low.iloc[-20:].min()

    # ── Current values ────────────────────────────────────────────────────────
    c_price   = close.iloc[-1]
    c_rsi     = rsi.iloc[-1]
    c_atr     = atr.iloc[-1]
    c_ema20   = ema20.iloc[-1]
    c_ema50   = ema50.iloc[-1]
    c_ema200  = ema200.iloc[-1]
    c_macd    = macd_hist.iloc[-1]
    p_macd    = macd_hist.iloc[-2]
    c_bb_low  = bb_lower.iloc[-1]
    c_bb_high = bb_upper.iloc[-1]
    c_bb_mid  = bb_mid.iloc[-1]

    score_buy  = 0
    score_sell = 0

    # ── Trend (EMA alignment) ─────────────────────────────────────────────────
    if c_ema20 > c_ema50 > c_ema200:
        score_buy  += 2
    elif c_ema20 < c_ema50 < c_ema200:
        score_sell += 2

    # ── Price vs EMA20 ────────────────────────────────────────────────────────
    if c_price > c_ema20:
        score_buy  += 1
    else:
        score_sell += 1

    # ── RSI ───────────────────────────────────────────────────────────────────
    if c_rsi < 35:
        score_buy  += 2
    elif c_rsi > 65:
        score_sell += 2
    elif 40 < c_rsi < 60:
        pass   # neutral zone, no score

    # ── MACD crossover ────────────────────────────────────────────────────────
    if p_macd < 0 < c_macd:          # bullish cross
        score_buy  += 3
    elif p_macd > 0 > c_macd:        # bearish cross
        score_sell += 3

    # ── Bollinger Band touch / breakout ───────────────────────────────────────
    if c_price <= c_bb_low * 1.001:
        score_buy  += 2
    elif c_price >= c_bb_high * 0.999:
        score_sell += 2

    # ── Minimum confluence threshold ──────────────────────────────────────────
    THRESHOLD = 5
    if score_buy < THRESHOLD and score_sell < THRESHOLD:
        return None

    direction = "BUY" if score_buy > score_sell else "SELL"
    confidence = max(score_buy, score_sell)
    max_possible = 10
    win_pct = min(95, int(60 + (confidence / max_possible) * 35))

    sl_multiplier = 1.5
    tp_multiplier = 2.5

    if direction == "BUY":
        sl    = round(c_price - c_atr * sl_multiplier, 5)
        tp1   = round(c_price + c_atr * tp_multiplier, 5)
        tp2   = round(c_price + c_atr * tp_multiplier * 1.6, 5)
        zone  = f"Support: {round(recent_low,5)}"
    else:
        sl    = round(c_price + c_atr * sl_multiplier, 5)
        tp1   = round(c_price - c_atr * tp_multiplier, 5)
        tp2   = round(c_price - c_atr * tp_multiplier * 1.6, 5)
        zone  = f"Resistance: {round(recent_high,5)}"

    sl_pips = abs(c_price - sl) / SYMBOLS[symbol]["pip_value"]

    return {
        "symbol":     symbol,
        "direction":  direction,
        "price":      c_price,
        "sl":         sl,
        "tp1":        tp1,
        "tp2":        tp2,
        "sl_pips":    sl_pips,
        "rsi":        round(c_rsi, 1),
        "atr":        round(c_atr, 5),
        "zone":       zone,
        "confidence": confidence,
        "win_pct":    win_pct,
        "ema_trend":  "↑ Bullish" if c_ema20 > c_ema50 else "↓ Bearish",
    }


def build_message(signal: dict) -> str:
    """Format Telegram signal message."""
    info   = SYMBOLS[signal["symbol"]]
    emoji  = "🟢" if signal["direction"] == "BUY" else "🔴"
    now    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"{emoji} *{signal['direction']} SIGNAL — {info['name']} ({signal['symbol']})*",
        f"🕐 `{now}`",
        "",
        f"📍 *Entry:*   `{signal['price']}`",
        f"🛑 *Stop Loss:* `{signal['sl']}`",
        f"🎯 *TP1:*    `{signal['tp1']}`",
        f"🎯 *TP2:*    `{signal['tp2']}`",
        "",
        f"📊 *Trend:* {signal['ema_trend']}",
        f"📈 *RSI:* `{signal['rsi']}`",
        f"📐 *Zone:* {signal['zone']}",
        f"⚡ *Signal Strength:* `{signal['confidence']}/10`",
        f"🏆 *Est. Win Probability:* `{signal['win_pct']}%`",
        "",
        "💼 *Recommended Lot Sizes:*",
    ]

    for acc_name, acc in ACCOUNTS.items():
        lot = calculate_lot_size(
            balance   = acc["balance"],
            risk_pct  = acc["risk_pct"],
            sl_pips   = signal["sl_pips"],
            pip_value = info["pip_value"],
            price     = signal["price"],
        )
        risk_amt = round(acc["balance"] * acc["risk_pct"], 2)
        lines.append(f"  {acc_name}: `{lot} lots`  (risk: ${risk_amt})")

    lines += [
        "",
        "⚠️ _Always verify before executing. Past signals ≠ guaranteed future results._",
    ]
    return "\n".join(lines)


async def run_bot():
    bot = Bot(token=TELEGRAM_TOKEN)
    logger.info("Bot started.")

    # startup message
    await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            "🤖 *Trading Signal Bot is LIVE!*\n\n"
            "Scanning: Gold, Silver, EUR/USD, GBP/USD, USD/JPY, "
            "AUD/USD, USD/CHF, EUR/JPY, GBP/JPY\n"
            f"Scanning every {SCAN_INTERVAL_MINUTES} minutes.\n\n"
            "Waiting for high-confluence signals... 📡"
        ),
        parse_mode=ParseMode.MARKDOWN,
    )

    async with aiohttp.ClientSession() as session:
        while True:
            logger.info("Starting market scan...")
            signals_sent = 0

            for symbol in SYMBOLS:
                try:
                    df = await fetch_ohlcv(session, symbol)
                    signal = analyze(df, symbol)
                    if signal:
                        msg = build_message(signal)
                        await bot.send_message(
                            chat_id=CHAT_ID,
                            text=msg,
                            parse_mode=ParseMode.MARKDOWN,
                        )
                        signals_sent += 1
                        logger.info(f"Signal sent: {symbol} {signal['direction']}")
                        await asyncio.sleep(1)   # avoid Telegram rate limit
                except Exception as e:
                    logger.error(f"Error scanning {symbol}: {e}")

            if signals_sent == 0:
                logger.info("No high-confluence signals this scan. Markets quiet.")

            await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    asyncio.run(run_bot())
