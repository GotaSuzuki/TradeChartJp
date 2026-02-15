"""Utilities for downloading price history and computing technical indicators."""

from __future__ import annotations

from typing import Optional

import re

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from app.config import get_config

_JP_CODE_RE = re.compile(r"^\d{4}$")
_JP_CODE_ALPHA_RE = re.compile(r"^\d{3}[A-Z]$")
_JP_SYMBOL_RE = re.compile(r"^(\d{4}|\d{3}[A-Z])\.T$")


def normalize_ticker_for_data(ticker: str) -> str:
    cleaned = ticker.strip().upper()
    if not cleaned:
        return ""
    if _JP_CODE_RE.fullmatch(cleaned) or _JP_CODE_ALPHA_RE.fullmatch(cleaned):
        return f"{cleaned}.T"
    return cleaned


def normalize_ticker_for_display(ticker: str) -> str:
    cleaned = ticker.strip().upper()
    if _JP_SYMBOL_RE.fullmatch(cleaned):
        return cleaned[:-2]
    return cleaned


def is_jp_ticker(ticker: str) -> bool:
    cleaned = ticker.strip().upper()
    return bool(
        _JP_CODE_RE.fullmatch(cleaned)
        or _JP_CODE_ALPHA_RE.fullmatch(cleaned)
        or _JP_SYMBOL_RE.fullmatch(cleaned)
    )


def download_price_history(ticker: str, *, period: str = "2y") -> pd.DataFrame:
    symbol = normalize_ticker_for_data(ticker)
    if not symbol:
        return pd.DataFrame()

    alpaca_df = _download_from_alpaca(symbol)
    if alpaca_df is not None and not alpaca_df.empty:
        return alpaca_df

    data = yf.download(symbol, period=period, auto_adjust=True, progress=False)
    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.reset_index()
    data.sort_values("Date", inplace=True)
    data.reset_index(drop=True, inplace=True)
    return data


