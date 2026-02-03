#!/usr/bin/env python3
"""CLI helper to register alerts into Supabase/JSON backend."""

from __future__ import annotations

import argparse
import sys

from app.alerts import add_alert


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add an RSI alert")
    parser.add_argument("ticker", help="証券コードまたはティッカー")
    parser.add_argument(
        "--threshold",
        type=float,
        default=40.0,
        help="RSI 閾値 (default: 40)",
    )
    parser.add_argument(
        "--type",
        default="RSI",
        help="アラートタイプ (default: RSI)",
    )
    parser.add_argument("--note", default="", help="任意のメモ")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.ticker:
        print("[ERROR] ticker is required", file=sys.stderr)
        sys.exit(1)
    alert = add_alert(
        ticker=args.ticker,
        alert_type=args.type,
        threshold=args.threshold,
        note=args.note,
    )
    print("Registered alert:", alert)


if __name__ == "__main__":
    main()
