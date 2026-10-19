"""
OHLCV download + simple file cache.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


def _cache_path(cache_dir: Path, ticker: str) -> Path:
    safe = ticker.replace(".", "_").replace("/", "_")
    return cache_dir / f"{safe}.parquet"


def is_cache_fresh(path: Path, max_age_hours: float) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(hours=max_age_hours)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def download_one(ticker: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """Download daily OHLCV for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="1d", auto_adjust=True)
        if df is None or df.empty:
            return None
        # Standardise columns
        df = df.rename(columns=str.title)
        needed = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in df.columns for c in needed):
            return None
        df = df[needed].dropna(how="any")
        if len(df) < 40:
            return None
        return df
    except Exception as e:
        logger.debug("Download failed for %s: %s", ticker, e)
        return None


def load_or_download(
    ticker: str,
    period: str,
    cache_dir: Path,
    cache_hours: float = 6.0,
) -> Optional[pd.DataFrame]:
    """Return cached data if fresh, otherwise download and cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, ticker)

    if is_cache_fresh(path, cache_hours):
        try:
            df = pd.read_parquet(path)
            if len(df) >= 40:
                return df
        except Exception:
            pass

    df = download_one(ticker, period=period)
    if df is not None:
        try:
            df.to_parquet(path)
        except Exception as e:
            logger.debug("Cache write failed for %s: %s", ticker, e)
    return df


def download_batch(
    tickers: List[str],
    period: str,
    cache_dir: Path,
    cache_hours: float,
    max_workers: int = 8,
    batch_delay: float = 1.0,
) -> Dict[str, pd.DataFrame]:
    """
    Parallel download with simple sequential batching to respect rate limits.
    Returns {ticker: DataFrame}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: Dict[str, pd.DataFrame] = {}
    total = len(tickers)
    logger.info("Downloading / loading cache for %d tickers (workers=%d) ...", total, max_workers)

    # Process in chunks to avoid overwhelming Yahoo
    chunk_size = max(20, max_workers * 3)
    for start in range(0, total, chunk_size):
        chunk = tickers[start : start + chunk_size]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(load_or_download, t, period, cache_dir, cache_hours): t
                for t in chunk
            }
            for fut in as_completed(futures):
                ticker = futures[fut]
                try:
                    df = fut.result()
                    if df is not None and not df.empty:
                        results[ticker] = df
                except Exception as e:
                    logger.debug("Worker error on %s: %s", ticker, e)

        done = min(start + chunk_size, total)
        logger.info("Progress: %d / %d tickers loaded", done, total)
        if start + chunk_size < total and batch_delay > 0:
            time.sleep(batch_delay)

    logger.info("Successfully loaded data for %d / %d tickers", len(results), total)
    return results
