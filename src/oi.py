"""
F&O Open Interest + PCR + Buildup analysis.
Uses nsepython for option-chain data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Common liquid F&O equity symbols (Yahoo-style without .NS)
# This list is curated for reliability; can be expanded later.
FNO_EQUITY_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN", "BHARTIARTL",
    "ITC", "LT", "HINDUNILVR", "BAJFINANCE", "HCLTECH", "MARUTI", "SUNPHARMA",
    "TATAMOTORS", "NTPC", "KOTAKBANK", "TITAN", "AXISBANK", "ONGC",
    "ULTRACEMCO", "COALINDIA", "ASIANPAINT", "WIPRO", "BAJAJFINSV", "JSWSTEEL",
    "M&M", "POWERGRID", "TATASTEEL", "ADANIPORTS", "ADANIENT", "GRASIM",
    "SBILIFE", "BPCL", "HINDALCO", "BAJAJ-AUTO", "CIPLA", "EICHERMOT",
    "BRITANNIA", "NESTLEIND", "DRREDDY", "APOLLOHOSP", "TATACONSUM", "DIVISLAB",
    "TECHM", "INDUSINDBK", "IOC", "HDFCLIFE", "HEROMOTOCO", "TATAPOWER",
    "PIDILITIND", "SIEMENS", "DLF", "HAVELLS", "GODREJCP", "AMBUJACEM",
    "DABUR", "VEDL", "INDIGO", "BANKBARODA", "PNB", "CANBK", "CHOLAFIN",
    "MUTHOOTFIN", "RECLTD", "PFC", "IRFC", "NMDC", "SAIL", "JINDALSTEL",
    "BHEL", "BEL", "HAL", "COFORGE", "PERSISTENT", "LTIM", "MPHASIS",
    "ZOMATO", "TRENT", "PAGEIND", "ALKEM", "AUROPHARMA", "BIOCON",
    "GLENMARK", "LUPIN", "TORNTPHARM", "ZYDUSLIFE", "LAURUSLABS",
    "HDFCAMC", "ICICIGI", "ICICIPRULI", "SBICARD", "FEDERALBNK",
    "IDFCFIRSTB", "AUBANK", "BANDHANBNK", "RBLBANK", "YESBANK",
]


def get_fno_symbols() -> List[str]:
    """Return F&O equity symbols in Yahoo format (SYMBOL.NS)."""
    return [f"{s}.NS" for s in FNO_EQUITY_SYMBOLS]


def _safe_pcr(payload: dict) -> Optional[float]:
    """Calculate Put-Call Ratio from option-chain payload."""
    try:
        from nsepython import pcr
        # pcr(payload, inp=0) → current expiry
        val = pcr(payload, 0)
        if val is None or val == 0:
            return None
        return round(float(val), 3)
    except Exception:
        # Manual fallback
        try:
            records = payload.get("records", {}).get("data", [])
            ce_oi = pe_oi = 0
            for row in records:
                ce = row.get("CE") or {}
                pe = row.get("PE") or {}
                ce_oi += int(ce.get("openInterest", 0) or 0)
                pe_oi += int(pe.get("openInterest", 0) or 0)
            if ce_oi == 0:
                return None
            return round(pe_oi / ce_oi, 3)
        except Exception:
            return None


def _classify_buildup(price_chg_pct: float, oi_chg: float) -> str:
    """
    Classic 4-quadrant OI buildup classification.
    price_chg_pct : % change in underlying (positive = up)
    oi_chg        : absolute change in total OI (positive = increase)
    """
    if price_chg_pct > 0.15 and oi_chg > 0:
        return "Long Buildup"
    if price_chg_pct > 0.15 and oi_chg < 0:
        return "Short Covering"
    if price_chg_pct < -0.15 and oi_chg > 0:
        return "Short Buildup"
    if price_chg_pct < -0.15 and oi_chg < 0:
        return "Long Unwinding"
    return "Neutral / Sideways"


def fetch_oi_snapshot(symbol: str) -> Dict[str, Any]:
    """
    Fetch OI + PCR + Buildup for one F&O symbol.
    symbol should be clean (e.g. "RELIANCE", not "RELIANCE.NS")
    """
    result = {
        "symbol": symbol,
        "pcr": None,
        "total_ce_oi": None,
        "total_pe_oi": None,
        "oi_change": None,
        "buildup": "N/A",
        "underlying": None,
        "ok": False,
        "error": None,
    }

    try:
        from nsepython import nse_optionchain_scrapper, oi_chain_builder

        clean = symbol.replace(".NS", "").replace(".ns", "").upper()
        payload = nse_optionchain_scrapper(clean)
        if not payload:
            result["error"] = "empty payload"
            return result

        # PCR
        result["pcr"] = _safe_pcr(payload)

        # Underlying & total OI via oi_chain_builder
        try:
            df, underlying, _ts = oi_chain_builder(clean, expiry="latest", oi_mode="full")
            result["underlying"] = float(underlying) if underlying else None

            if df is not None and not df.empty:
                # Column names can vary slightly
                ce_col = next((c for c in df.columns if "CALLS_OI" in c or c == "CALLS_OI"), None)
                pe_col = next((c for c in df.columns if "PUTS_OI" in c or c == "PUTS_OI"), None)
                ce_chg = next((c for c in df.columns if "CALLS_Chng" in c), None)
                pe_chg = next((c for c in df.columns if "PUTS_Chng" in c), None)

                if ce_col and pe_col:
                    total_ce = int(df[ce_col].sum())
                    total_pe = int(df[pe_col].sum())
                    result["total_ce_oi"] = total_ce
                    result["total_pe_oi"] = total_pe

                    oi_change = 0
                    if ce_chg and pe_chg:
                        oi_change = int(df[ce_chg].sum() + df[pe_chg].sum())
                    result["oi_change"] = oi_change

                    # Approximate price change from underlying vs previous close if available
                    # For simplicity we use a neutral bias if we cannot get exact % change
                    # Caller can pass price_chg_pct for better classification
        except Exception as e:
            logger.debug("oi_chain_builder failed for %s: %s", clean, e)

        result["ok"] = True
        return result

    except Exception as e:
        result["error"] = str(e)[:120]
        logger.debug("OI fetch failed for %s: %s", symbol, e)
        return result


def analyse_fno_stock(
    symbol: str,
    price_chg_pct: float = 0.0,
) -> Dict[str, Any]:
    """
    Full F&O analysis for one stock.
    Returns PCR, buildup label, and a simple conviction score (0-100).
    """
    snap = fetch_oi_snapshot(symbol)
    if not snap.get("ok"):
        return {
            "symbol": symbol.replace(".NS", ""),
            "pcr": None,
            "buildup": "N/A",
            "oi_score": 0,
            "oi_ok": False,
            "error": snap.get("error"),
        }

    pcr = snap.get("pcr")
    oi_chg = snap.get("oi_change") or 0
    buildup = _classify_buildup(price_chg_pct, oi_chg)

    # Simple OI conviction score
    score = 40  # base
    if buildup == "Long Buildup":
        score += 35
    elif buildup == "Short Covering":
        score += 20
    elif buildup == "Short Buildup":
        score -= 25
    elif buildup == "Long Unwinding":
        score -= 15

    if pcr is not None:
        if pcr < 0.7:          # call-heavy → bullish
            score += 15
        elif pcr > 1.3:        # put-heavy → cautious / bearish
            score -= 10

    score = max(0, min(100, score))

    return {
        "symbol": symbol.replace(".NS", ""),
        "pcr": pcr,
        "buildup": buildup,
        "oi_change": oi_chg,
        "total_ce_oi": snap.get("total_ce_oi"),
        "total_pe_oi": snap.get("total_pe_oi"),
        "underlying": snap.get("underlying"),
        "oi_score": score,
        "oi_ok": True,
    }
