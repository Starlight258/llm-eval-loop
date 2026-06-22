from __future__ import annotations

import json
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
except ImportError:  # pragma: no cover - fallback for minimal environments
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            self.routes = []

        def get(self, path: str):
            def decorator(func):
                self.routes.append(("GET", path, func))
                return func

            return decorator

        def post(self, path: str):
            def decorator(func):
                self.routes.append(("POST", path, func))
                return func

            return decorator


from core.loop import run_evaluation_loop
from core.prompt_loader import load_prompt_document
from core.schemas import MockMetricData
from storage.db import EvaluationStore

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
PROMPT_DIR = BASE_DIR / "prompts"
DB_PATH = BASE_DIR / "storage" / "evaluation.sqlite"

app = FastAPI(title="LLM Report Evaluation Loop")


def load_metric(dataset_id: str) -> MockMetricData:
    path = DATA_DIR / f"{dataset_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {dataset_id}")
    payload = json.loads(path.read_text())
    return MockMetricData(**payload)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/datasets")
def datasets() -> list[str]:
    return sorted(path.stem for path in DATA_DIR.glob("*.json"))


@app.post("/run/{dataset_id}")
def run_dataset(dataset_id: str) -> dict[str, object]:
    metric = load_metric(dataset_id)
    prompt = load_prompt_document(PROMPT_DIR / "generator_v1.yaml")
    store = EvaluationStore(DB_PATH)
    result = run_evaluation_loop(dataset_id, metric, prompt, store)
    return {
        "dataset_id": result.dataset_id,
        "stopped_reason": result.stopped_reason,
        "final_prompt_version": result.final_prompt_version,
        "best_score": result.best_run.overall_score,
        "runs": [run.__dict__ for run in result.runs],
    }

