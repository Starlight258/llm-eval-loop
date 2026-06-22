from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class OllamaClient:
    base_url: str
    model_name: str
    timeout_seconds: float = 120.0
    num_ctx: int = 8192
    temperature: float = 0.2

    def is_available(self) -> bool:
        try:
            self._request_json("GET", "/api/tags")
        except Exception:
            return False
        return True

    def chat(self, *, system: str, user: str) -> str:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "num_ctx": self.num_ctx,
                "temperature": self.temperature,
            },
        }
        response = self._request_json("POST", "/api/chat", payload)
        message = response.get("message") or {}
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty response from Ollama")
        return content.strip()

    def _request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url.rstrip('/')}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as exc:  # pragma: no cover - network failure depends on local daemon
            raise ConnectionError(f"failed to reach Ollama at {self.base_url}") from exc

