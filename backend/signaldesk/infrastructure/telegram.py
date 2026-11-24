from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class TelegramBot:
    token: str

    @classmethod
    def from_environment(cls) -> "TelegramBot":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        return cls(token)

    def send(self, chat_id: int, text: str) -> dict[str, Any]:
        response = httpx.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
