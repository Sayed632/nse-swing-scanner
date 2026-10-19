"""
Technical indicator computation and swing signal detection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
except ImportError:
    ta = None


def compute_indicators(df: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    """
    Add EMA, RSI, MACD, ATR, volume SMA columns to an OHLCV DataFrame.
    Expects columns: Open, High, Low, Close, Volume
    """
    if df is None or df.empty or len(df) < 30:
        return df

    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    ema_s = cfg.get("ema_short", 20)
    ema_m = cfg.get("ema_mid", 50)
    ema_l = cfg.get("ema_long", 200)
    rsi_p = cfg.get("rsi_period", 14)
    atr_p = cfg.get("atr_period", 14)
    vol_p = cfg.get("volume_sma", 20)
    macd_f = cfg.get("macd_fast", 12)
    macd_s = cfg.get("macd_slow", 26)
    macd_sig = cfg.get("macd_signal", 9)

    # EMAs
    df["EMA_20"] = close.ewm(span=ema_s, adjust=False).mean()
    df["EMA_50"] = close.ewm(span=ema_m, adjust=False).mean()
    df["EMA_200"] = close.ewm(span=ema_l, adjust=False).mean()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / rsi_p, min_periods=rsi_p, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_p, min_periods=rsi_p, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema_fast = close.ewm(span=macd_f, adjust=False).mean()
    ema_slow = close.ewm(span=macd_s, adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_Signal"] = df["MACD"].ewm(span=macd_sig, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    # ATR
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(alpha=1 / atr_p, min_periods=atr_p, adjust=False).mean()

    # Volume SMA
    df["Vol_SMA"] = volume.rolling(vol_p, min_periods=1).mean()

    # 52-week high / low (approx with available history)
    df["High_52w"] = high.rolling(window=min(252, len(df)), min_periods=20).max()
    df["Low_52w"] = low.rolling(window=min(252, len(df)), min_periods=20).min()

    return df


def detect_swing_signals(df: pd.DataFrame, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate classic swing-trade confluence on the latest bar.
    Returns a dict with boolean signals, score components and suggested levels.
    """
    result = {
        "qualified": False,
        "signals": [],
        "signal_count": 0,
        "score": 0.0,
        "entry": None,
        "stop": None,
        "target1": None,
        "target2": None,
        "rr1": None,
        "rr2": None,
        "details": {},
    }

    if df is None or len(df) < 50:
        return result

    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else row

    close = float(row["Close"])
    ema20 = float(row.get("EMA_20", np.nan))
    ema50 = float(row.get("EMA_50", np.nan))
    ema200 = float(row.get("EMA_200", np.nan))
    rsi = float(row.get("RSI", np.nan))
    atr = float(row.get("ATR", np.nan))
    vol = float(row.get("Volume", 0))
    vol_sma = float(row.get("Vol_SMA", 1))
    macd_hist = float(row.get("MACD_Hist", 0))
    prev_macd_hist = float(prev.get("MACD_Hist", 0))
    high_52w = float(row.get("High_52w", np.nan))

    if any(np.isnan(x) for x in (ema20, ema50, ema200, rsi, atr)):
        return result

    signals: List[str] = []

    # 1. Trend filter – price above long-term EMA
    above_200 = close > ema200
    result["details"]["above_ema200"] = above_200

    # 2. EMA alignment / stack
    ema_aligned = close > ema20 > ema50
    if ema_aligned:
        signals.append("EMA_ALIGN")
    result["details"]["ema_aligned"] = ema_aligned

    # 3. RSI recovery (was oversold-ish recently, now rising in healthy zone)
    rsi_recent = df["RSI"].iloc[-6:-1]
    was_oversold = (rsi_recent <= 42).any()
    rsi_rising = rsi > float(prev.get("RSI", rsi)) and 40 <= rsi <= 68
    if was_oversold and rsi_rising:
        signals.append("RSI_RECOVERY")
    result["details"]["rsi"] = round(rsi, 1)

    # 4. MACD histogram turning positive / crossover
    macd_cross = macd_hist > 0 and prev_macd_hist <= 0
    macd_positive = macd_hist > 0
    if macd_cross or (macd_positive and macd_hist > prev_macd_hist):
        signals.append("MACD_UP")
    result["details"]["macd_hist"] = round(macd_hist, 3)

    # 5. Volume surge on green day
    vol_ratio = vol / vol_sma if vol_sma > 0 else 1.0
    green = close > float(row.get("Open", close))
    if vol_ratio >= 1.5 and green:
        signals.append("VOLUME_SURGE")
    result["details"]["vol_ratio"] = round(vol_ratio, 2)

    # 6. Near 52-week high (momentum leaders)
    if not np.isnan(high_52w) and high_52w > 0:
        pct_from_high = (high_52w - close) / high_52w * 100
        near_high = pct_from_high <= 12.0
        if near_high and above_200:
            signals.append("NEAR_52W_HIGH")
        result["details"]["pct_from_52w_high"] = round(pct_from_high, 1)

    # Hard filter: must be above EMA200 for long swing
    if not above_200:
        result["signals"] = signals
        result["signal_count"] = len(signals)
        return result

    min_signals = int(cfg.get("min_signals", 2))
    result["signals"] = signals
    result["signal_count"] = len(signals)
    result["qualified"] = len(signals) >= min_signals

    # Suggested trade levels (ATR-based)
    risk_cfg = cfg.get("risk", {})
    sl_mult = float(risk_cfg.get("atr_sl_multiplier", 1.5))
    t1_mult = float(risk_cfg.get("atr_t1_multiplier", 2.0))
    t2_mult = float(risk_cfg.get("atr_t2_multiplier", 3.5))

    entry = close
    stop = entry - sl_mult * atr
    t1 = entry + t1_mult * atr
    t2 = entry + t2_mult * atr
    risk = entry - stop
    rr1 = (t1 - entry) / risk if risk > 0 else 0
    rr2 = (t2 - entry) / risk if risk > 0 else 0

    result.update({
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target1": round(t1, 2),
        "target2": round(t2, 2),
        "rr1": round(rr1, 2),
        "rr2": round(rr2, 2),
        "atr": round(atr, 2),
    })

    # Simple composite score (0–100)
    weights = cfg.get("weights", {})
    w_sig = float(weights.get("signal_count", 0.30))
    w_trend = float(weights.get("trend_strength", 0.25))
    w_vol = float(weights.get("volume", 0.15))
    w_rsi = float(weights.get("rsi_position", 0.15))
    w_rr = float(weights.get("risk_reward", 0.15))

    # Signal count component (max 5 signals → 100)
    sig_score = min(len(signals) / 5.0, 1.0) * 100

    # Trend strength: full stack gets higher
    trend_score = 0.0
    if close > ema20 > ema50 > ema200:
        trend_score = 100.0
    elif close > ema20 > ema50:
        trend_score = 70.0
    elif close > ema200:
        trend_score = 40.0

    # Volume
    vol_score = min(vol_ratio / 3.0, 1.0) * 100

    # RSI sweet spot (45–65 ideal for swing continuation)
    if 45 <= rsi <= 65:
        rsi_score = 100.0
    elif 40 <= rsi < 45 or 65 < rsi <= 70:
        rsi_score = 70.0
    else:
        rsi_score = 30.0

    # Risk-reward
    rr_score = min(rr1 / 3.0, 1.0) * 100

    composite = (
        w_sig * sig_score
        + w_trend * trend_score
        + w_vol * vol_score
        + w_rsi * rsi_score
        + w_rr * rr_score
    )
    result["score"] = round(composite, 1)

    return result
