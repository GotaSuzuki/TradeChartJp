"""TradeChart JP Streamlit アプリ。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.alerts import add_alert, delete_alert, load_alerts, update_alert
from app.cache import DataCache
from app.clients.edinet_client import EdinetClient
from app.clients.price_service import PriceService
from app.clients.tdnet_client import TdnetClient
from app.config import get_config
from app.market_data import compute_rsi as compute_price_rsi
from app.metrics import compute_cagr, compute_yoy, to_dataframe
from app.services.filings_fetcher_jp import FilingsFetcherJP

METRIC_LABELS = {
    "revenue": "売上高",
    "operating_income": "営業利益",
    "net_income": "当期純利益",
    "operating_cash_flow": "営業キャッシュフロー",
}

TECH_PERIOD_OPTIONS = {
    "3ヶ月": 90,
    "6ヶ月": 180,
    "1年": 365,
}


@st.cache_resource(show_spinner=False)
def _init_services():
    config = get_config()
    cache = DataCache("data/cache")
    edinet = EdinetClient(user_agent=config.user_agent, download_dir=config.download_dir)
    fetcher = FilingsFetcherJP(
        edinet,
        cache=cache,
        cache_ttl_hours=config.cache_ttl_hours,
    )
    tdnet = TdnetClient(config.tdnet_base_url)
    return config, fetcher, tdnet


def main() -> None:
    st.set_page_config(page_title="TradeChart JP", layout="wide")
    config, fetcher, tdnet = _init_services()
    st.title("TradeChart JP")
    st.caption("EDINET/TDnet のデータで日本株を可視化")

    with st.sidebar:
        st.header("パラメータ")
        code_input = st.text_input("証券コード", value="7203")
        years = st.slider("取得年数", 1, 10, value=config.filings_years)
        fetch_clicked = st.button("財務データを取得", use_container_width=True)
        tech_period_label = st.selectbox(
            "テクニカル期間",
            list(TECH_PERIOD_OPTIONS.keys()),
            index=1,
        )

    code = code_input.strip()
    view = st.radio(
        "表示ビュー",
        ("ファンダメンタル", "テクニカル", "タイムライン", "アラート"),
        horizontal=True,
    )

    if fetch_clicked:
        if not code:
            st.warning("証券コードを入力してください。")
        else:
            with st.spinner("EDINET から取得中..."):
                try:
                    metrics = fetcher.fetch_recent_filings(
                        code,
                        years=years,
                    )
                except Exception as exc:  # pragma: no cover - UI 通知
                    st.error(f"取得に失敗しました: {exc}")
                    metrics = None

            if not metrics:
                st.info("データを取得できませんでした。")
            else:
                yoy = compute_yoy(metrics)
                cagr_map = compute_cagr(yoy)
                df = to_dataframe(yoy)
                st.session_state["financial_df"] = df
                st.session_state["cagr_map"] = cagr_map
                st.session_state["selected_code"] = code

    stored_df = st.session_state.get("financial_df")
    stored_cagr = st.session_state.get("cagr_map")
    stored_code = st.session_state.get("selected_code", code)

    if view == "ファンダメンタル":
        if stored_df is None or stored_cagr is None:
            st.info("左のフォームで財務データを取得してください。")
        else:
            render_metric_panels(stored_df, stored_cagr)
            render_alert_form(stored_code, config, location="fundamental")
    elif view == "テクニカル":
        render_technical_section(stored_code, tech_period_label, config)
        render_alert_form(stored_code, config, location="technical")
    elif view == "タイムライン":
        render_timeline_view(stored_code, tdnet)
    else:
        render_alerts_page()


def render_metric_panels(df: pd.DataFrame, cagr_map: Dict[str, Optional[float]]):
    st.subheader("主要指標")
    cols = st.columns(len(METRIC_LABELS))
    for idx, (metric, label) in enumerate(METRIC_LABELS.items()):
        metric_df = df[df["metric"] == metric].dropna(subset=["value"])
        if metric_df.empty:
            cols[idx].info("データなし")
            continue
        metric_df = metric_df.sort_values("year")
        latest = metric_df.iloc[-1]
        value_text = _format_value(latest["value"], latest.get("unit"))
        year = int(latest["year"])
        cagr = cagr_map.get(metric)
        delta, delta_color = _format_cagr_delta(cagr)

        max_abs = metric_df["value"].abs().max()
        scale, suffix = _determine_scale(max_abs)
        metric_df["value_m"] = metric_df["value"] / scale
        unit_series = metric_df["unit"].dropna()
        unit = unit_series.iloc[-1] if not unit_series.empty else "JPY"

        with cols[idx]:
            st.metric(
                label=f"{label} ({year})",
                value=value_text,
                delta=delta,
                delta_color=delta_color,
            )
            fig = px.line(
                metric_df,
                x="year",
                y="value_m",
                markers=True,
                labels={"year": "年度", "value_m": _build_axis_label(label, unit, suffix)},
            )
            fig.update_layout(margin=dict(l=6, r=6, t=20, b=6), height=260)
            st.plotly_chart(fig, use_container_width=True)


def render_technical_section(code: str, period_label: str, config) -> None:
    st.subheader("テクニカル")
    if not code:
        st.info("証券コードを入力してください。")
        return
    price_df = _get_price_history(code, config.price_provider)
    if price_df is None or price_df.empty:
        st.info("価格データを取得できませんでした。")
        return

    price_df = price_df.sort_values("Date")
    price_df = _append_rsi(price_df)
    latest_price, latest_rsi = _render_latest_price(price_df)
    price_df["MA20"] = price_df["Close"].rolling(20).mean()
    price_df["MA50"] = price_df["Close"].rolling(50).mean()
    price_df["MA200"] = price_df["Close"].rolling(200).mean()

    days = TECH_PERIOD_OPTIONS.get(period_label, 180)
    last_date = pd.to_datetime(price_df["Date"]).max()
    cutoff = last_date - pd.Timedelta(days=days)
    recent = price_df[price_df["Date"] >= cutoff]

    display_cols = [col for col in ["Close", "MA20", "MA50", "MA200"] if col in recent.columns]
    melted = recent.melt(
        id_vars="Date",
        value_vars=display_cols,
        var_name="Series",
        value_name="Price",
    )
    if "RSI" in recent.columns:
        rsi_lookup = recent.set_index("Date")["RSI"]
        melted["RSI"] = melted["Date"].map(rsi_lookup)

    fig = px.line(
        melted,
        x="Date",
        y="Price",
        color="Series",
        labels={"Date": "日付", "Price": "価格 (JPY)", "Series": "系列"},
    )
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=320, hovermode="x")
    rsi_map = {}
    if "RSI" in melted:
        for series in melted["Series"].unique():
            rsi_map[series] = (
                melted[melted["Series"] == series]["RSI"].to_numpy()
            )
    has_rsi_line = "RSI" in recent.columns
    for trace in fig.data:
        name = trace.name
        if name == "Close":
            rsi_values = rsi_map.get(name)
            if rsi_values is not None and rsi_values.size:
                trace.customdata = rsi_values.reshape(-1, 1)
                trace.hovertemplate = (
                    "日付 %{x|%Y-%m-%d}<br>株価 %{y:,.2f} 円"
                    + "<br>RSI %{customdata[0]:.1f}"
                    + "<extra></extra>"
                )
            else:
                trace.hovertemplate = (
                    "日付 %{x|%Y-%m-%d}<br>株価 %{y:,.2f} 円" + "<extra></extra>"
                )
        else:
            trace.hoverinfo = "skip"
            trace.hovertemplate = None

    if has_rsi_line:
        fig.add_trace(
            go.Scatter(
                x=recent["Date"],
                y=recent["RSI"],
                name="RSI",
                mode="lines",
                line=dict(color="#800080", width=2, dash="dash"),
                yaxis="y2",
                hovertemplate="日付 %{x|%Y-%m-%d}<br>RSI %{y:.1f}<extra></extra>",
            )
        )
        fig.update_layout(
            yaxis2=dict(
                title="RSI",
                overlaying="y",
                side="right",
                range=[0, 100],
                showgrid=False,
            )
        )
    st.plotly_chart(fig, use_container_width=True)

    if latest_price is not None and latest_rsi is not None:
        st.caption(f"最新終値: {latest_price:,.2f} 円 / RSI: {latest_rsi:.1f}")


def render_timeline_view(code: str, tdnet: TdnetClient) -> None:
    st.subheader("開示タイムライン")
    if not code:
        st.info("証券コードを入力してください。")
        return
    with st.spinner("TDnet から取得中..."):
        events = tdnet.fetch_recent_events(code)
    if not events:
        st.info("直近の開示情報がありません。")
        return
    for event in events:
        ts = event.get("timestamp") or ""
        title = event.get("title") or ""
        url = event.get("url") or ""
        if url:
            st.markdown(f"**{ts}** - [{title}]({url})")
        else:
            st.markdown(f"**{ts}** - {title}")


def render_alert_form(ticker: str, config, location: str) -> None:
    st.subheader("RSIアラートを追加")
    with st.form(key=f"alert-form-{location}"):
        st.write("RSIが閾値を下回ったら通知します。")
        threshold = st.number_input(
            "RSI閾値",
            min_value=0.0,
            max_value=100.0,
            value=float(getattr(config, "rsi_alert_threshold", 40.0)),
            step=1.0,
        )
        note = st.text_input("メモ", value="")
        submitted = st.form_submit_button("アラートを追加")
        if submitted:
            if not ticker:
                st.warning("先に証券コードでデータ取得してください。")
            else:
                add_alert(
                    ticker=ticker,
                    alert_type="RSI",
                    threshold=threshold,
                    note=note,
                )
                st.success(f"{ticker} のRSIアラートを登録しました。")


def render_alerts_page() -> None:
    st.header("登録済みアラート")
    alerts = load_alerts()
    if not alerts:
        st.info("アラートはまだありません。")
        return
    df = pd.DataFrame(alerts)
    df = df.drop(columns=["note"], errors="ignore")
    company_map = _load_company_names()
    df["銘柄"] = df["ticker"].map(lambda code: company_map.get(code, code))
    display_cols = [
        "銘柄",
        "ticker",
        "type",
        "threshold",
    ]
    df = df[display_cols]

    latest_data = []
    unique_tickers = df["ticker"].unique()
    for ticker in unique_tickers:
        price_df = _get_price_history(ticker, "yfinance")
        if price_df.empty:
            latest_data.append({"ticker": ticker, "current_price": None, "current_rsi": None})
            continue
        price_df = _append_rsi(price_df)
        latest_price = price_df.dropna(subset=["Close"]).iloc[-1]["Close"] if not price_df.dropna(subset=["Close"]).empty else None
        latest_rsi_df = price_df.dropna(subset=["RSI"])
        latest_rsi = latest_rsi_df.iloc[-1]["RSI"] if not latest_rsi_df.empty else None
        latest_data.append(
            {
                "ticker": ticker,
                "current_price": latest_price,
                "current_rsi": latest_rsi,
            }
        )

    latest_df = pd.DataFrame(latest_data)
    merged = df.merge(latest_df, on="ticker", how="left")
    merged["目標株価"] = _estimate_price_for_rsi_series(
        merged["current_price"], merged["current_rsi"], merged["threshold"]
    )
    display_mapping = {
        "ticker": "銘柄コード",
        "type": "タイプ",
        "current_price": "現在株価",
        "current_rsi": "現在RSI",
        "threshold": "アラートRSI",
        "目標株価": "目標株価",
    }
    display_df = merged.rename(columns=display_mapping)
    display_df["現在株価"] = display_df["現在株価"].map(lambda x: f"{x:,.2f}" if pd.notna(x) else "-")
    display_df["現在RSI"] = display_df["現在RSI"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "-")
    display_df["アラートRSI"] = display_df["アラートRSI"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "-")
    display_df["目標株価"] = display_df["目標株価"].map(lambda x: f"{x:,.2f}" if pd.notna(x) else "-")
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    option_tuples = [
        (
            f"{company_map.get(a['ticker'], a['ticker'])} ({a['ticker']}) - {a['type']} <= {a['threshold']}",
            a["id"],
        )
        for a in alerts
    ]
    labels = [label for label, _ in option_tuples]
    ids = {label: alert_id for label, alert_id in option_tuples}

    if labels:
        edit_label = st.selectbox("編集するアラート", labels, key="edit-alert")
        selected_id = ids[edit_label]
        selected_alert = next((a for a in alerts if a.get("id") == selected_id), None)
        if selected_alert:
            with st.form("edit-alert-form"):
                new_ticker = st.text_input(
                    "証券コード",
                    value=selected_alert.get("ticker", ""),
                )
                new_threshold = st.number_input(
                    "RSI閾値を編集",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(selected_alert.get("threshold", 40.0)),
                    step=1.0,
                )
                submitted = st.form_submit_button("アラートを更新")
                if submitted:
                    trimmed = new_ticker.strip()
                    if not trimmed:
                        st.warning("証券コードを入力してください。")
                    elif update_alert(
                        selected_id,
                        ticker=trimmed,
                        threshold=float(new_threshold),
                    ):
                        st.success("アラートを更新しました。再読込で反映されます。")
                    else:
                        st.error("更新に失敗しました。")

    delete_label = st.selectbox("削除するアラート", labels, key="delete-alert")
    if st.button("選択したアラートを削除"):
        delete_alert(ids[delete_label])
        st.success("アラートを削除しました。再読込で反映されます。")


def _load_company_names() -> Dict[str, str]:
    mapping_path = Path("data/mappings/companies.csv")
    if not mapping_path.exists():
        return {}
    data = pd.read_csv(mapping_path)
    return dict(zip(data["code"].astype(str), data["name"]))


def _get_price_history(code: str, provider: str) -> pd.DataFrame:
    try:
        service = PriceService(provider=provider)
        return service.download(code).dataframe
    except Exception:
        return pd.DataFrame()


def _append_rsi(price_df: pd.DataFrame) -> pd.DataFrame:
    return compute_price_rsi(price_df)


def _estimate_price_for_rsi_series(current_price, current_rsi, target_rsi):
    try:
        return current_price * (target_rsi / current_rsi)
    except Exception:
        return float("nan")


def _render_latest_price(price_df: pd.DataFrame):
    clean = price_df.dropna(subset=["Close"]) if not price_df.empty else pd.DataFrame()
    if clean.empty:
        return None, None
    last_row = clean.iloc[-1]
    last_close = last_row["Close"]
    last_date = pd.to_datetime(last_row["Date"]).date()
    try:
        prev_close = clean.iloc[-2]["Close"]
        delta = last_close - prev_close
    except IndexError:
        delta = None
    delta_text = f"{delta:+.2f}" if delta is not None else None
    delta_color = "normal" if (delta or 0) >= 0 else "inverse"
    rsi_value = last_row.get("RSI")
    price_col, rsi_col = st.columns([2, 1])
    with price_col:
        st.metric(
            label=f"最新終値 ({last_date})",
            value=f"{last_close:,.2f} 円",
            delta=delta_text,
            delta_color=delta_color,
        )
    with rsi_col:
        st.metric(
            label="RSI",
            value=f"{rsi_value:.1f}" if rsi_value is not None else "N/A",
        )
    return last_close, rsi_value


def _format_value(value, unit):
    if value is None:
        return "N/A"
    scale, suffix = _determine_scale(abs(value))
    scaled_value = value / scale
    unit_label = _build_unit_label(unit, suffix)
    return f"{scaled_value:,.2f} {unit_label}".strip()


def _format_cagr_delta(cagr):
    if cagr is None:
        return "CAGR N/A", "off"
    value = cagr * 100
    color = "normal" if value >= 0 else "inverse"
    return f"CAGR {value:+.1f}%", color


def _determine_scale(value):
    thresholds = [
        (1_000_000_000_000, "兆"),
        (1_000_000_000, "億"),
        (1_000_000, "百万"),
        (1_000, "千"),
    ]
    for threshold, label in thresholds:
        if value >= threshold:
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
    label = _build_unit_label(unit, suffix)
    return f"{metric_label} ({label})" if label else metric_label


if __name__ == "__main__":
    main()
