"""設定値を一元管理するモジュール。"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    company_name: str = "Gota Suzuki"
    email_address: str = "go.baseball.0408@icloud.com"
    filings_years: int = 5
    cache_ttl_hours: int = 12
    download_dir: str = "data/raw"
    line_channel_access_token: Optional[str] = None
    line_channel_secret: Optional[str] = None
    line_target_user_id: Optional[str] = None
    rsi_alert_threshold: float = 80.0
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    alpaca_api_key_id: Optional[str] = None
    alpaca_api_secret_key: Optional[str] = None
    alpaca_data_feed: str = "iex"
    alpaca_data_base_url: str = "https://data.alpaca.markets"

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
        line_channel_access_token=_clean_secret(
            _env_first(
                ["LINE_CHANNEL_ACCESS_TOKEN", "CHANNEL_ACCESS_TOKEN"],
                defaults.line_channel_access_token,
            )
        ),
        line_channel_secret=_clean_secret(
            _env_first(
                ["LINE_CHANNEL_SECRET", "CHANNEL_SECRET"],
                defaults.line_channel_secret,
            )
        ),
        line_target_user_id=os.getenv(
            "LINE_TARGET_USER_ID", defaults.line_target_user_id
        ),
        rsi_alert_threshold=_float_env(
            "RSI_ALERT_THRESHOLD", defaults.rsi_alert_threshold
        ),
        supabase_url=os.getenv("SUPABASE_URL", defaults.supabase_url),
        supabase_service_role_key=_clean_secret(
            os.getenv("SUPABASE_SERVICE_ROLE_KEY", defaults.supabase_service_role_key)
        ),
        alpaca_api_key_id=_clean_secret(
            os.getenv("ALPACA_API_KEY_ID", defaults.alpaca_api_key_id)
        ),
        alpaca_api_secret_key=_clean_secret(
            os.getenv("ALPACA_API_SECRET_KEY", defaults.alpaca_api_secret_key)
        ),
        alpaca_data_feed=os.getenv("ALPACA_DATA_FEED", defaults.alpaca_data_feed),
        alpaca_data_base_url=os.getenv(
            "ALPACA_DATA_BASE_URL", defaults.alpaca_data_base_url
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


def _env_first(names, default=None):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _clean_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.startswith("***"):
        return None
    return cleaned
