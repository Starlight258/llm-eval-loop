# LLM Report Evaluation Loop

Mock metric data is turned into Markdown reports, scored against a rubric, stored in SQLite, and iteratively improved through prompt optimization.

This repository keeps the implementation self-contained so it can run without external API keys. The default local backend is heuristic, and the app can switch to Ollama when `qwen3.6` is available.

## Layout

- `core/` - generation, evaluation, prompt loading, optimization, and loop orchestration
- `storage/` - SQLite persistence
- `app/` - FastAPI entrypoint
- `dashboard/` - Streamlit dashboard
- `data/` - mock datasets
- `prompts/` - baseline prompt specs
- `tests/` - unit tests

## Local run

- API: `uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Dashboard: `streamlit run dashboard/streamlit_app.py`

## Docker

1. Start the stack: `docker compose up --build`
2. Pull the local model into Ollama: `docker compose exec ollama ollama pull qwen3.6`
3. Open the API at `http://localhost:8000`
4. Open the dashboard at `http://localhost:8501`

The dashboard lets you choose `auto`, `ollama`, or `heuristic` and run a dataset through the evaluation loop.
