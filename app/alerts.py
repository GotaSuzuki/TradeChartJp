"""Utility functions for managing alert definitions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from uuid import uuid4

ALERTS_FILE = Path("data/alerts.json")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY"
)
SUPABASE_TABLE = os.getenv("SUPABASE_ALERTS_TABLE", "alertJP")
_SUPABASE_CLIENT = None


def _supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _get_supabase_client():
    global _SUPABASE_CLIENT
    if not _supabase_enabled():
        return None
    if _SUPABASE_CLIENT is None:
        try:
            from supabase import create_client
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Supabase support requires the 'supabase' package."
            ) from exc

        _SUPABASE_CLIENT = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _SUPABASE_CLIENT


def load_alerts() -> List[Dict[str, str]]:
    if _supabase_enabled():
        client = _get_supabase_client()
        try:
            response = client.table(SUPABASE_TABLE).select("*").execute()
        except Exception:
            return []
        return _normalize_supabase_rows(response.data or [])

    if not ALERTS_FILE.exists():
        return []
    try:
        with ALERTS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return data


def save_alerts(alerts: List[Dict[str, str]]) -> None:
    if _supabase_enabled():
        # Supabase operations are handled per action; bulk save is not needed.
        return
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


def add_alert(*, ticker: str, alert_type: str, threshold: float, note: str = "") -> Dict[str, str]:
    if _supabase_enabled():
        client = _get_supabase_client()
        payload = {
            "ticker": ticker.upper(),
            "type": alert_type,
            "threshold": threshold,
            "note": note,
        }
        response = (
            client.table(SUPABASE_TABLE)
            .insert(payload)
            .select("*")
            .execute()
        )
        inserted = response.data[0] if response.data else payload
        return _normalize_supabase_rows([inserted])[0]

    alert = {
        "id": str(uuid4()),
        "ticker": ticker.upper(),
        "type": alert_type,
        "threshold": threshold,
        "note": note,
    }
    alerts = load_alerts()
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def delete_alert(alert_id: str) -> None:
    if _supabase_enabled():
        client = _get_supabase_client()
        client.table(SUPABASE_TABLE).delete().eq("id", alert_id).execute()
        return
    alerts = [alert for alert in load_alerts() if alert.get("id") != alert_id]
    save_alerts(alerts)


def update_alert(alert_id: str, **changes) -> bool:
    if _supabase_enabled():
        client = _get_supabase_client()
        payload = {key: value for key, value in changes.items() if value is not None}
        if not payload:
            return False
        response = (
            client.table(SUPABASE_TABLE)
            .update(payload)
            .eq("id", alert_id)
            .select("*")
            .execute()
        )
        return bool(response.data)

    alerts = load_alerts()
    updated = False
    for alert in alerts:
        if alert.get("id") == alert_id:
            for key, value in changes.items():
                if value is not None:
                    alert[key] = value
            updated = True
            break
    if updated:
        save_alerts(alerts)
    return updated


def _normalize_supabase_rows(rows: List[Dict[str, object]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for row in rows:
        row_id = row.get("id")
        normalized.append(
            {
                "id": str(row_id) if row_id is not None else "",
                "ticker": str(row.get("ticker", "")),
                "type": str(row.get("type", "")),
                "threshold": row.get("threshold"),
                "note": row.get("note", ""),
            }
        )
    return normalized


def _to_supabase_id(value: Optional[str]):
    return value
