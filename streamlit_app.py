"""Streamlit entrypoint for Japanese stock dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.alerts import add_alert, delete_alert, load_alerts
from app.config import get_config
from app.jp_financials import download_annual_metrics
from app.market_data import (
    compute_rsi as compute_price_rsi,
    download_price_history,
    is_jp_ticker,
    normalize_ticker_for_display,
)
from app.metrics import compute_cagr, compute_yoy, to_dataframe
from app.ticker_labels import get_ticker_label

METRIC_LABELS = {
    "revenue": "売上高",
    "operating_income": "営業利益",
    "net_income": "純利益",
    "operating_cash_flow": "営業キャッシュフロー",
}

TECH_PERIOD_OPTIONS = {
    "3ヶ月": 90,
    "6ヶ月": 180,
    "1年": 365,
}


@st.cache_resource(show_spinner=False)
def _init_config():
    return get_config()


def main() -> None:
    st.set_page_config(page_title="日本株アラートダッシュボード", layout="wide")
    config = _init_config()
    st.title("日本株アラートダッシュボード")

    st.markdown(
        "yfinance から年次財務データと価格データを取得し、主要指標・テクニカル・RSIアラートを表示します。"
    )

    with st.sidebar:
        st.header("パラメータ")
        ticker_input = st.text_input("銘柄コード / ティッカー", value="7203")
        years = st.slider("取得年数", min_value=1, max_value=10, value=config.filings_years)
        fetch_clicked = st.button("データを取得", use_container_width=True)
        tech_period_label = st.selectbox(
            "テクニカル期間", list(TECH_PERIOD_OPTIONS.keys()), index=1
        )

    ticker = normalize_ticker_for_display(ticker_input)
    view = st.radio(
        "表示ビュー", ("ファンダメンタル", "テクニカル", "アラート"), horizontal=True
    )

    if fetch_clicked:
        if not ticker:
            st.warning("銘柄コードまたはティッカーを入力してください。")
            return

        with st.spinner("財務データを取得中..."):
            metrics = download_annual_metrics(ticker, years=years)

        if not metrics:
            st.warning("指定銘柄の財務データを取得できませんでした。")
            return

        enriched = compute_yoy(metrics)
        cagr_map = compute_cagr(enriched)
        df = to_dataframe(enriched)
        if df.empty:
            st.warning("可視化可能なデータがありません。")
            return

        st.session_state["financial_df"] = df
        st.session_state["cagr_map"] = cagr_map
        st.session_state["selected_ticker"] = ticker
        history = st.session_state.get("ticker_history", [])
        if ticker not in history:
            history.append(ticker)
            st.session_state["ticker_history"] = history[-10:]

    stored_df = st.session_state.get("financial_df")
    stored_cagr = st.session_state.get("cagr_map")
    stored_ticker = st.session_state.get("selected_ticker", ticker)

    if view == "アラート":
        render_alerts_page()
        return

    if stored_df is None or stored_cagr is None:
        st.info("左のフォームで銘柄を取得するとビューが表示されます。")
        return

    if view == "ファンダメンタル":
        render_metric_panels(stored_df, stored_cagr)
        render_alert_form(stored_ticker, config, location="fundamental")
    else:
        render_technical_section(stored_ticker, tech_period_label)


def render_metric_panels(df, cagr_map):
    st.subheader("主要指標")
    cols = st.columns(len(METRIC_LABELS))
    for idx, (metric, label) in enumerate(METRIC_LABELS.items()):
        metric_df = df[df["metric"] == metric].dropna(subset=["value"])
        if metric_df.empty:
            continue
        metric_df = metric_df.sort_values("year")
        latest = metric_df.iloc[-1]
        value_text = _format_value(latest["value"], latest.get("unit"))
        year = int(latest["year"])
        cagr = cagr_map.get(metric)
        delta, delta_color = _format_cagr_delta(cagr)

        max_abs = metric_df["value"].abs().max()
        scale, suffix = _determine_scale(max_abs)
        metric_df["value_m"] = metric_df["value"] / scale if scale else metric_df["value"]
        unit_series = metric_df["unit"] if "unit" in metric_df else None
        if unit_series is not None and not unit_series.dropna().empty:
            unit = unit_series.dropna().iloc[-1]
        else:
            unit = ""

        with cols[idx]:
            st.metric(
                label=f"{label} ({year})",
                value=value_text,
                delta=delta,
                delta_color=delta_color,
            )
            y_label = _build_axis_label(label, unit, suffix)
            fig = px.line(
                metric_df,
                x="year",
                y="value_m",
                markers=True,
                labels={"year": "年度", "value_m": y_label},
            )
            fig.update_layout(margin=dict(l=6, r=6, t=20, b=6), height=260)
            fig.update_traces(line_color="#1f77b4")
            st.plotly_chart(fig, use_container_width=True)


def render_technical_section(ticker: str, period_label: str):
    st.subheader(f"テクニカル表示: {get_ticker_label(ticker)}")
    price_df = _get_price_history(ticker)
    if price_df is None or price_df.empty:
        st.info("価格データを取得できませんでした。")
        return

    required_cols = {"Date", "Close"}
    if not required_cols.issubset(price_df.columns):
        st.info("価格データの形式が予期せず、描画できませんでした。")
        return

    currency = _currency_for_ticker(ticker)
    price_df = price_df.sort_values("Date").copy()
    price_df = _append_rsi(price_df)
    latest_price, latest_rsi = _render_latest_price(price_df, currency)
    price_df["MA20"] = price_df["Close"].rolling(20).mean()
    price_df["MA50"] = price_df["Close"].rolling(50).mean()
    price_df["MA200"] = price_df["Close"].rolling(200).mean()

    days = TECH_PERIOD_OPTIONS.get(period_label, 180)
    if price_df["Date"].dtype.kind == "M":
        last_date = price_df["Date"].max()
    else:
        last_date = pd.to_datetime(price_df["Date"]).max()
    cutoff = last_date - pd.Timedelta(days=days)
    recent = price_df[price_df["Date"] >= cutoff]

    display_cols = [
        col for col in ["Close", "MA20", "MA50", "MA200"] if col in recent.columns
    ]
    melted = recent.melt(
        id_vars="Date", value_vars=display_cols, var_name="Series", value_name="Price"
    )
    if "RSI" in recent.columns:
        rsi_lookup = recent.set_index("Date")["RSI"]
        melted["RSI"] = melted["Date"].map(rsi_lookup)
    else:
        melted["RSI"] = None
    melted.dropna(subset=["Price"], inplace=True)

    fig = px.line(
        melted,
        x="Date",
        y="Price",
        color="Series",
        labels={"Date": "日付", "Price": f"価格 ({currency})", "Series": "系列"},
    )
    _apply_cross_shading(fig, recent)
    fig.update_layout(
        margin=dict(l=10, r=10, t=20, b=10),
        height=320,
        hovermode="x",
        hoverlabel=dict(bgcolor="rgba(0,0,0,0)", font_color="#000"),
    )
    fig.update_xaxes(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="white",
        spikedash="dot",
        spikethickness=1,
    )
    for trace in fig.data:
        if trace.name.upper() == "CLOSE":
            mask = melted["Series"].str.upper() == "CLOSE"
            custom = melted.loc[mask, ["RSI"]].to_numpy()
            trace.customdata = custom
            trace.hovertemplate = (
                f"%{{x|%Y-%m-%d}}<br>Close: %{{y:.2f}} {currency}"
                + ("<br>RSI: %{customdata[0]:.1f}" if custom.size else "")
                + "<extra></extra>"
            )
        else:
            trace.hovertemplate = None
            trace.hoverinfo = "skip"

    st.plotly_chart(fig, use_container_width=True)
    st.caption("データソース: Yahoo Finance (yfinance)")

    if latest_price is not None and latest_rsi is not None:
        st.subheader("RSI目安価格")
        st.markdown(
            "現在のRSIと、RSIが40/35/30まで低下した際のおおよその価格です。"
        )
        bands = [
            ("RSI 40", 40),
            ("RSI 35", 35),
            ("RSI 30", 30),
        ]
        rows = []
        inserted_current = False
        for label, target in bands:
            if not inserted_current and latest_rsi >= target:
                rows.append(
                    {
                        "項目": "現在RSI",
                        "RSI": latest_rsi,
                        "目安価格": latest_price,
                        "highlight": True,
                    }
                )
                inserted_current = True
            rows.append(
                {
                    "項目": label,
                    "RSI": target,
                    "目安価格": _estimate_price_for_rsi(latest_price, latest_rsi, target),
                    "highlight": False,
                }
            )
        if not inserted_current:
            rows.append(
                {
                    "項目": "現在RSI",
                    "RSI": latest_rsi,
                    "目安価格": latest_price,
                    "highlight": True,
                }
            )

        df = pd.DataFrame(rows)
        df["RSI表記"] = df["RSI"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "-")
        df["価格表記"] = df["目安価格"].map(
            lambda x: _format_price(x, currency) if pd.notna(x) else "-"
        )
        display_df = df[["項目", "RSI表記", "価格表記"]]
        styled = display_df.style.apply(
            lambda row: [
                (
                    "background-color: rgba(255, 220, 0, 0.3)"
                    if df.iloc[row.name]["highlight"]
                    else ""
                )
                for _ in row
            ],
            axis=1,
        ).set_table_styles(
            [
                {
                    "selector": "th",
                    "props": "text-align: center;",
                }
            ]
        )
        styled = styled.set_properties(**{"text-align": "center"})
        st.table(styled)


def _format_price(value, currency: str) -> str:
    if value is None or pd.isna(value):
        return "-"
    decimals = 0 if currency == "JPY" else 2
    return f"{value:,.{decimals}f} {currency}"


def _format_value(value, unit):
    if value is None:
        return "N/A"
    scale, suffix = _determine_scale(abs(value))
    scaled_value = value / scale
    unit_str = _build_unit_label(unit, suffix)
    return f"{scaled_value:,.2f} {unit_str}".strip()


def _format_cagr_delta(cagr):
    if cagr is None:
        return "CAGR N/A", "off"
    value = cagr * 100
    color = "normal" if value >= 0 else "inverse"
    return f"CAGR {value:+.1f}%", color


def _determine_scale(value):
    if value is None:
        return 1, ""
    try:
        magnitude = float(value)
    except (TypeError, ValueError):
        return 1, ""
    if magnitude != magnitude:
        return 1, ""
    thresholds = [
        (1_000_000_000_000, "兆"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ]
    for threshold, label in thresholds:
        if magnitude >= threshold:
            return threshold, label
    return 1, ""


def _build_unit_label(unit, suffix):
    parts = []
    if suffix:
        parts.append(suffix)
    if unit:
        parts.append(unit)
    return " ".join(parts)


def _build_axis_label(metric_label, unit, suffix):
    unit_label = _build_unit_label(unit, suffix)
    if unit_label:
        return f"{metric_label} ({unit_label})"
    return metric_label


def _apply_cross_shading(fig, price_df):
    if not {"Date", "MA20", "MA50"}.issubset(price_df.columns):
        return

    df = price_df.dropna(subset=["MA20", "MA50"]).copy()
    if df.empty:
        return

    df["state"] = (df["MA20"] > df["MA50"]).astype(int)
    df["change"] = df["state"].diff().fillna(0)

    segments = []
    current_state = df.iloc[0]["state"]
    start_date = df.iloc[0]["Date"]
    prev_date = start_date
    for _, row in df.iterrows():
        date = row["Date"]
        change = row["change"]
        if change != 0:
            segments.append((start_date, prev_date, current_state))
            start_date = date
            current_state = row["state"]
        prev_date = date
    segments.append((start_date, prev_date, current_state))

    for start, end, state in segments:
        if pd.isna(start) or pd.isna(end):
            continue
        start_ts = pd.to_datetime(start)
        end_ts = pd.to_datetime(end)
        if start_ts >= end_ts:
            continue
        color = (
            "rgba(255, 99, 132, 0.15)"
            if state == 1
            else "rgba(100, 149, 237, 0.15)"
        )
        fig.add_vrect(
            x0=start_ts,
            x1=end_ts,
            fillcolor=color,
            opacity=0.3,
            line_width=0,
            layer="below",
        )


def _render_latest_price(price_df: pd.DataFrame, currency: str):
    clean = price_df.dropna(subset=["Close"]).copy()
    if clean.empty:
        return None, None
    last_row = clean.iloc[-1]
    last_close = last_row["Close"]
    last_date = last_row["Date"]
    try:
        prev_close = clean.iloc[-2]["Close"]
        delta = last_close - prev_close
    except IndexError:
        delta = None

    delta_text = None
    delta_color = "off"
    if delta is not None:
        sign = "+" if delta >= 0 else ""
        delta_text = f"{sign}{delta:,.2f}"
        delta_color = "normal" if delta >= 0 else "inverse"

    rsi_value = clean.iloc[-1].get("RSI") if "RSI" in clean.columns else None
    rsi_display = f"{rsi_value:.1f}" if rsi_value is not None else "N/A"

    price_col, rsi_col = st.columns([2, 1])
    with price_col:
        st.metric(
            label=f"最新終値 ({pd.to_datetime(last_date).date()})",
            value=_format_price(last_close, currency),
            delta=delta_text,
            delta_color=delta_color,
        )

    with rsi_col:
        st.metric(
            label="RSI",
            value=rsi_display,
        )
    return last_close, rsi_value


def _estimate_price_for_rsi(current_price: float, current_rsi: float, target_rsi: float) -> float:
    if current_price is None or current_rsi is None or target_rsi <= 0:
        return float("nan")
    change = (target_rsi - current_rsi) / 100
    return current_price * (1 + change)


def render_alert_form(ticker: str, config, location: str) -> None:
    st.subheader("RSIアラートを追加")
    with st.form(key=f"alert-form-{location}"):
        st.write("RSIが指定閾値を下回ったら通知するアラートを登録します。")
        default_threshold = float(getattr(config, "rsi_alert_threshold", 40.0))
        threshold = st.number_input(
            "RSI閾値",
            min_value=0.0,
            max_value=100.0,
            value=default_threshold,
            step=1.0,
        )
        note = st.text_input("メモ", value="")
        submitted = st.form_submit_button("アラートを追加")
        if submitted:
            if not ticker:
                st.warning("先に銘柄を取得してください。")
                return
            add_alert(ticker=ticker, alert_type="RSI", threshold=threshold, note=note)
            st.success(f"{get_ticker_label(ticker)} のRSIアラートを登録しました。")


def render_alerts_page() -> None:
    st.header("登録済みアラート")
    alerts = load_alerts()
    if not alerts:
        st.info(
            "登録されたアラートはまだありません。ファンダメンタルまたはテクニカルビューから追加できます。"
        )
        return

    df = pd.DataFrame(alerts)
    df = df.drop(columns=["id", "note"], errors="ignore")
    current_data = []
    for ticker in df["ticker"].unique():
        price_df = _get_price_history(ticker)
        currency = _currency_for_ticker(ticker)
        if price_df.empty:
            current_data.append(
                {
                    "ticker": ticker,
                    "current_price": None,
                    "current_rsi": None,
                    "currency": currency,
                }
            )
            continue
        price_df = _append_rsi(price_df)
        latest_close = price_df.dropna(subset=["Close"])
        latest_rsi = price_df.dropna(subset=["RSI"])
        current_data.append(
            {
                "ticker": ticker,
                "current_price": latest_close.iloc[-1].get("Close")
                if not latest_close.empty
                else None,
                "current_rsi": latest_rsi.iloc[-1].get("RSI")
                if not latest_rsi.empty
                else None,
                "currency": currency,
            }
        )

    latest_df = pd.DataFrame(current_data)
    df = df.merge(latest_df, on="ticker", how="left")
    df["alert_price"] = _estimate_price_for_rsi_series(
        df["current_price"], df["current_rsi"], df["threshold"]
    )

    column_map = {
        "ticker": "銘柄",
        "type": "タイプ",
        "threshold": "アラートRSI",
        "current_price": "現在株価",
        "current_rsi": "現在RSI",
        "alert_price": "目標株価",
    }
    df = df.rename(columns=column_map)
    df["銘柄"] = df["銘柄"].map(get_ticker_label)
    df["現在株価"] = df.apply(
        lambda row: _format_price(row["現在株価"], row.get("currency", "JPY")),
        axis=1,
    )
    df["現在RSI"] = df["現在RSI"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "-")
    df["目標株価"] = df.apply(
        lambda row: _format_price(row["目標株価"], row.get("currency", "JPY")),
        axis=1,
    )
    st.dataframe(df[["銘柄", "タイプ", "アラートRSI", "現在株価", "現在RSI", "目標株価"]], use_container_width=True, hide_index=True)

    options = {
        f"{get_ticker_label(a['ticker'])} - {a['type']} <= {a['threshold']}": a["id"]
        for a in alerts
    }
    selected = st.selectbox("削除するアラート", list(options.keys()))
    if st.button("選択したアラートを削除"):
        delete_alert(options[selected])
        st.success("アラートを削除しました。再読込すると一覧に反映されます。")


def _append_rsi(price_df: pd.DataFrame) -> pd.DataFrame:
    return compute_price_rsi(price_df)


def _estimate_price_for_rsi_series(current_price, current_rsi, target_rsi):
    price = pd.to_numeric(current_price, errors="coerce")
    current = pd.to_numeric(current_rsi, errors="coerce")
    target = pd.to_numeric(target_rsi, errors="coerce")
    ratio = target / current
    ratio = ratio.where(current > 0)
    return price * ratio


def _currency_for_ticker(ticker: str) -> str:
    return "JPY" if is_jp_ticker(ticker) else "USD"


@st.cache_data(show_spinner=False)
def _get_price_history(ticker: str) -> pd.DataFrame:
    return download_price_history(ticker)


if __name__ == "__main__":
    main()
