from __future__ import annotations

import json
import logging
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
    logging.basicConfig(level=logging.INFO)
    base_runtime = RuntimeConfig.from_env()
    st.title("LLM Report Evaluation Loop")
    st.caption("Run mock datasets through a report generator, rubric judge, and prompt optimizer.")
    backend_options = ["auto", "ollama", "claude"]
    backend_index = backend_options.index(base_runtime.backend) if base_runtime.backend in backend_options else 0
    backend = st.sidebar.selectbox("Backend", backend_options, index=backend_index)
    model_name = st.sidebar.text_input("Model", value=base_runtime.model_name)
    ollama_base_url = st.sidebar.text_input(
        "Ollama URL",
        value=base_runtime.ollama_base_url,
    )
    anthropic_api_key = st.sidebar.text_input(
        "Anthropic API Key",
        value=base_runtime.anthropic_api_key,
        type="password",
    )
    anthropic_base_url = st.sidebar.text_input(
        "Anthropic URL",
        value=base_runtime.anthropic_base_url,
    )
    anthropic_model = st.sidebar.text_input(
        "Claude Model",
        value=base_runtime.anthropic_model,
    )
    num_ctx = st.sidebar.number_input("Context", min_value=1024, max_value=131072, value=base_runtime.num_ctx, step=1024)
    temperature = st.sidebar.number_input("Temperature", min_value=0.0, max_value=1.0, value=base_runtime.temperature, step=0.05)
    max_output_tokens = st.sidebar.number_input(
        "Max output tokens",
        min_value=256,
        max_value=32768,
        value=base_runtime.max_output_tokens,
        step=256,
    )
    max_runtime_seconds = st.sidebar.number_input(
        "Max runtime (s)",
        min_value=30.0,
        max_value=7200.0,
        value=base_runtime.max_runtime_seconds,
        step=30.0,
    )
    max_total_tokens = st.sidebar.number_input(
        "Max tokens",
        min_value=1000,
        max_value=1000000,
        value=base_runtime.max_total_tokens,
        step=1000,
    )
    human_feedback = st.text_area(
        "Human feedback (optional)",
        value="",
        placeholder="예: 숫자 표기는 더 명확하게, 톤은 조금 더 신중하게",
        height=120,
    )
    runtime = RuntimeConfig(
        backend=backend,
        model_name=model_name,
        ollama_base_url=ollama_base_url,
        anthropic_api_key=anthropic_api_key,
        anthropic_base_url=anthropic_base_url,
        anthropic_model=anthropic_model,
        num_ctx=int(num_ctx),
        temperature=float(temperature),
        max_output_tokens=int(max_output_tokens),
        max_runtime_seconds=float(max_runtime_seconds),
        max_total_tokens=int(max_total_tokens),
    )
    dataset_id = st.selectbox("Dataset", sorted(path.stem for path in DATA_DIR.glob("*.json")))
    run_clicked = st.button("Run evaluation")
    store = EvaluationStore(DB_PATH)
    result = None
    if run_clicked:
        try:
            metric = MockMetricData(**json.loads((DATA_DIR / f"{dataset_id}.json").read_text()))
            prompt = load_prompt_document(PROMPT_DIR / "generator_v1.yaml")
            result = run_evaluation_loop(
                dataset_id,
                metric,
                prompt,
                store,
                runtime=runtime,
                human_feedback=human_feedback,
            )
        except ConnectionError as exc:
            st.error(str(exc))
        else:
            latest_run = result.runs[-1]
            st.success(f"Completed {len(result.runs)} run(s) with backend {runtime.normalized_backend()}")
            st.metric("Baseline score", f"{result.baseline_run.overall_score:.3f}")
            st.metric("Latest score", f"{latest_run.overall_score:.3f}")
            st.metric("Best score", f"{result.best_run.overall_score:.3f}")
            st.metric("Feedback rounds", len(result.feedback_runs))
            st.metric("Tokens used", f"{result.total_prompt_tokens + result.total_completion_tokens}")
            st.metric("Elapsed seconds", f"{result.elapsed_seconds:.1f}")
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
            st.write("### Acceptance checklist")
            st.write(result.acceptance_checks)
            if result.acceptance_failures:
                st.write("### Acceptance failures")
                st.write(result.acceptance_failures)
            st.write("### Latest report")
            st.code(latest_run.report_text, language="markdown")
            st.write("### Baseline report")
            st.code(result.baseline_run.report_text, language="markdown")
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
    st.write("### Prompt history")
    st.dataframe(store.list_prompt_versions())


if __name__ == "__main__":
    main()
