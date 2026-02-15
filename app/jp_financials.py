"""Fetch annual financial metrics for Japanese stocks via yfinance."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

import pandas as pd
import yfinance as yf

from app.market_data import normalize_ticker_for_data

METRIC_ROWS = {
    "revenue": [
        "Total Revenue",
        "Revenue",
        "Operating Revenue",
    ],
    "operating_income": [
        "Operating Income",
        "OperatingIncome",
    ],
    "net_income": [
        "Net Income",
        "NetIncome",
        "Net Income Common Stockholders",
    ],
    "operating_cash_flow": [
        "Operating Cash Flow",
        "Total Cash From Operating Activities",
        "Cash Flow From Continuing Operating Activities",
    ],
}


def download_annual_metrics(ticker: str, *, years: int = 5) -> Dict[str, List[dict]]:
    symbol = normalize_ticker_for_data(ticker)
    if not symbol:
        return {}

    try:
        ticker_obj = yf.Ticker(symbol)
        income_stmt = _first_non_empty_statement(
            [ticker_obj.income_stmt, ticker_obj.financials]
        )
        cashflow_stmt = _first_non_empty_statement([ticker_obj.cashflow])
    except Exception:
        return {}

    if income_stmt is None and cashflow_stmt is None:
        return {}

    available_years = sorted(
        set(_statement_year_map(income_stmt).keys())
        | set(_statement_year_map(cashflow_stmt).keys())
    )
    if not available_years:
        return {}

    limit = max(int(years), 1)
    selected_years = available_years[-limit:]
    currency = _detect_currency(ticker_obj, symbol)

    metrics: Dict[str, List[dict]] = {}
    for metric, row_candidates in METRIC_ROWS.items():
        statement = cashflow_stmt if metric == "operating_cash_flow" else income_stmt
        row_name = _find_row_name(statement, row_candidates)
        series: List[dict] = []
        for year in selected_years:
            value = _value_for_year(statement, row_name, year)
            series.append(
                {
                    "year": year,
                    "value": value,
                    "unit": currency,
                }
            )
        metrics[metric] = series

    return metrics


def _first_non_empty_statement(
    statements: Iterable[Optional[pd.DataFrame]],
) -> Optional[pd.DataFrame]:
    for statement in statements:
        if statement is None:
            continue
        if not isinstance(statement, pd.DataFrame):
            continue
        if statement.empty:
            continue
        return statement.copy()
    return None


def _statement_year_map(statement: Optional[pd.DataFrame]) -> Dict[int, object]:
    if statement is None or statement.empty:
        return {}

    latest_per_year: Dict[int, tuple[pd.Timestamp, object]] = {}
    for column in statement.columns:
        ts = pd.to_datetime(column, errors="coerce")
        if pd.isna(ts):
            continue
        year = int(ts.year)
        current = latest_per_year.get(year)
        if current is None or ts > current[0]:
            latest_per_year[year] = (ts, column)

    return {year: pair[1] for year, pair in latest_per_year.items()}


def _find_row_name(
    statement: Optional[pd.DataFrame], row_candidates: Iterable[str]
) -> Optional[object]:
    if statement is None or statement.empty:
        return None

    index_lookup = {
        _normalize_label(str(index)): index for index in statement.index
    }
    for candidate in row_candidates:
        matched = index_lookup.get(_normalize_label(candidate))
        if matched is not None:
            return matched
    return None


def _value_for_year(
    statement: Optional[pd.DataFrame], row_name: Optional[object], year: int
) -> Optional[float]:
    if statement is None or statement.empty or row_name is None:
        return None

    year_map = _statement_year_map(statement)
    column = year_map.get(year)
    if column is None:
        return None

    try:
        value = statement.at[row_name, column]
    except Exception:
        return None

    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _detect_currency(ticker_obj: yf.Ticker, symbol: str) -> str:
    try:
        fast_info = ticker_obj.fast_info or {}
        currency = fast_info.get("currency")
        if currency:
            return str(currency).upper()
    except Exception:
        pass

    try:
        info = ticker_obj.info or {}
        currency = info.get("currency")
        if currency:
            return str(currency).upper()
    except Exception:
        pass

    if symbol.endswith(".T"):
        return "JPY"
    return "USD"
