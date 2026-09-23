"""Thin OpenAI-compatible LLM client.

Reads configuration from environment (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL).
Returns ``None`` on any failure so callers can fall back to deterministic logic.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx


class LLMUnavailable(RuntimeError):
    """Raised when the LLM endpoint is not configured or unreachable."""


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or ""
        self.model = model or os.environ.get("LLM_MODEL") or ""
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.api_key != "replace_me" and self.model and self.model != "replace_me")

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        if not self.configured:
            raise LLMUnavailable("LLM not configured")
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMUnavailable(f"unexpected response: {data}") from exc
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMUnavailable(f"non-JSON response: {content[:200]}") from exc