"""指定ティッカーの10-Kを事前に取得してローカル保存する。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.cache import DataCache
from app.config import get_config
from app.edgar_client import EdgarClient
from app.filings_fetcher import FilingsFetcher


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-fetch SEC filings for tickers")
    parser.add_argument("tickers", nargs="+", help="ティッカーシンボル (例: AAPL MSFT)")
    parser.add_argument("--output", default="data/processed", help="保存先ディレクトリ")
    args = parser.parse_args()

    config = get_config()
    cache = DataCache(Path(args.output) / "cache")
    client = EdgarClient(
        company_name=config.company_name,
        email_address=config.email_address,
        download_dir=config.download_dir,
    )
    fetcher = FilingsFetcher(client, cache=cache, cache_ttl_hours=config.cache_ttl_hours)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    for ticker in args.tickers:
        filings = fetcher.fetch_recent_filings(ticker, years=config.filings_years)
        if not filings:
            print(f"{ticker}: データが見つかりませんでした")
            continue
        output_path = output_dir / f"{ticker.upper()}_filings.json"
        output_path.write_text(json.dumps(filings, indent=2))
        print(f"{ticker}: {len(filings)}期分を {output_path} に保存しました")


if __name__ == "__main__":
    main()
