from __future__ import annotations

from core.evaluation_agent import EvaluationAgent
from core.generator import ReportGenerator
from core.prompt_optimizer import PromptOptimizer
from core.runtime import RuntimeConfig, build_services
from core.schemas import EvaluationRunRecord, LoopResult, MockMetricData, PromptDocument, PromptVersionRecord
from storage.db import EvaluationStore

MAX_LOOP_ITERATIONS = 3


def run_evaluation_loop(
    dataset_id: str,
    metric: MockMetricData,
    initial_prompt: PromptDocument,
    store: EvaluationStore,
    *,
    runtime: RuntimeConfig | None = None,
    max_iterations: int = MAX_LOOP_ITERATIONS,
) -> LoopResult:
    services = build_services(runtime or RuntimeConfig(backend="heuristic"))
    generator = services.generator
    judge = services.evaluator
    optimizer = PromptOptimizer()
    current_prompt = initial_prompt
    prompt_history: list[PromptVersionRecord] = []
    runs: list[EvaluationRunRecord] = []
    best_run: EvaluationRunRecord | None = None
    stopped_reason = "max_iterations_reached"

    for iteration in range(max_iterations):
        prompt_history.append(
            PromptVersionRecord(
                prompt_version=current_prompt.prompt_version,
                label=current_prompt.label,
                prompt_text=current_prompt.raw_text,
                applied_rules=current_prompt.spec.instructions,
                good_example=current_prompt.spec.good_example,
                bad_example=current_prompt.spec.bad_example,
            )
        )
        report_text = generator.generate(metric, current_prompt)
        evaluation = judge.evaluate(metric, report_text)
        run = store.save_evaluation_run(
            dataset_id=dataset_id,
            prompt_version=current_prompt.prompt_version,
            report_text=report_text,
            evaluation=evaluation,
        )
        runs.append(run)
        if best_run is None or run.overall_score >= best_run.overall_score:
            best_run = run

        if iteration == max_iterations - 1:
            break

        next_prompt = optimizer.propose_next(current_prompt, evaluation, iteration)
        if len(runs) > 0 and iteration >= 0 and len(runs) >= 2:
            if run.overall_score < runs[-2].overall_score:
                stopped_reason = "score_declined"
                break
        current_prompt = next_prompt

    if best_run is None:
        raise RuntimeError("evaluation loop did not produce any runs")
    if len(runs) >= 2 and runs[-1].overall_score < runs[-2].overall_score:
        stopped_reason = "score_declined"
    final_run = runs[-1]
    human_review_notes = (
        f"Review {len(runs)} stored runs for dataset {dataset_id}. "
        f"Compare prompt versions {', '.join(record.prompt_version for record in prompt_history)}."
    )
    return LoopResult(
        dataset_id=dataset_id,
        final_prompt_version=final_run.prompt_version,
        final_run=final_run,
        best_run=best_run,
        runs=runs,
        prompt_history=prompt_history,
        stopped_reason=stopped_reason,
        human_review_notes=f"{human_review_notes} Backend: {services.backend_label}.",
    )
