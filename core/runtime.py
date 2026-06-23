from __future__ import annotations

from dataclasses import dataclass
import os

from core.evaluation_agent import EvaluationAgent
from core.generator import ReportGenerator
from core.llm_client import OllamaClient


@dataclass(frozen=True)
class RuntimeConfig:
    backend: str = "auto"
    model_name: str = "qwen2.5:3b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 120.0
    num_ctx: int = 4096
    temperature: float = 0.2
    max_runtime_seconds: float = 300.0
    max_total_tokens: int = 12000

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(
            backend=os.getenv("EVAL_LOOP_BACKEND", "auto").strip().lower(),
            model_name=os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip(),
            timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "4096")),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.2")),
            max_runtime_seconds=float(os.getenv("EVAL_LOOP_MAX_RUNTIME_SECONDS", "300")),
            max_total_tokens=int(os.getenv("EVAL_LOOP_MAX_TOTAL_TOKENS", "12000")),
        )

    def normalized_backend(self) -> str:
        backend = self.backend.strip().lower()
        if backend not in {"auto", "ollama"}:
            raise ValueError(f"unsupported backend: {backend}")
        return backend


@dataclass(frozen=True)
class RuntimeServices:
    generator: ReportGenerator
    evaluator: EvaluationAgent
    backend_label: str


def build_services(config: RuntimeConfig | None = None) -> RuntimeServices:
    config = config or RuntimeConfig.from_env()
    backend = config.normalized_backend()
    candidate = OllamaClient(
        base_url=config.ollama_base_url,
        model_name=config.model_name,
        timeout_seconds=config.timeout_seconds,
        num_ctx=config.num_ctx,
        temperature=config.temperature,
    )
    if not candidate.is_available():
        raise ConnectionError(f"failed to reach Ollama at {config.ollama_base_url}")
    client = candidate
    backend_label = f"ollama:{config.model_name}"
    return RuntimeServices(
        generator=ReportGenerator(llm_client=client, model_name=config.model_name),
        evaluator=EvaluationAgent(llm_client=client, model_name=config.model_name),
        backend_label=backend_label,
    )
