# NSE Swing Scanner

**Parallel swing / daily scanner for NSE with optional F&O Open Interest + PCR.**

- `full_nse` or `nifty500` → pure technical swing setups  
- **`fno`** (recommended for daily trading) → technical confluence **+** OI Buildup + PCR

This is a **separate project** from `nse-live-scanner`. Keep both.

---

## Features

- Universes: `full_nse` | `nifty500` | **`fno`**
- Parallel download + analysis + parquet cache
- Classic swing confluence (EMA stack, RSI recovery, MACD, volume, near 52w high)
- **F&O layer** (when mode = fno):
  - Put-Call Ratio (PCR)
  - OI Buildup: Long Buildup / Short Covering / Short Buildup / Long Unwinding
  - OI conviction score that boosts or filters setups
- ATR-based entry / stop / targets
- CSV + rich table output
- GitHub Actions ready

---

## Quick Start

```bash
git clone https://github.com/Sayed632/nse-swing-scanner.git
cd nse-swing-scanner

python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate

pip install -r requirements.txt

# F&O mode (Technical + OI + PCR) – best for daily trading
python main.py --universe fno --workers 8 --top 20

# Pure swing on Nifty 500
python main.py --universe nifty500 --workers 12 --top 25
```

Results are saved under `results/`.

---

## Configuration (`config.yaml`)

| Key | Meaning |
|-----|---------|
| `universe.mode` | `fno` / `nifty500` / `full_nse` |
| `oi.enabled` | Turn OI + PCR layer on/off |
| `oi.min_oi_score` | Minimum OI conviction to keep a setup |
| `oi.long_buildup_bonus` | Extra points when Long Buildup is detected |
| `scan.max_workers` | Parallelism |
| `scan.min_signals` | Minimum technical confluence factors |

---

## OI Buildup (quick reference)

| Price | OI Change | Label | Bias |
|-------|-----------|-------|------|
| ↑ | ↑ | **Long Buildup** | Strong Bullish |
| ↑ | ↓ | **Short Covering** | Bullish |
| ↓ | ↑ | **Short Buildup** | Strong Bearish |
| ↓ | ↓ | **Long Unwinding** | Bearish |

PCR = Put OI ÷ Call OI  
- Low PCR (< 0.7) → more calls → bullish lean  
- High PCR (> 1.3) → more puts → cautious / bearish lean

---

## Project layout

```
nse-swing-scanner/
├── main.py
├── config.yaml
├── requirements.txt
├── src/
│   ├── universe.py
│   ├── data.py
│   ├── indicators.py
│   ├── oi.py          ← F&O OI + PCR + Buildup
│   └── scanner.py
├── cache/
└── results/
```

---

## Notes

- OI data comes from NSE via `nsepython`. It works best during market hours.
- First run downloads data and is slower; later runs use cache.
- This is **not** financial advice. Always manage your own risk.

## License

MIT
