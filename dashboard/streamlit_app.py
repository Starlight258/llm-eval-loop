from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    import streamlit as st
except ImportError:  # pragma: no cover - optional UI dependency
    st = None

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from storage.db import EvaluationStore
from core.loop import run_evaluation_loop
from core.prompt_loader import load_prompt_document
from core.runtime import RuntimeConfig
from core.schemas import MockMetricData

DATA_DIR = BASE_DIR / "data"
PROMPT_DIR = Path(os.getenv("EVAL_PROMPT_DIR", str(BASE_DIR / ".local" / "prompts")))
DB_PATH = Path(os.getenv("EVAL_DB_PATH", str(BASE_DIR / "storage" / "evaluation.sqlite")))


def main() -> None:
    if st is None:
        print("streamlit is not installed")
        return
    st.title("LLM Report Evaluation Loop")
    st.caption("Run mock datasets through a report generator, rubric judge, and prompt optimizer.")
    backend = st.sidebar.selectbox("Backend", ["auto", "ollama", "heuristic"], index=0)
    model_name = st.sidebar.text_input("Model", value=os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    ollama_base_url = st.sidebar.text_input(
        "Ollama URL",
        value=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    )
    num_ctx = st.sidebar.number_input("Context", min_value=1024, max_value=131072, value=int(os.getenv("OLLAMA_NUM_CTX", "4096")), step=1024)
    temperature = st.sidebar.number_input("Temperature", min_value=0.0, max_value=1.0, value=float(os.getenv("OLLAMA_TEMPERATURE", "0.2")), step=0.05)
    runtime = RuntimeConfig(
        backend=backend,
        model_name=model_name,
        ollama_base_url=ollama_base_url,
        num_ctx=int(num_ctx),
        temperature=float(temperature),
    )
    dataset_id = st.selectbox("Dataset", sorted(path.stem for path in DATA_DIR.glob("*.json")))
    run_clicked = st.button("Run evaluation")
    store = EvaluationStore(DB_PATH)
    result = None
    if run_clicked:
        metric = MockMetricData(**json.loads((DATA_DIR / f"{dataset_id}.json").read_text()))
        prompt = load_prompt_document(PROMPT_DIR / "generator_v1.yaml")
        result = run_evaluation_loop(dataset_id, metric, prompt, store, runtime=runtime)
        latest_run = result.runs[-1]
        st.success(f"Completed {len(result.runs)} run(s) with backend {runtime.normalized_backend()}")
        st.metric("Latest score", f"{latest_run.overall_score:.3f}")
        st.metric("Best score", f"{result.best_run.overall_score:.3f}")
        st.write("### Runs")
        st.dataframe(
            [
                {
                    "prompt_version": run.prompt_version,
                    "overall_score": run.overall_score,
                    "groundedness": run.groundedness_score,
                    "appropriateness": run.appropriateness_score,
                    "calibration": run.calibration_score,
                    "consistency": run.consistency_score,
                    "readability": run.readability_score,
                }
                for run in result.runs
            ]
        )
        st.write("### Latest report")
        st.code(latest_run.report_text, language="markdown")
        st.write("### Best report")
        st.code(result.best_run.report_text, language="markdown")
        st.write("### Judge feedback")
        st.write(latest_run.judge_feedback)
        st.write("### Review notes")
        st.write(result.human_review_notes)

    runs = store.list_runs()
    st.metric("Stored runs", len(runs))
    st.write("### Stored history")
    st.dataframe(
        [
            {
                "run_id": run.run_id,
                "dataset_id": run.dataset_id,
                "prompt_version": run.prompt_version,
                "overall_score": run.overall_score,
                "created_at": run.created_at,
            }
            for run in runs
        ]
    )


if __name__ == "__main__":
    main()
