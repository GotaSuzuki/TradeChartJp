"""アプリ設定を集中管理する。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    company_name: str = "TradeChart JP"
    email_address: str = "support@example.com"
    filings_years: int = 5
    cache_ttl_hours: int = 12
    download_dir: str = "data/raw_jp"
    tdnet_base_url: str = "https://www.release.tdnet.info/inbs"
    price_provider: str = "yfinance"
    line_channel_access_token: Optional[str] = None
    line_channel_secret: Optional[str] = None
    line_target_user_id: Optional[str] = None
    line_notifications_enabled: bool = True
    rsi_alert_threshold: float = 40.0

    @property
    def user_agent(self) -> str:
        return f"{self.company_name} {self.email_address}"


def get_config() -> AppConfig:
    defaults = AppConfig()
    return AppConfig(
        company_name=os.getenv("APP_COMPANY_NAME", defaults.company_name),
        email_address=os.getenv("APP_EMAIL_ADDRESS", defaults.email_address),
        filings_years=_int_env("APP_FILINGS_YEARS", defaults.filings_years),
        cache_ttl_hours=_int_env("APP_CACHE_TTL_HOURS", defaults.cache_ttl_hours),
        download_dir=os.getenv("APP_DOWNLOAD_DIR", defaults.download_dir),
        tdnet_base_url=os.getenv("TDNET_BASE_URL", defaults.tdnet_base_url),
        price_provider=os.getenv("PRICE_PROVIDER", defaults.price_provider),
        line_channel_access_token=_coalesce_env(
            ["CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_ACCESS_TOKEN"],
            defaults.line_channel_access_token,
        ),
        line_channel_secret=_coalesce_env(
            ["CHANNEL_SECRET", "LINE_CHANNEL_SECRET"],
            defaults.line_channel_secret,
        ),
        line_target_user_id=_coalesce_env(
            ["LINE_TARGET_USER_ID"],
            defaults.line_target_user_id,
        ),
        line_notifications_enabled=_bool_env(
            "LINE_NOTIFICATIONS_ENABLED", defaults.line_notifications_enabled
        ),
        rsi_alert_threshold=_float_env(
            "RSI_ALERT_THRESHOLD", defaults.rsi_alert_threshold
        ),
    )


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _coalesce_env(names, default):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default
