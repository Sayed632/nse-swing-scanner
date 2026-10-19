"""
Core parallel swing scanner.
"""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from rich.console import Console
from rich.table import Table

from .data import download_batch
from .indicators import compute_indicators, detect_swing_signals
from .universe import load_universe

logger = logging.getLogger(__name__)
console = Console()


def _analyse_one(args: tuple) -> Optional[Dict[str, Any]]:
    """
    Worker function – must be top-level for ProcessPoolExecutor on Windows.
    args = (ticker, df, indicator_cfg, scan_cfg)
    """
    ticker, df, indicator_cfg, scan_cfg = args
    try:
        df = compute_indicators(df, indicator_cfg)
        signal = detect_swing_signals(df, {**indicator_cfg, **scan_cfg})
        if not signal.get("qualified"):
            return None

        return {
            "ticker": ticker.replace(".NS", ""),
            "price": signal["entry"],
            "score": signal["score"],
            "signals": ", ".join(signal["signals"]),
            "signal_count": signal["signal_count"],
            "stop": signal["stop"],
            "target1": signal["target1"],
            "target2": signal["target2"],
            "rr1": signal["rr1"],
            "rr2": signal["rr2"],
            "rsi": signal["details"].get("rsi"),
            "vol_ratio": signal["details"].get("vol_ratio"),
            "pct_from_52w": signal["details"].get("pct_from_52w_high"),
        }
    except Exception as e:
        logger.debug("Analyse failed for %s: %s", ticker, e)
        return None


def run_scan(cfg: Dict[str, Any]) -> pd.DataFrame:
    """
    Full pipeline:
    1. Load universe
    2. Download / cache OHLCV in parallel
    3. Analyse each ticker for swing setups
    4. Rank and return top results
    """
    uni_cfg = cfg.get("universe", {})
    scan_cfg = cfg.get("scan", {})
    ind_cfg = cfg.get("indicators", {})
    out_cfg = cfg.get("output", {})
    risk_cfg = cfg.get("risk", {})

    # Merge risk into scan for the detector
    scan_cfg = {**scan_cfg, "risk": risk_cfg, "weights": cfg.get("weights", {})}

    mode = uni_cfg.get("mode", "full_nse")
    exclude_sme = bool(uni_cfg.get("exclude_sme", True))
    min_vol = float(uni_cfg.get("min_avg_volume", 50000))
    min_price = float(uni_cfg.get("min_price", 30.0))
    max_price = uni_cfg.get("max_price")

    console.print(f"[bold cyan]Loading universe[/] (mode={mode}) ...")
    tickers = load_universe(mode=mode, exclude_sme=exclude_sme)
    console.print(f"  → {len(tickers)} symbols loaded")

    cache_dir = Path(out_cfg.get("cache_dir", "cache"))
    period = scan_cfg.get("history_period", "6mo")
    max_workers = int(scan_cfg.get("max_workers", 12))
    batch_delay = float(scan_cfg.get("batch_delay", 1.5))
    cache_hours = float(out_cfg.get("cache_hours", 6))

    data_map = download_batch(
        tickers=tickers,
        period=period,
        cache_dir=cache_dir,
        cache_hours=cache_hours,
        max_workers=max_workers,
        batch_delay=batch_delay,
    )

    # Liquidity / price pre-filter
    filtered = {}
    for t, df in data_map.items():
        try:
            last_close = float(df["Close"].iloc[-1])
            avg_vol = float(df["Volume"].tail(20).mean())
            if last_close < min_price:
                continue
            if max_price is not None and last_close > float(max_price):
                continue
            if avg_vol < min_vol:
                continue
            filtered[t] = df
        except Exception:
            continue

    console.print(f"[bold cyan]Analysing[/] {len(filtered)} liquid names ...")

    # Prepare worker args
    worker_args = [
        (t, df, ind_cfg, scan_cfg) for t, df in filtered.items()
    ]

    results: List[Dict[str, Any]] = []
    # ProcessPool can be heavy; ThreadPool is safer for yfinance + many cores
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_analyse_one, arg) for arg in worker_args]
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                results.append(res)

    if not results:
        console.print("[yellow]No swing setups matched the current criteria.[/]")
        return pd.DataFrame()

    df_out = pd.DataFrame(results)
    df_out = df_out.sort_values("score", ascending=False).reset_index(drop=True)

    top_n = int(out_cfg.get("top_n", 30))
    df_out = df_out.head(top_n)

    # Pretty table
    table = Table(title="NSE Swing Setups – Ranked", show_lines=False)
    table.add_column("Rank", justify="right", style="dim")
    table.add_column("Ticker", style="bold cyan")
    table.add_column("Price", justify="right")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Signals")
    table.add_column("Stop", justify="right")
    table.add_column("T1", justify="right")
    table.add_column("RR1", justify="right")
    table.add_column("RSI", justify="right")

    for i, row in df_out.iterrows():
        table.add_row(
            str(i + 1),
            row["ticker"],
            f"₹{row['price']:.1f}",
            f"{row['score']:.1f}",
            row["signals"][:40],
            f"{row['stop']:.1f}",
            f"{row['target1']:.1f}",
            f"{row['rr1']:.1f}",
            f"{row['rsi']:.0f}" if pd.notna(row["rsi"]) else "-",
        )

    console.print(table)
    return df_out
