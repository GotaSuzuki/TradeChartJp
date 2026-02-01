"""価格データ取得サービス。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import yfinance as yf


@dataclass
class PriceResult:
    dataframe: pd.DataFrame
    source: str


class PriceService:
    def __init__(self, provider: str = "yfinance") -> None:
        self.provider = provider

    def download(self, code: str, *, period: str = "2y") -> PriceResult:
        if self.provider != "yfinance":
            raise ValueError(f"Unsupported provider: {self.provider}")

        ticker = self._to_yfinance_symbol(code)
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index().sort_values("Date")
        return PriceResult(dataframe=df, source="yfinance")

    @staticmethod
    def _to_yfinance_symbol(code: str) -> str:
        code = code.strip()
        if not code:
            raise ValueError("code is required")
        # yfinance は東証銘柄に .T サフィックスを付ける
        if code.endswith(".T"):
            return code
        return f"{code}.T"
