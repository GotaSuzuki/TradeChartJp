"""Notification utilities for LINE Messaging API."""

from __future__ import annotations

from typing import Optional

import requests


class LineMessagingNotifier:
    API_URL = "https://api.line.me/v2/bot/message/push"

    def __init__(self, channel_access_token: str, target_user_id: str) -> None:
        if not channel_access_token:
            raise ValueError("channel_access_token is required")
        if not target_user_id:
            raise ValueError("target_user_id is required")
        self.channel_access_token = channel_access_token.strip()
        self.target_user_id = target_user_id.strip()

    def send(self, message: str) -> None:
        payload = {
            "to": self.target_user_id,
            "messages": [
                {
                    "type": "text",
                    "text": message,
                }
            ],
        }
        response = requests.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.channel_access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
