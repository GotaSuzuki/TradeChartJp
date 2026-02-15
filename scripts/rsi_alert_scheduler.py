"""Run RSI alerts automatically at scheduled JST times."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.rsi_alert import run_alerts, DEFAULT_TICKERS

JST = ZoneInfo("Asia/Tokyo")


def parse_times(value: str) -> list[dt_time]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    times = []
    for part in parts:
        try:
            hour, minute = part.split(":")
            times.append(dt_time(int(hour), int(minute)))
        except ValueError:
            continue
    return times or [dt_time(7, 0), dt_time(12, 30)]


def next_run(now: datetime, schedule_times: list[dt_time]) -> datetime:
    candidates = []
    for t in schedule_times:
        run_dt = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if run_dt <= now:
            run_dt += timedelta(days=1)
        candidates.append(run_dt)
    return min(candidates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Schedule RSI alerts at given JST times")
    parser.add_argument("tickers", nargs="*", help="監視する銘柄コード (例: 7203 8306)")
    parser.add_argument(
        "--times",
        default="07:00,12:30",
        help="JSTでの実行時刻をカンマ区切りで指定 (例: '07:00,12:30')",
    )
    args = parser.parse_args()

    tickers = args.tickers or DEFAULT_TICKERS
    schedule_times = parse_times(args.times)
    print(f"予定された実行時刻 (JST): {[t.strftime('%H:%M') for t in schedule_times]}")

    while True:
        now = datetime.now(JST)
        run_at = next_run(now, schedule_times)
        wait_seconds = (run_at - now).total_seconds()
        print(f"次の実行: {run_at.strftime('%Y-%m-%d %H:%M')} JST (あと {wait_seconds/60:.1f} 分)")
        time.sleep(max(wait_seconds, 0))
        try:
            print("RSIアラートを実行中...")
            run_alerts(tickers)
        except Exception as exc:  # pragma: no cover
            print(f"アラート実行中にエラーが発生しました: {exc}")
        time.sleep(1)


if __name__ == "__main__":
    main()
