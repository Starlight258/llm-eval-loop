from __future__ import annotations

from time import monotonic

from core.evaluation_agent import EvaluationAgent
from core.generator import ReportGenerator
from core.prompt_optimizer import PromptOptimizer
from core.runtime import RuntimeConfig, RuntimeServices, build_services
from core.schemas import EvaluationResult, EvaluationRunRecord, LoopResult, MockMetricData, PromptDocument, PromptVersionRecord
from storage.db import EvaluationStore

MAX_FEEDBACK_ITERATIONS = 3

ACCEPTANCE_SCORE_THRESHOLD = 4.5
REQUIRED_SECTIONS = ("## Snapshot", "## Interpretation", "## Breakdown", "## Watchouts")


def _has_required_sections(report_text: str) -> bool:
    return all(section in report_text for section in REQUIRED_SECTIONS)


def _evaluate_acceptance(report_text: str, evaluation) -> tuple[bool, list[str], list[str]]:
    checks = [
        f"overall_score >= {ACCEPTANCE_SCORE_THRESHOLD:.1f}",
        f"groundedness_score >= {ACCEPTANCE_SCORE_THRESHOLD:.1f}",
        f"appropriateness_score >= {ACCEPTANCE_SCORE_THRESHOLD:.1f}",
        f"calibration_score >= {ACCEPTANCE_SCORE_THRESHOLD:.1f}",
        f"consistency_score >= {ACCEPTANCE_SCORE_THRESHOLD:.1f}",
        f"readability_score >= {ACCEPTANCE_SCORE_THRESHOLD:.1f}",
        "report includes required sections",
        "judge found no failed sentences",
    ]
    failures: list[str] = []
    if evaluation.overall_score < ACCEPTANCE_SCORE_THRESHOLD:
        failures.append("overall score below threshold")
    if evaluation.scores.groundedness_score < ACCEPTANCE_SCORE_THRESHOLD:
        failures.append("groundedness below threshold")
    if evaluation.scores.appropriateness_score < ACCEPTANCE_SCORE_THRESHOLD:
        failures.append("appropriateness below threshold")
    if evaluation.scores.calibration_score < ACCEPTANCE_SCORE_THRESHOLD:
        failures.append("calibration below threshold")
    if evaluation.scores.consistency_score < ACCEPTANCE_SCORE_THRESHOLD:
        failures.append("consistency below threshold")
    if evaluation.scores.readability_score < ACCEPTANCE_SCORE_THRESHOLD:
        failures.append("readability below threshold")
    if not _has_required_sections(report_text):
        failures.append("required sections missing")
    if evaluation.failed_sentences:
        failures.append("judge reported failed sentences")
    return (not failures), checks, failures


def _record_usage(usage, *, total_prompt_tokens: int, total_completion_tokens: int) -> tuple[int, int]:
    if usage is None:
        return total_prompt_tokens, total_completion_tokens
    return (
        total_prompt_tokens + usage.prompt_tokens,
        total_completion_tokens + usage.completion_tokens,
    )


