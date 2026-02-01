#!/usr/bin/env python3
"""Check RSI alerts and send LINE notifications at scheduled times."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple
import argparse

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.alerts import load_alerts
from app.clients.price_service import PriceService
from app.config import get_config
from app.market_data import compute_rsi
from app.notifier import LineMessagingNotifier


def main() -> None:
    parser = argparse.ArgumentParser(description="Send LINE RSI alerts.")
    parser.add_argument("--force", action="store_true", help="Send regardless of current time")
    args = parser.parse_args()

    config = get_config()
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    if not args.force and now.hour not in {12, 15}:
        print(f"[INFO] Current JST hour {now.hour} is not a notification window.")
        return

    if not config.line_channel_access_token or not config.line_target_user_id:
        print("[WARN] LINE credentials are not configured. Skipping notifications.")
        return

    alerts = [alert for alert in load_alerts() if alert.get("type") == "RSI"]
    if not alerts:
        print("[INFO] No RSI alerts registered.")
        return

    ticker_stats = _collect_rsi_stats(alerts, config.price_provider)
    if not ticker_stats:
        print("[WARN] No price/RSI data available. Skipping notifications.")
        return

    notifier = LineMessagingNotifier(
        config.line_channel_access_token,
        config.line_target_user_id,
    )

    for alert in alerts:
        ticker = alert.get("ticker")
        stats = ticker_stats.get(ticker)
        if not stats:
            continue
        rsi_value, price = stats
        threshold = float(alert.get("threshold", 0))
        if pd.isna(rsi_value) or rsi_value > threshold:
            continue
        message = _build_message(ticker, price, rsi_value, threshold, now)
        notifier.send(message)
        print(f"[INFO] Sent alert for {ticker} (RSI {rsi_value:.1f}).")


def _collect_rsi_stats(alerts: List[Dict[str, str]], provider: str) -> Dict[str, Tuple[float, float]]:
    service = PriceService(provider=provider)
    stats: Dict[str, Tuple[float, float]] = {}
    seen = set()
    for alert in alerts:
        ticker = alert.get("ticker")
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        try:
            result = service.download(ticker)
        except Exception as exc:  # pragma: no cover - network errors
            print(f"[WARN] Failed to download price for {ticker}: {exc}")
            continue
        df = compute_rsi(result.dataframe)
        price = _latest_value(df, "Close")
        rsi_value = _latest_value(df, "RSI")
        if price is None or rsi_value is None:
            continue
        stats[ticker] = (float(rsi_value), float(price))
    return stats


def _latest_value(df: pd.DataFrame, column: str):
    if column not in df.columns:
        return None
    clean = df.dropna(subset=[column])
    if clean.empty:
        return None
    return clean.iloc[-1][column]


def _build_message(ticker: str, price: float, rsi_value: float, threshold: float, now: datetime) -> str:
    date_str = now.strftime("%Y-%m-%d %H:%M")
    return (
        f"[TradeChart JP]\n"
        f"{date_str} JST\n"
        f"{ticker}: RSI {rsi_value:.1f} (<= {threshold:.1f})\n"
        f"株価: {price:,.2f}"
    )


if __name__ == "__main__":
    main()
