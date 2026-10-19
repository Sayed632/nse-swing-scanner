# NSE Swing Scanner

**Parallel swing-trade scanner for the full NSE mainboard equity universe (~2,100–2,200 names).**

Scans daily charts in parallel, applies multi-factor technical confluence, ranks setups by a transparent score, and outputs entry / stop / target levels based on ATR.

This is a **separate, clean project** from the existing `nse-live-scanner` (live momentum + sentiment bot). Keep both if you want live intraday alerts **and** end-of-day swing ideas.

---

## Features

- **Full NSE mainboard** universe (EQ + BE series) pulled live from NSE archives, or Nifty 500
- Parallel download + analysis (`ThreadPoolExecutor` + caching)
- Classic swing confluence:
  - Price > EMA 200
  - EMA 20 > EMA 50 alignment
  - RSI recovery from oversold zone
  - MACD histogram turning up
  - Volume surge on green day
  - Proximity to 52-week high
- ATR-based stop / target suggestions + risk-reward filter
- Configurable scoring weights
- CSV output + rich terminal table
- Optional Telegram (disabled by default)
- GitHub Actions ready (optional)

---

## Quick Start

```bash
# 1. Clone / create the repo
git clone https://github.com/YOUR_USERNAME/nse-swing-scanner.git
cd nse-swing-scanner

# 2. Virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# 3. Install
pip install -r requirements.txt

# 4. Run (full NSE mainboard)
python main.py

# Or Nifty 500 only (faster)
python main.py --universe nifty500 --workers 16 --top 25
```

Results are saved under `results/swing_setups_YYYYMMDD_HHMM.csv`.

---

## Configuration

Edit `config.yaml`:

| Section | Key settings |
|---------|--------------|
| `universe.mode` | `"full_nse"` or `"nifty500"` |
| `universe.min_avg_volume` | Liquidity filter (default 50 000) |
| `universe.min_price` | Ignore very cheap stocks |
| `scan.max_workers` | Parallelism (8–16 typical) |
| `scan.min_signals` | How many confluence factors required |
| `indicators.*` | EMA / RSI / MACD / ATR periods |
| `weights.*` | Score component weights |
| `risk.*` | ATR multipliers for stop & targets |

---

## How the score works (0–100)

| Component | Weight | What it measures |
|-----------|--------|------------------|
| Signal count | 30 % | Number of active confluence signals |
| Trend strength | 25 % | Full EMA stack quality |
| Volume | 15 % | Relative volume vs 20-day average |
| RSI position | 15 % | Ideal swing zone (≈45–65) |
| Risk-reward | 15 % | Quality of ATR-based R:R |

Only stocks that clear the hard filters (above EMA 200 + minimum signal count + liquidity) are scored.

---

## Project layout

```
nse-swing-scanner/
├── main.py                 # CLI entry point
├── config.yaml             # All tunables
├── requirements.txt
├── README.md
├── src/
│   ├── universe.py         # NSE list loader
│   ├── data.py             # Download + parquet cache
│   ├── indicators.py       # EMA/RSI/MACD/ATR + signal logic
│   └── scanner.py          # Orchestration + ranking
├── cache/                  # OHLCV parquet files (gitignored)
└── results/                # Dated CSV outputs
```

---

## Notes & Limitations

- Data source is Yahoo Finance (`yfinance`). It is free but rate-limited; the scanner uses batching + cache to stay polite.
- Full mainboard scan of ~2,000 names typically takes 4–12 minutes depending on workers, cache hit rate and network.
- This is **not** financial advice. Swing setups can fail. Always apply your own risk management and position sizing.
- SME / Emerge stocks are excluded by default for liquidity reasons.

---

## Next possible upgrades

- Weekly bias filter
- Relative strength vs Nifty
- Telegram / Discord alerts
- Simple back-test module
- Streamlit dashboard

---

## License

MIT – use freely, improve, and share.
