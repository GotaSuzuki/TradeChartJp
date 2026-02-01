"""TDnet 公開情報の簡易クライアント。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import requests


class TdnetClient:
    def __init__(
        self,
        base_url: str,
        *,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def fetch_recent_events(
        self,
        code: str,
        *,
        days: int = 30,
    ) -> List[Dict[str, str]]:
        target_dates = [date.today() - timedelta(days=offset) for offset in range(days)]
        events: List[Dict[str, str]] = []
        for day in target_dates:
            file_name = day.strftime("I_main_00_%Y%m%d.json")
            url = f"{self.base_url}/{file_name}"
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code != 200:
                    continue
                data = response.json()
            except Exception:
                continue
            rows = data.get("items") or data
            for row in rows:
                if str(row.get("code")) != str(code):
                    continue
                timestamp = row.get("date") or row.get("tdnet_date")
                events.append(
                    {
                        "title": row.get("title", ""),
                        "timestamp": timestamp,
                        "url": row.get("url", ""),
                    }
                )
        events.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        return events
