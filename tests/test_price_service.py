import pandas as pd

from app.clients.price_service import PriceService


def test_to_yfinance_symbol_appends_suffix():
    service = PriceService()
    assert service._to_yfinance_symbol("7203") == "7203.T"
    assert service._to_yfinance_symbol("6758.T") == "6758.T"


def test_download_uses_yfinance(monkeypatch):
    frame = pd.DataFrame({
        "Date": pd.date_range("2023-01-01", periods=2, freq="D"),
        "Close": [100, 110],
    })

    def fake_download(ticker, **kwargs):  # type: ignore[override]
        assert ticker == "7203.T"
        return frame.set_index("Date")

    monkeypatch.setattr("yfinance.download", fake_download)
    service = PriceService()
    result = service.download("7203")
    assert not result.dataframe.empty
    assert result.dataframe.iloc[-1]["Close"] == 110
