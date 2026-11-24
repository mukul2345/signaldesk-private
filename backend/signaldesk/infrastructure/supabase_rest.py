"""Small PostgREST adapter for stateless jobs and serverless handlers."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import httpx


class CloudConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupabaseRest:
    url: str
    api_key: str
    bearer_token: str
    timeout_seconds: float = 20

    @classmethod
    def service(cls) -> "SupabaseRest":
        return cls._from_environment("SUPABASE_SECRET_KEY")

    @classmethod
    def user(cls, bearer_token: str) -> "SupabaseRest":
        client = cls._from_environment("SUPABASE_PUBLISHABLE_KEY")
        return cls(client.url, client.api_key, bearer_token)

    @classmethod
    def _from_environment(cls, key_name: str) -> "SupabaseRest":
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get(key_name, "")
        if not url or not key:
            raise CloudConfigurationError(f"SUPABASE_URL and {key_name} are required")
        return cls(url, key, key)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, str]] = None,
        json: Any = None,
        prefer: Optional[str] = None,
    ) -> Any:
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        response = httpx.request(
            method,
            f"{self.url}/rest/v1/{path.lstrip('/')}",
            params=params,
            json=json,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def auth_user(self) -> dict[str, Any]:
        response = httpx.get(
            f"{self.url}/auth/v1/user",
            headers={"apikey": self.api_key, "Authorization": f"Bearer {self.bearer_token}"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def select(self, table: str, params: Mapping[str, str]) -> list[dict[str, Any]]:
        result = self.request("GET", table, params=params)
        return result if isinstance(result, list) else []

    def insert(self, table: str, values: Mapping[str, Any]) -> list[dict[str, Any]]:
        result = self.request("POST", table, json=values, prefer="return=representation")
        return result if isinstance(result, list) else []

    def upsert(
        self, table: str, values: Any, *, on_conflict: str
    ) -> list[dict[str, Any]]:
        result = self.request(
            "POST",
            table,
            params={"on_conflict": on_conflict},
            json=values,
            prefer="resolution=merge-duplicates,return=representation",
        )
        return result if isinstance(result, list) else []

    def update(self, table: str, values: Mapping[str, Any], params: Mapping[str, str]) -> list[dict[str, Any]]:
        result = self.request("PATCH", table, params=params, json=values, prefer="return=representation")
        return result if isinstance(result, list) else []

    def delete(self, table: str, params: Mapping[str, str]) -> None:
        self.request("DELETE", table, params=params, prefer="return=minimal")

    def count(self, table: str) -> int:
        response = httpx.get(
            f"{self.url}/rest/v1/{table}", params={"select": "id", "limit": "1"},
            headers={"apikey": self.api_key, "Authorization": f"Bearer {self.bearer_token}", "Prefer": "count=exact", "Range": "0-0"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content_range = response.headers.get("content-range", "0-0/0")
        return int(content_range.rsplit("/", 1)[-1])
