from __future__ import annotations

from dataclasses import dataclass
import os

from core.evaluation_agent import EvaluationAgent
from core.generator import ReportGenerator
from core.llm_client import OllamaClient


@dataclass(frozen=True)
class RuntimeConfig:
    backend: str = "auto"
    model_name: str = "llama3.2:3b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 120.0
    num_ctx: int = 4096
    temperature: float = 0.2

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(
            backend=os.getenv("EVAL_LOOP_BACKEND", "auto").strip().lower(),
            model_name=os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip(),
            timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "4096")),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.2")),
        )

    def normalized_backend(self) -> str:
        backend = self.backend.strip().lower()
        if backend not in {"auto", "ollama", "heuristic"}:
            return "auto"
        return backend


@dataclass(frozen=True)
class RuntimeServices:
    generator: ReportGenerator
    evaluator: EvaluationAgent
    backend_label: str


def build_services(config: RuntimeConfig | None = None) -> RuntimeServices:
    config = config or RuntimeConfig.from_env()
    backend = config.normalized_backend()
    client = None
    backend_label = "heuristic"
    if backend in {"auto", "ollama"}:
        candidate = OllamaClient(
            base_url=config.ollama_base_url,
            model_name=config.model_name,
            timeout_seconds=config.timeout_seconds,
            num_ctx=config.num_ctx,
            temperature=config.temperature,
        )
        if backend == "ollama" or candidate.is_available():
            client = candidate
            backend_label = f"ollama:{config.model_name}"
    return RuntimeServices(
        generator=ReportGenerator(llm_client=client, model_name=config.model_name),
        evaluator=EvaluationAgent(llm_client=client, model_name=config.model_name),
        backend_label=backend_label,
    )