def run_evaluation_loop(
    dataset_id: str,
    metric: MockMetricData,
    initial_prompt: PromptDocument,
    store: EvaluationStore,
    *,
    runtime: RuntimeConfig | None = None,
    services: RuntimeServices | None = None,
    max_feedback_iterations: int = MAX_FEEDBACK_ITERATIONS,
    human_feedback: str = "",
) -> LoopResult:
    services = services or build_services(runtime or RuntimeConfig())
    generator = services.generator
    judge = services.evaluator
    optimizer = PromptOptimizer()
    current_prompt = initial_prompt
    prompt_history: list[PromptVersionRecord] = []
    runs: list[EvaluationRunRecord] = []
    feedback_runs: list[EvaluationRunRecord] = []
    best_run: EvaluationRunRecord | None = None
    stopped_reason = "max_feedback_iterations_reached"
    total_prompt_tokens = 0
    total_completion_tokens = 0
    started_at = monotonic()
    acceptance_passed = False
    acceptance_checks: list[str] = []
    acceptance_failures: list[str] = []

    def _run_single_pass(prompt: PromptDocument, *, loop_feedback: str) -> tuple[EvaluationRunRecord, EvaluationResult]:
        nonlocal total_prompt_tokens, total_completion_tokens
        prompt_history.append(
            PromptVersionRecord(
                prompt_version=prompt.prompt_version,
                label=prompt.label,
                prompt_text=prompt.raw_text,
                applied_rules=prompt.spec.instructions,
                good_example=prompt.spec.good_example,
                bad_example=prompt.spec.bad_example,
            )
        )
        store.save_prompt_version(
            prompt_version=prompt.prompt_version,
            label=prompt.label,
            prompt_text=prompt.raw_text,
            applied_rules=prompt.spec.instructions,
            good_example=prompt.spec.good_example,
            bad_example=prompt.spec.bad_example,
        )
        report_text = generator.generate(metric, prompt, human_feedback=loop_feedback)
        total_prompt_tokens, total_completion_tokens = _record_usage(
            getattr(generator, "last_usage", None),
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
        )
        evaluation = judge.evaluate(metric, report_text)
        total_prompt_tokens, total_completion_tokens = _record_usage(
            getattr(judge, "last_usage", None),
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
        )
        run = store.save_evaluation_run(
            dataset_id=dataset_id,
            prompt_version=prompt.prompt_version,
            report_text=report_text,
            evaluation=evaluation,
        )
        runs.append(run)
        return run, evaluation

    if runtime is not None and runtime.max_runtime_seconds > 0 and monotonic() - started_at >= runtime.max_runtime_seconds:
        stopped_reason = "runtime_budget_exceeded"
    else:
        baseline_run, baseline_evaluation = _run_single_pass(current_prompt, loop_feedback="")
        acceptance_passed, acceptance_checks, acceptance_failures = _evaluate_acceptance(
            baseline_run.report_text,
            baseline_evaluation,
        )
        best_run = baseline_run
        baseline_accepted = acceptance_passed
        if runtime is not None and runtime.max_total_tokens > 0:
            if total_prompt_tokens + total_completion_tokens >= runtime.max_total_tokens:
                stopped_reason = "token_budget_exceeded"
        if stopped_reason == "max_feedback_iterations_reached" and runtime is not None and runtime.max_runtime_seconds > 0:
            if monotonic() - started_at >= runtime.max_runtime_seconds:
                stopped_reason = "runtime_budget_exceeded"
        if not human_feedback.strip() and baseline_accepted:
            stopped_reason = "passed_acceptance_criteria"
        elif stopped_reason == "max_feedback_iterations_reached":
            current_evaluation = baseline_evaluation
            current_run = baseline_run
            loop_feedback = human_feedback.strip()
            for iteration in range(max_feedback_iterations):
                if runtime is not None and runtime.max_runtime_seconds > 0:
                    if monotonic() - started_at >= runtime.max_runtime_seconds:
                        stopped_reason = "runtime_budget_exceeded"
                        break
                if runtime is not None and runtime.max_total_tokens > 0:
                    if total_prompt_tokens + total_completion_tokens >= runtime.max_total_tokens:
                        stopped_reason = "token_budget_exceeded"
                        break
                next_prompt = optimizer.propose_next(
                    current_prompt,
                    current_evaluation,
                    iteration,
                    human_feedback=loop_feedback,
                )
                current_prompt = next_prompt
                next_run, next_evaluation = _run_single_pass(current_prompt, loop_feedback=loop_feedback)
                feedback_runs.append(next_run)
                if best_run is None or next_run.overall_score >= best_run.overall_score:
                    best_run = next_run
                acceptance_passed, acceptance_checks, acceptance_failures = _evaluate_acceptance(
                    next_run.report_text,
                    next_evaluation,
                )
                if next_run.overall_score < current_run.overall_score:
                    stopped_reason = "score_declined"
                    break
                current_run = next_run
                current_evaluation = next_evaluation
                if acceptance_passed:
                    stopped_reason = "passed_acceptance_criteria"
                    break

    if best_run is None:
        raise RuntimeError("evaluation loop did not produce any runs")
    if stopped_reason == "max_feedback_iterations_reached" and len(runs) >= 2 and runs[-1].overall_score < runs[-2].overall_score:
        stopped_reason = "score_declined"
    final_run = runs[-1]
    elapsed_seconds = monotonic() - started_at
    human_review_notes = (
        f"Review {len(runs)} stored runs for dataset {dataset_id} (baseline + feedback refinements). "
        f"Compare prompt versions {', '.join(record.prompt_version for record in prompt_history)}."
    )
    if human_feedback.strip():
        human_review_notes += " Human feedback was supplied after the baseline run and used in refinements."
    if baseline_accepted:
        human_review_notes += " Baseline run already met the acceptance checklist."
    if acceptance_passed:
        human_review_notes += " Acceptance checklist passed."
    if stopped_reason == "runtime_budget_exceeded":
        human_review_notes += " Stopped because the runtime budget was exceeded."
    if stopped_reason == "token_budget_exceeded":
        human_review_notes += " Stopped because the token budget was exceeded."
    return LoopResult(
        dataset_id=dataset_id,
        final_prompt_version=final_run.prompt_version,
        baseline_run=runs[0],
        final_run=final_run,
        best_run=best_run,
        runs=runs,
        feedback_runs=feedback_runs,
        prompt_history=prompt_history,
        acceptance_passed=acceptance_passed,
        acceptance_checks=acceptance_checks,
        acceptance_failures=acceptance_failures,
        elapsed_seconds=elapsed_seconds,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        stopped_reason=stopped_reason,
        human_review_notes=f"{human_review_notes} Backend: {services.backend_label}.",
    )
