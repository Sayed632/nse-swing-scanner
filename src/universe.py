"""
Universe loader for NSE equity.
Supports Nifty 500 and full mainboard equity list.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Official NSE equity list endpoint (public CSV)
NSE_EQUITY_CSV = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/csv,application/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _download_nse_equity_csv() -> pd.DataFrame:
    """Download the official NSE equity master list."""
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    # Warm-up cookie (NSE sometimes requires it)
    try:
        session.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass

    resp = session.get(NSE_EQUITY_CSV, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(pd.io.common.StringIO(resp.text))
    return df


def get_full_nse_mainboard(exclude_sme: bool = True) -> List[str]:
    """
    Return list of NSE mainboard equity symbols in Yahoo format (SYMBOL.NS).
    Filters out SME / BE / other non-EQ series when exclude_sme=True.
    """
    try:
        df = _download_nse_equity_csv()
    except Exception as e:
        logger.error("Failed to download NSE equity list: %s", e)
        logger.warning("Falling back to a static Nifty-500 style list")
        return _fallback_nifty500()

    # Normalise column names
    df.columns = [c.strip().upper() for c in df.columns]

    # Common column names in EQUITY_L.csv
    symbol_col = None
    for candidate in ("SYMBOL", "SYMBOL ", "SCRIP CODE", "SECURITY"):
        if candidate in df.columns:
            symbol_col = candidate
            break
    if symbol_col is None:
        # Try first column
        symbol_col = df.columns[0]

    series_col = None
    for candidate in ("SERIES", "SERIES "):
        if candidate in df.columns:
            series_col = candidate
            break

    symbols = df[symbol_col].astype(str).str.strip().str.upper()

    if exclude_sme and series_col:
        series = df[series_col].astype(str).str.strip().str.upper()
        # Keep only EQ (and sometimes BE for trade-to-trade)
        mask = series.isin(["EQ", "BE"])
        symbols = symbols[mask]

    # Clean & deduplicate
    symbols = (
        symbols.dropna()
        .loc[lambda s: s.str.len() > 0]
        .loc[lambda s: ~s.str.contains(r"[^A-Z0-9&\-]", regex=True)]
        .drop_duplicates()
        .tolist()
    )

    # Yahoo Finance suffix
    tickers = [f"{s}.NS" for s in symbols]
    logger.info("Loaded %d NSE mainboard symbols", len(tickers))
    return tickers


def get_nifty500() -> List[str]:
    """Convenience wrapper – currently falls back to static list.
    Can be extended later with official Nifty 500 constituents.
    """
    return _fallback_nifty500()


def _fallback_nifty500() -> List[str]:
    """Static liquid universe used when live download fails."""
    return [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS",
        "INFY.NS", "SBIN.NS", "LICI.NS", "ITC.NS", "HINDUNILVR.NS", "LT.NS",
        "BAJFINANCE.NS", "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS", "ADANIENT.NS",
        "TATAMOTORS.NS", "NTPC.NS", "KOTAKBANK.NS", "TITAN.NS", "AXISBANK.NS",
        "ONGC.NS", "ULTRACEMCO.NS", "COALINDIA.NS", "ASIANPAINT.NS", "WIPRO.NS",
        "BAJAJFINSV.NS", "JSWSTEEL.NS", "M&M.NS", "POWERGRID.NS", "TATASTEEL.NS",
        "ADANIPORTS.NS", "GRASIM.NS", "SBILIFE.NS", "BPCL.NS", "HINDALCO.NS",
        "BAJAJ-AUTO.NS", "CIPLA.NS", "EICHERMOT.NS", "BRITANNIA.NS", "NESTLEIND.NS",
        "DRREDDY.NS", "APOLLOHOSP.NS", "TATACONSUM.NS", "DIVISLAB.NS", "TECHM.NS",
        "INDUSINDBK.NS", "IOC.NS", "HDFCLIFE.NS", "HEROMOTOCO.NS", "TATAPOWER.NS",
        "PIDILITIND.NS", "SIEMENS.NS", "DLF.NS", "HAVELLS.NS", "GODREJCP.NS",
        "AMBUJACEM.NS", "SHREECEM.NS", "DABUR.NS", "VEDL.NS", "INDIGO.NS",
        "BANKBARODA.NS", "PNB.NS", "CANBK.NS", "UNIONBANK.NS", "IDFCFIRSTB.NS",
        "CHOLAFIN.NS", "MUTHOOTFIN.NS", "RECLTD.NS", "PFC.NS", "IRFC.NS",
        "NMDC.NS", "SAIL.NS", "JINDALSTEL.NS", "HINDCOPPER.NS", "NATIONALUM.NS",
        "BHEL.NS", "BEL.NS", "HAL.NS", "COFORGE.NS", "PERSISTENT.NS",
        "LTIM.NS", "MPHASIS.NS", "OFSS.NS", "TATAELXSI.NS", "ZOMATO.NS",
        "PAYTM.NS", "NYKAA.NS", "POLICYBZR.NS", "DMART.NS", "TRENT.NS",
        "PAGEIND.NS", "ABBOTINDIA.NS", "ALKEM.NS", "AUROPHARMA.NS", "BIOCON.NS",
        "GLENMARK.NS", "LUPIN.NS", "TORNTPHARM.NS", "ZYDUSLIFE.NS", "LAURUSLABS.NS",
    ]


def load_universe(mode: str = "full_nse", exclude_sme: bool = True) -> List[str]:
    """Main entry point used by the scanner."""
    mode = (mode or "full_nse").lower().strip()
    if mode in ("full_nse", "full", "nse", "all"):
        return get_full_nse_mainboard(exclude_sme=exclude_sme)
    if mode in ("nifty500", "nifty_500", "500"):
        return get_nifty500()
    logger.warning("Unknown universe mode '%s' – using full_nse", mode)
    return get_full_nse_mainboard(exclude_sme=exclude_sme)
