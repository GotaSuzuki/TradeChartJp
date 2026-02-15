"""Utility functions for managing alert definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from app.config import get_config
from app.market_data import normalize_ticker_for_display

try:  # Optional dependency for Supabase storage
    from supabase import Client, create_client  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    create_client = None  # type: ignore
    Client = None  # type: ignore

ALERTS_FILE = Path("data/alerts.json")
_SUPABASE_CLIENT: Optional[Client] = None


def load_alerts() -> List[Dict[str, str]]:
    client = _get_supabase_client()
    if client:
        try:
            response = client.table("alerts").select("*").execute()
            data = response.data or []
            normalized = _normalize_alert_list(data)
            _save_local_cache(normalized)
            return normalized
        except Exception:
            return []

    if not ALERTS_FILE.exists():
        return []
    try:
        with ALERTS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return _normalize_alert_list(data)


def save_alerts(alerts: List[Dict[str, str]]) -> None:
    client = _get_supabase_client()
    if client:
        # For Supabase we rely on add/delete operations; save() via file is fallback only
        return

    _save_local_cache(alerts)


def add_alert(*, ticker: str, alert_type: str, threshold: float, note: str = "") -> Dict[str, str]:
    normalized_ticker = normalize_ticker_for_display(ticker)
    alert = {
        "id": str(uuid4()),
        "ticker": normalized_ticker,
        "type": alert_type,
        "threshold": threshold,
        "note": note,
    }
    client = _get_supabase_client()
    if client:
        client.table("alerts").insert(alert).execute()
        return alert

    alerts = load_alerts()
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def delete_alert(alert_id: str) -> None:
    client = _get_supabase_client()
    if client:
        client.table("alerts").delete().eq("id", alert_id).execute()
        return

    alerts = [alert for alert in load_alerts() if alert.get("id") != alert_id]
    save_alerts(alerts)


def _get_supabase_client() -> Optional[Client]:
    global _SUPABASE_CLIENT
    if create_client is None:
        return None
    config = get_config()
    if not config.supabase_url or not config.supabase_service_role_key:
        return None
    if _SUPABASE_CLIENT is None:
        _SUPABASE_CLIENT = create_client(
            config.supabase_url,
            config.supabase_service_role_key,
        )
    return _SUPABASE_CLIENT


def _save_local_cache(alerts: List[Dict[str, str]]) -> None:
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


def _normalize_alert_list(raw_alerts) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    if not isinstance(raw_alerts, list):
        return normalized
    for alert in raw_alerts:
        if not isinstance(alert, dict):
            continue
        item = dict(alert)
        item["ticker"] = normalize_ticker_for_display(str(item.get("ticker", "")))
        normalized.append(item)
    return normalized
