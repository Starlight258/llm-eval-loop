# LLM Report Evaluation Loop

Mock metric data is turned into Markdown reports, scored against a rubric, stored in SQLite, and iteratively improved through prompt optimization.

This repository keeps the implementation self-contained so it can run without external API keys. FastAPI, Streamlit, and Anthropic/OpenAI clients are wired as optional integration points.

## Layout

- `core/` - generation, evaluation, prompt loading, optimization, and loop orchestration
- `storage/` - SQLite persistence
- `app/` - FastAPI entrypoint
- `dashboard/` - Streamlit dashboard
- `data/` - mock datasets
- `prompts/` - baseline prompt specs
- `tests/` - unit tests

