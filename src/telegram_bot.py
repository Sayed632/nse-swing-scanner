"""
Telegram alert helper for NSE Swing Scanner.
Uses TELEGRAM_TOKEN and TELEGRAM_CHAT_ID from environment / GitHub secrets.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)


def _get_credentials() -> tuple[Optional[str], Optional[str]]:
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    return token, chat_id


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a plain text / Markdown message. Returns True on success."""
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        logger.warning("Telegram credentials missing – skipping send")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram hard limit ~4096 characters
    if len(text) > 4000:
        text = text[:3950] + "\n\n_…truncated_"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            logger.info("Telegram message sent successfully")
            return True
        logger.error("Telegram API error %s: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return False


def format_and_send(df: pd.DataFrame, mode: str = "fno", top_n: int = 12) -> bool:
    """
    Build a clean Telegram report from the scan DataFrame and send it.
    """
    if df is None or df.empty:
        return send_message(
            "📊 *NSE Scanner Report*\n\n"
            "No setups matched the filters today."
        )

    df = df.head(top_n).copy()
    now = pd.Timestamp.now().strftime("%d %b %Y %H:%M")

    header = (
        f"📊 *NSE F&O Daily Scanner*\n"
        f"🕐 `{now}` | Mode: `{mode.upper()}`\n"
        f"Top {len(df)} setups (Technical + OI)\n"
        f"{'─' * 28}\n"
    )

    lines = []
    for i, row in df.iterrows():
        ticker = row.get("ticker", "?")
        price = row.get("price", 0)
        score = row.get("score", 0)
        buildup = row.get("buildup", "N/A")
        pcr = row.get("pcr")
        stop = row.get("stop")
        t1 = row.get("target1")
        signals = str(row.get("signals", ""))[:35]

        pcr_str = f"{pcr:.2f}" if pcr is not None and pd.notna(pcr) else "-"
        stop_str = f"{stop:.1f}" if stop is not None else "-"
        t1_str = f"{t1:.1f}" if t1 is not None else "-"

        # Emoji by buildup
        if buildup == "Long Buildup":
            emoji = "🟢"
        elif buildup == "Short Covering":
            emoji = "🟡"
        elif buildup == "Short Buildup":
            emoji = "🔴"
        else:
            emoji = "⚪"

        block = (
            f"{emoji} *{ticker}*  ₹{price:.1f}  | Score `{score:.0f}`\n"
            f"   {buildup} | PCR `{pcr_str}`\n"
            f"   SL `{stop_str}` → T1 `{t1_str}`\n"
            f"   _{signals}_\n"
        )
        lines.append(block)

    footer = (
        f"\n{'─' * 28}\n"
        f"_Not financial advice. Manage your own risk._"
    )

    message = header + "\n".join(lines) + footer
    return send_message(message)
