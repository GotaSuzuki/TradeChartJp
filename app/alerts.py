"""Utility functions for managing alert definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict
from uuid import uuid4

ALERTS_FILE = Path("data/alerts.json")


def load_alerts() -> List[Dict[str, str]]:
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
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


def add_alert(*, ticker: str, alert_type: str, threshold: float, note: str = "") -> Dict[str, str]:
    alerts = load_alerts()
    alert = {
        "id": str(uuid4()),
        "ticker": ticker.upper(),
        "type": alert_type,
        "threshold": threshold,
        "note": note,
    }
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def delete_alert(alert_id: str) -> None:
    alerts = [alert for alert in load_alerts() if alert.get("id") != alert_id]
    save_alerts(alerts)


def update_alert(alert_id: str, **changes) -> bool:
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
