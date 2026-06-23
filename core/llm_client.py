from __future__ import annotations

from dataclasses import dataclass
import json
from types import SimpleNamespace
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
        client = self._create_client()
        payload: dict[str, object] = {
            "model": self.model_name,
            "max_tokens": self.max_output_tokens,
            "system": system,
            "messages": [
                {"role": "user", "content": user},
            ],
        }
        if self._supports_temperature():
            payload["temperature"] = self.temperature
        try:
            response = client.messages.create(**payload)
        except Exception as exc:  # pragma: no cover - SDK/network failure depends on remote API
            raise ConnectionError(f"failed to reach Anthropic API at {self.base_url}: {exc}") from exc
        content_blocks = getattr(response, "content", []) or []
        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
        content = "".join(text_parts).strip()
        if not content:
            raise ValueError("empty response from Anthropic")
        usage_block = getattr(response, "usage", None) or SimpleNamespace()
        usage = AnthropicUsage(
            prompt_tokens=int(getattr(usage_block, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(usage_block, "output_tokens", 0) or 0),
        )
        return AnthropicChatResult(content=content, usage=usage)

    def _create_client(self):
        try:
            import anthropic as anthropic_sdk
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency resolution failure
            raise ImportError(
                "anthropic package is required for Claude backend; install it with `uv add anthropic`"
            ) from exc
        return anthropic_sdk.Anthropic(api_key=self.api_key, base_url=self.base_url)

    def _supports_temperature(self) -> bool:
        return not self.model_name.startswith("claude-opus-4")
