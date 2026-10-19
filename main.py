#!/usr/bin/env python3
"""
NSE Swing Scanner – CLI entry point
===================================
Scans the full NSE mainboard (or Nifty 500) in parallel and surfaces
high-quality swing-trade setups.

Usage:
    python main.py
    python main.py --universe nifty500
    python main.py --workers 16 --top 20
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml
from rich.console import Console
from rich.logging import RichHandler

from src.scanner import run_scan

console = Console()


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="NSE Parallel Swing Scanner")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--universe", choices=["full_nse", "nifty500"], help="Override universe")
    parser.add_argument("--workers", type=int, help="Override max parallel workers")
    parser.add_argument("--top", type=int, help="Override top N results")
    parser.add_argument("--no-cache", action="store_true", help="Ignore existing cache")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.get("logging", {}).get("level", "INFO"))

    if args.universe:
        cfg.setdefault("universe", {})["mode"] = args.universe
    if args.workers:
        cfg.setdefault("scan", {})["max_workers"] = args.workers
    if args.top:
        cfg.setdefault("output", {})["top_n"] = args.top
    if args.no_cache:
        cfg.setdefault("output", {})["cache_hours"] = 0

    console.rule("[bold green]NSE Swing Scanner")
    console.print(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"Universe mode : {cfg.get('universe', {}).get('mode')}")
    console.print(f"Workers       : {cfg.get('scan', {}).get('max_workers')}")
    console.print()

    try:
        df = run_scan(cfg)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/]")
        return 130
    except Exception as e:
        console.print(f"[bold red]Fatal error:[/] {e}")
        logging.exception("Scan failed")
        return 1

    # Save results
    out_cfg = cfg.get("output", {})
    if out_cfg.get("save_csv", True) and not df.empty:
        results_dir = Path(out_cfg.get("results_dir", "results"))
        results_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        path = results_dir / f"swing_setups_{stamp}.csv"
        df.to_csv(path, index=False)
        console.print(f"\n[green]Saved[/] {len(df)} setups → {path}")

    console.rule("[bold green]Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
