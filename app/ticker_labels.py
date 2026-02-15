"""Ticker label helpers for Japanese display names."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

import requests
from bs4 import BeautifulSoup

from app.market_data import is_jp_ticker, normalize_ticker_for_data, normalize_ticker_for_display

JP_TICKER_NAMES = {
    "285A": "キオクシアホールディングス",
    "6857": "アドバンテスト",
    "6525": "KOKUSAI ELECTRIC",
    "3110": "日東紡",
    "6871": "日本マイクロニクス",
    "5803": "フジクラ",
    "4062": "イビデン",
    "7011": "三菱重工業",
    "5805": "SWCC",
}

_TITLE_CODE_RE = re.compile(r"【[^】]+】")
_TITLE_SUFFIX_RE = re.compile(r"の株価・株式情報$")
_MULTISPACE_RE = re.compile(r"\s+")


def get_ticker_name_jp(ticker: str) -> str:
    code = normalize_ticker_for_display(ticker)
    if not code:
        return ""

    fixed_name = JP_TICKER_NAMES.get(code)
    if fixed_name:
        return fixed_name

    fetched = _fetch_name_from_yahoo(code)
    return fetched or ""


def get_ticker_label(ticker: str) -> str:
    code = normalize_ticker_for_display(ticker)
    if not code:
        return ""

    name = get_ticker_name_jp(code)
    if not name:
        return code
    return f"{code} {name}"


@lru_cache(maxsize=256)
def _fetch_name_from_yahoo(ticker_code: str) -> Optional[str]:
    if not is_jp_ticker(ticker_code):
        return None

    symbol = normalize_ticker_for_data(ticker_code)
    if not symbol:
        return None

    url = f"https://finance.yahoo.co.jp/quote/{symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://finance.yahoo.co.jp/",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    h1 = soup.find("h1")
    if h1:
        candidates.append(h1.get_text(" ", strip=True))
    if soup.title:
        candidates.append(soup.title.get_text(" ", strip=True))

    for raw in candidates:
        normalized = _normalize_name(raw)
        if normalized:
            return normalized
    return None


def _normalize_name(text: str) -> str:
    if not text:
        return ""

    normalized = text.strip()
    normalized = normalized.replace("（株）", "").replace("(株)", "").replace("㈱", "")
    normalized = _TITLE_CODE_RE.sub("", normalized)
    normalized = normalized.split(" - Yahoo!ファイナンス")[0]
    normalized = _TITLE_SUFFIX_RE.sub("", normalized)
    normalized = normalized.replace("：株価・株式情報", "")
    normalized = normalized.strip(" -:")
    normalized = _MULTISPACE_RE.sub(" ", normalized).strip()
    return normalized
