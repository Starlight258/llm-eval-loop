from __future__ import annotations

from pathlib import Path

try:
    import streamlit as st
except ImportError:  # pragma: no cover - optional UI dependency
    st = None

from storage.db import EvaluationStore

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "storage" / "evaluation.sqlite"


def main() -> None:
    if st is None:
        print("streamlit is not installed")
        return
    st.title("LLM Report Evaluation Loop")
    store = EvaluationStore(DB_PATH)
    runs = store.list_runs()
    st.metric("Stored runs", len(runs))
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
    st.subheader("Prompt history")
    st.dataframe(store.list_prompt_versions())


if __name__ == "__main__":
    main()

