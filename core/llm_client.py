from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class OllamaUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class OllamaChatResult:
    content: str
    usage: OllamaUsage


@dataclass(frozen=True)
class AnthropicUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class AnthropicChatResult:
    content: str
    usage: AnthropicUsage


@dataclass(frozen=True)
class OllamaClient:
    base_url: str
    model_name: str
    timeout_seconds: float = 120.0
    num_ctx: int = 4096
    temperature: float = 0.2

    def is_available(self) -> bool:
        try:
            self._request_json("GET", "/api/tags")
        except Exception:
            return False
        return True

    def chat(self, *, system: str, user: str) -> str:
        return self.chat_with_usage(system=system, user=user).content

    def chat_with_usage(self, *, system: str, user: str) -> OllamaChatResult:
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
        usage = OllamaUsage(
            prompt_tokens=int(response.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(response.get("eval_count", 0) or 0),
        )
        return OllamaChatResult(content=content.strip(), usage=usage)

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
            reason = getattr(exc, "reason", exc)
            raise ConnectionError(f"failed to reach Ollama at {self.base_url}: {reason}") from exc


@dataclass(frozen=True)
class AnthropicClient:
    api_key: str
    model_name: str
    base_url: str = "https://api.anthropic.com"
    timeout_seconds: float = 120.0
    temperature: float = 0.2
    max_output_tokens: int = 4096

    def is_available(self) -> bool:
        return bool(self.api_key.strip())

    def chat(self, *, system: str, user: str) -> str:
        return self.chat_with_usage(system=system, user=user).content

    def chat_with_usage(self, *, system: str, user: str) -> AnthropicChatResult:
        payload = {
            "model": self.model_name,
            "max_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "system": system,
            "messages": [
                {"role": "user", "content": user},
            ],
        }
        response = self._request_json("POST", "/v1/messages", payload)
        content_blocks = response.get("content") or []
        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        content = "".join(text_parts).strip()
        if not content:
            raise ValueError("empty response from Anthropic")
        usage_block = response.get("usage") or {}
        usage = AnthropicUsage(
            prompt_tokens=int(usage_block.get("input_tokens", 0) or 0),
            completion_tokens=int(usage_block.get("output_tokens", 0) or 0),
        )
        return AnthropicChatResult(content=content, usage=usage)

    def _request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url.rstrip('/')}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as exc:  # pragma: no cover - network failure depends on remote API
            reason = getattr(exc, "reason", exc)
            raise ConnectionError(f"failed to reach Anthropic API at {self.base_url}: {reason}") from exc
