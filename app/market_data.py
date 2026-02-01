"""Utilities for downloading price history and computing technical indicators."""

from __future__ import annotations

from typing import Optional

import pandas as pd
import yfinance as yf


def download_price_history(ticker: str, *, period: str = "2y") -> pd.DataFrame:
    data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.reset_index()
    data.sort_values("Date", inplace=True)
    data.reset_index(drop=True, inplace=True)
    return data


def compute_rsi(price_df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    if "Close" not in price_df.columns:
        return price_df.copy()

    result = price_df.copy()
    close = result["Close"].astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace({0: pd.NA})
    rsi = 100 - (100 / (1 + rs))
    result["RSI"] = rsi
    return result