def download_fund_nav_history(code: str) -> pd.DataFrame:
    """Download NAV history for Japanese mutual funds via Yahoo Finance Japan."""

    headers = _fund_headers()
    history_html = _fetch_fund_page(code, "/history", headers)
    if not history_html:
        return pd.DataFrame()

    rows = _parse_fund_nav_history_from_html(history_html)
    if not rows:
        summary_html = _fetch_fund_page(code, "", headers)
        if summary_html:
            rows = _parse_fund_nav_snapshot_from_html(summary_html)
        else:
            rows = _parse_fund_nav_snapshot_from_html(history_html)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df.sort_values("Date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def fetch_usd_jpy_rate() -> tuple[Optional[float], Optional[pd.Timestamp]]:
    """Fetch USD/JPY rate from a public FX API."""

    url = "https://open.er-api.com/v6/latest/USD"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return None, None

    data = response.json()
    if data.get("result") != "success":
        return None, None
    rates = data.get("rates") or {}
    rate = rates.get("JPY")
    if rate is None:
        return None, None
    timestamp = data.get("time_last_update_unix")
    as_of = (
        pd.to_datetime(timestamp, unit="s", utc=True).tz_convert(None)
        if timestamp
        else None
    )
    try:
        return float(rate), as_of
    except (TypeError, ValueError):
        return None, None


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


def _download_from_alpaca(ticker: str) -> Optional[pd.DataFrame]:
    symbol = normalize_ticker_for_data(ticker)
    if is_jp_ticker(symbol):
        return None

    config = get_config()
    if not config.alpaca_api_key_id or not config.alpaca_api_secret_key:
        return None

    base_url = config.alpaca_data_base_url.rstrip("/")
    url = f"{base_url}/v2/stocks/{symbol}/bars"
    params = {
        "timeframe": "1Day",
        "limit": 1000,
        "feed": config.alpaca_data_feed or "iex",
        "adjustment": "split",
    }
    headers = {
        "APCA-API-KEY-ID": config.alpaca_api_key_id,
        "APCA-API-SECRET-KEY": config.alpaca_api_secret_key,
    }
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None

    data = response.json().get("bars", [])
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df.rename(
        columns={"t": "Date", "o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"},
        inplace=True,
    )
    df["Date"] = pd.to_datetime(df["Date"])
    df.sort_values("Date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


_DATE_RE = re.compile(r"\\d{4}/\\d{1,2}/\\d{1,2}")


def _parse_fund_nav_history_from_html(html: str) -> list[dict]:
    rows = _parse_fund_nav_history_tables(html)
    if rows:
        return rows
    soup = BeautifulSoup(html, "html.parser")
    return _parse_fund_nav_history(soup)


def _parse_fund_nav_history_tables(html: str) -> list[dict]:
    try:
        tables = pd.read_html(html)
    except (ValueError, ImportError):
        return []

    rows: list[dict] = []
    for table in tables:
        columns = _normalize_columns(table.columns)
        table.columns = columns
        date_col = next((c for c in columns if "日付" in c), None)
        nav_col = next((c for c in columns if "基準" in c and "価額" in c), None)
        if nav_col is None:
            nav_col = next((c for c in columns if "基準" in c), None)
        if not date_col or not nav_col:
            continue

        sub = table[[date_col, nav_col]].copy()
        sub.columns = ["Date", "NAV"]
        sub["Date"] = pd.to_datetime(sub["Date"], errors="coerce")
        sub["NAV"] = sub["NAV"].apply(lambda value: _parse_number(str(value)))
        sub = sub.dropna(subset=["Date", "NAV"])
        for _, row in sub.iterrows():
            rows.append({"Date": row["Date"], "NAV": row["NAV"]})
        if rows:
            break
    return rows


def _normalize_columns(columns) -> list[str]:
    if isinstance(columns, pd.MultiIndex):
        normalized = []
        for col in columns:
            parts = [str(part) for part in col if str(part) != "nan"]
            normalized.append(" ".join(parts).strip())
        return normalized
    return [str(col).strip() for col in columns]


def _parse_fund_nav_snapshot_from_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    nav_value = None
    nav_date = None

    for label in soup.find_all(string=re.compile("基準価額")):
        parent = getattr(label, "parent", None)
        if parent and parent.name in ("dt", "th"):
            sibling = parent.find_next_sibling(["dd", "td"])
            if sibling:
                nav_value = _parse_number(sibling.get_text(strip=True))
        if nav_value is None and parent:
            row = parent.find_parent("tr")
            if row:
                nav_value = _parse_number(row.get_text(" ", strip=True))
        if nav_value is not None:
            break

    if nav_value is None:
        match = re.search(r"基準価額[^0-9]*([0-9,]+)", html)
        if match:
            nav_value = _parse_number(match.group(1))

    for label in soup.find_all(string=re.compile("基準日|更新日")):
        parent = getattr(label, "parent", None)
        if parent and parent.name in ("dt", "th"):
            sibling = parent.find_next_sibling(["dd", "td"])
            if sibling:
                nav_date = _parse_date_from_text(sibling.get_text(strip=True))
        if nav_date:
            break

    if nav_date is None:
        nav_date = _parse_date_from_text(html)

    if nav_value is None:
        return []
    return [{"Date": nav_date, "NAV": nav_value}]


def _parse_fund_nav_history(soup: BeautifulSoup) -> list[dict]:
    tables = soup.find_all("table")
    candidates = []
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if not headers:
            continue
        if "日付" in headers and any("基準" in header for header in headers):
            candidates.append(table)

    tables_to_scan = candidates if candidates else tables
    rows: list[dict] = []
    for table in tables_to_scan:
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            texts = [cell.get_text(strip=True) for cell in cells]
            date_idx = None
            for idx, text in enumerate(texts):
                if _DATE_RE.fullmatch(text):
                    date_idx = idx
                    break
            if date_idx is None:
                continue
            date_value = pd.to_datetime(texts[date_idx], errors="coerce")
            if pd.isna(date_value):
                continue

            nav_text = None
            if date_idx + 1 < len(texts):
                nav_text = texts[date_idx + 1]
            if nav_text is None or not _looks_like_number(nav_text):
                nav_text = next((t for t in texts if _looks_like_number(t)), None)

            nav_value = _parse_number(nav_text)
            if nav_value is None:
                continue
            rows.append({"Date": date_value, "NAV": nav_value})

        if rows:
            break
    return rows


def _looks_like_number(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"\\d", text))


def _parse_number(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.]", "", text)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date_from_text(text: str) -> Optional[pd.Timestamp]:
    match = _DATE_RE.search(text)
    if not match:
        return None
    parsed = pd.to_datetime(match.group(0), errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed


def _fund_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://finance.yahoo.co.jp/",
    }


def _fetch_fund_page(code: str, path: str, headers: dict) -> Optional[str]:
    url = f"https://finance.yahoo.co.jp/quote/{code}{path}"
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None
    return response.text
