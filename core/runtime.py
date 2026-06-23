from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path

from core.evaluation_agent import EvaluationAgent
from core.generator import ReportGenerator
from core.llm_client import AnthropicClient, OllamaClient


logger = logging.getLogger(__name__)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class RuntimeConfig:
    backend: str = "auto"
    model_name: str = "qwen2.5:3b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-sonnet-4-6"
    timeout_seconds: float = 120.0
    num_ctx: int = 4096
    temperature: float = 0.2
    max_output_tokens: int = 4096
    max_runtime_seconds: float = 300.0
    max_total_tokens: int = 12000

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        env_file = os.getenv("EVAL_ENV_FILE", "").strip()
        if env_file:
            _load_env_file(Path(env_file).expanduser())
        else:
            _load_env_file(Path(__file__).resolve().parents[1] / ".env")
        return cls(
            backend=os.getenv("EVAL_LOOP_BACKEND", "").strip().lower() or "auto",
            model_name=os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip(),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
            anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip(),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip(),
            timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "4096")),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.2")),
            max_output_tokens=int(os.getenv("ANTHROPIC_MAX_OUTPUT_TOKENS", "4096")),
            max_runtime_seconds=float(os.getenv("EVAL_LOOP_MAX_RUNTIME_SECONDS", "300")),
            max_total_tokens=int(os.getenv("EVAL_LOOP_MAX_TOTAL_TOKENS", "12000")),
        )

    def normalized_backend(self) -> str:
        backend = self.backend.strip().lower()
        if backend not in {"auto", "ollama", "claude"}:
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
    if backend in {"auto", "ollama"}:
        client = OllamaClient(
            base_url=config.ollama_base_url,
            model_name=config.model_name,
            timeout_seconds=config.timeout_seconds,
            num_ctx=config.num_ctx,
            temperature=config.temperature,
        )
        if not client.is_available():
            raise ConnectionError(f"failed to reach Ollama at {config.ollama_base_url}")
        backend_label = f"ollama:{config.model_name}"
        runtime_model = config.model_name
    else:
        client = AnthropicClient(
            api_key=config.anthropic_api_key,
            model_name=config.anthropic_model,
            base_url=config.anthropic_base_url,
            timeout_seconds=config.timeout_seconds,
            temperature=config.temperature,
            max_output_tokens=config.max_output_tokens,
        )
        if not client.is_available():
            raise ConnectionError("missing ANTHROPIC_API_KEY for Claude backend")
        backend_label = f"claude:{config.anthropic_model}"
        runtime_model = config.anthropic_model
    logger.info("runtime backend selected: %s", backend_label)
    return RuntimeServices(
        generator=ReportGenerator(llm_client=client, model_name=runtime_model),
        evaluator=EvaluationAgent(llm_client=client, model_name=runtime_model),
        backend_label=backend_label,
    )
