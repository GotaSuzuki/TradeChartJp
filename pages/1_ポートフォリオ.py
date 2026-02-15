"""Streamlit portfolio page."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st

from app.market_data import (
    download_fund_nav_history,
    download_price_history,
    fetch_usd_jpy_rate,
    is_jp_ticker,
    normalize_ticker_for_display,
)
from app.portfolio import delete_holding, load_holdings, upsert_holding

st.set_page_config(page_title="ポートフォリオ", layout="wide")

st.title("ポートフォリオ")
st.markdown("保有株の登録、現在価格、構成比をまとめて表示します。")

COLOR_PALETTE = [
    "#4C78A8",
    "#F58518",
    "#E45756",
    "#72B7B2",
    "#54A24B",
    "#EECA3B",
    "#B279A2",
    "#FF9DA6",
    "#9D755D",
    "#BAB0AC",
    "#1F77B4",
    "#2CA02C",
    "#D62728",
    "#9467BD",
    "#8C564B",
]

FUND_ALIAS = {
    "04311181": "FANG+",
}
BASE_CURRENCY = "JPY"


def _is_fund_code(ticker: str) -> bool:
    return ticker.isdigit() and len(ticker) == 8


def _display_label(ticker: str) -> str:
    ticker = normalize_ticker_for_display(ticker)
    alias = FUND_ALIAS.get(ticker)
    if alias:
        return alias
    return ticker


@st.cache_data(show_spinner=False, ttl=3600)
def _get_usd_jpy_rate() -> Tuple[Optional[float], Optional[pd.Timestamp]]:
    return fetch_usd_jpy_rate()


def _convert_to_base(
    value: Optional[float],
    currency: str,
    base_currency: str,
    usd_jpy_rate: Optional[float],
) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    if currency == base_currency:
        return float(value)
    if base_currency == "JPY" and currency == "USD":
        if usd_jpy_rate is None:
            return None
        return float(value) * usd_jpy_rate
    if base_currency == "USD" and currency == "JPY":
        if usd_jpy_rate is None or usd_jpy_rate == 0:
            return None
        return float(value) / usd_jpy_rate
    return None


@st.cache_data(show_spinner=False, ttl=1800)
def _get_latest_stock_price(ticker: str) -> Tuple[Optional[float], Optional[pd.Timestamp]]:
    try:
        price_df = download_price_history(ticker, period="1y")
    except Exception:
        return None, None

    if price_df is None or price_df.empty or "Close" not in price_df.columns:
        return None, None
    clean = price_df.dropna(subset=["Close"]).copy()
    if clean.empty:
        return None, None
    last = clean.iloc[-1]
    price = float(last["Close"])
    date = pd.to_datetime(last.get("Date"))
    return price, date


@st.cache_data(show_spinner=False, ttl=1800)
def _get_latest_fund_nav(code: str) -> Tuple[Optional[float], Optional[pd.Timestamp]]:
    try:
        nav_df = download_fund_nav_history(code)
    except Exception:
        return None, None
    if nav_df is None or nav_df.empty or "NAV" not in nav_df.columns:
        return None, None
    clean = nav_df.dropna(subset=["NAV"]).copy()
    if clean.empty:
        return None, None
    last = clean.iloc[-1]
    nav = float(last["NAV"])
    date = pd.to_datetime(last.get("Date"))
    return nav, date


def _build_portfolio_rows(holdings: List[Dict[str, object]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for holding in holdings:
        ticker = normalize_ticker_for_display(str(holding.get("ticker", "")))
        shares = float(holding.get("shares", 0))
        if _is_fund_code(ticker):
            price, price_date = _get_latest_fund_nav(ticker)
            currency = "JPY"
        else:
            price, price_date = _get_latest_stock_price(ticker)
            currency = "JPY" if is_jp_ticker(ticker) else "USD"
        value = price * shares if price is not None else None
        rows.append(
            {
                "id": holding.get("id"),
                "ticker": ticker,
                "label": _display_label(ticker),
                "shares": shares,
                "price": price,
                "price_date": price_date,
                "value": value,
                "currency": currency,
            }
        )
    return rows


def _format_value(value: Optional[float], currency: str) -> str:
    if value is None or pd.isna(value):
        return "-"
    decimals = 0 if currency == "JPY" else 2
    return f"{value:,.{decimals}f} {currency}"


left_col, right_col = st.columns([1.1, 1.4], gap="large")

with left_col:
    st.subheader("保有株の登録")
    with st.form("portfolio-add-form"):
        ticker_input = st.text_input("銘柄コード/ティッカー", value="", placeholder="7203")
        shares_input = st.number_input(
            "保有数",
            min_value=1,
            value=1,
            step=1,
            format="%d",
            help="整数のみ入力できます。",
        )
        submitted = st.form_submit_button("追加 / 更新")
        if submitted:
            ticker = normalize_ticker_for_display(ticker_input)
            if not ticker:
                st.warning("銘柄コードまたはティッカーを入力してください。")
            elif shares_input <= 0:
                st.warning("保有数は0より大きく入力してください。")
            else:
                upsert_holding(ticker=ticker, shares=int(shares_input))
                st.success(f"{ticker} を登録しました。")

    st.divider()

    holdings = load_holdings()
    if not holdings:
        st.subheader("保有一覧")
        st.info("まだ保有株が登録されていません。")
    else:
        rows = _build_portfolio_rows(holdings)
        df = pd.DataFrame(rows)
        df.sort_values("ticker", inplace=True)

        st.subheader("保有一覧")
        currency_totals = df.groupby("currency")["value"].sum(min_count=1).dropna()
        needs_fx = any(currency != BASE_CURRENCY for currency in df["currency"].dropna())
        usd_jpy_rate, fx_as_of = (None, None)
        if needs_fx:
            usd_jpy_rate, fx_as_of = _get_usd_jpy_rate()

        if needs_fx and usd_jpy_rate is not None:
            df["value_base"] = df.apply(
                lambda row: _convert_to_base(
                    row["value"], row["currency"], BASE_CURRENCY, usd_jpy_rate
                ),
                axis=1,
            )
            total_base = df["value_base"].sum(min_count=1)
            if pd.isna(total_base):
                st.metric("評価額合計", "-")
            else:
                st.metric("評価額合計 (JPY換算)", _format_value(total_base, BASE_CURRENCY))
            if fx_as_of is not None:
                st.caption(
                    f"USD/JPY: {usd_jpy_rate:,.2f} (as of {fx_as_of.date()})"
                )
        elif currency_totals.empty:
            st.metric("評価額合計", "-")
        elif len(currency_totals) == 1:
            currency = currency_totals.index[0]
            st.metric("評価額合計", _format_value(currency_totals.iloc[0], currency))
        else:
            st.markdown("評価額合計 (通貨別)")
            cols = st.columns(len(currency_totals))
            for col, (currency, total) in zip(cols, currency_totals.items()):
                with col:
                    st.metric(currency, _format_value(total, currency))
            st.info("為替レートを取得できないため、合算できませんでした。")

        display_df = df.rename(
            columns={
                "label": "銘柄",
                "shares": "保有数",
                "price": "現在株価",
                "price_date": "価格日付",
                "value": "評価額",
                "currency": "通貨",
            }
        )
        if needs_fx and usd_jpy_rate is not None:
            display_df["評価額(換算)"] = df["value_base"]
            display_df = display_df[
                ["銘柄", "通貨", "保有数", "現在株価", "評価額", "評価額(換算)", "価格日付"]
            ]
        else:
            display_df = display_df[
                ["銘柄", "通貨", "保有数", "現在株価", "評価額", "価格日付"]
            ]

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "保有数": st.column_config.NumberColumn(format="%d"),
                "現在株価": st.column_config.NumberColumn(format="%.2f"),
                "評価額": st.column_config.NumberColumn(format="%.2f"),
                "評価額(換算)": st.column_config.NumberColumn(format="%.0f"),
                "価格日付": st.column_config.DatetimeColumn(format="YYYY-MM-DD"),
            },
        )

        st.subheader("保有株の削除")
        options = {
            f"{_display_label(h['ticker'])} ({h['shares']})": h["id"]
            for h in holdings
        }
        selected = st.selectbox("削除する銘柄", list(options.keys()))
        if st.button("選択した銘柄を削除"):
            delete_holding(options[selected])
            st.success("保有株を削除しました。再読込すると一覧に反映されます。")

with right_col:
    st.subheader("ポートフォリオ構成比")
    holdings = load_holdings()
    if not holdings:
        st.info("保有株がないため、構成比を表示できません。")
    else:
        rows = _build_portfolio_rows(holdings)
        df = pd.DataFrame(rows)
        df.sort_values("ticker", inplace=True)
        currency_set = set(df["currency"].dropna())
        needs_fx = any(currency != BASE_CURRENCY for currency in currency_set)
        usd_jpy_rate, fx_as_of = (None, None)
        if needs_fx:
            usd_jpy_rate, fx_as_of = _get_usd_jpy_rate()

        plot_df = df.dropna(subset=["value"]).copy()
        if plot_df.empty:
            st.info("価格データが取得できず、構成比を計算できませんでした。")
        elif needs_fx and usd_jpy_rate is None:
            st.info("為替レートを取得できないため、構成比を表示できません。")
        else:
            if needs_fx:
                plot_df["value_base"] = plot_df.apply(
                    lambda row: _convert_to_base(
                        row["value"], row["currency"], BASE_CURRENCY, usd_jpy_rate
                    ),
                    axis=1,
                )
                plot_values = plot_df["value_base"]
            else:
                plot_values = plot_df["value"]

            total_value = plot_values.sum(min_count=1)
            if pd.isna(total_value) or not total_value or total_value <= 0:
                st.info("価格データが取得できず、構成比を計算できませんでした。")
            else:
                labels = plot_df["label"].tolist()
                fig = px.pie(
                    plot_df,
                    names="label",
                    values=plot_values,
                    color="label",
                    title="ポートフォリオ構成比",
                    category_orders={"label": labels},
                    color_discrete_sequence=COLOR_PALETTE,
                )
                fig.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig, use_container_width=True)

    st.caption("データソース: Yahoo Finance (yfinance) / Yahoo Finance Japan / Alpaca")
