# LLM Report Evaluation Loop 설계

## 1. 프로젝트 목적

LLM이 생성한 수치 해석 리포트를 Rubric 기준으로 평가하고, 평가 결과를 바탕으로 프롬프트와 예시를 반복 개선하는 시스템을 만든다.

인턴 프로젝트 코드는 없기 때문에 실제 운영 데이터는 사용하지 않는다. 대신 Mock 지표 데이터를 만들고, 이를 기반으로 리포트 생성과 평가 루프를 재현한다.

목표는 리포트 생성 자체보다 LLM 출력 품질을 평가하고 개선하는 구조를 설계하는 것이다.

## 2. 핵심 아이디어

기존 방식은 실패 사례가 생기면 바로 프롬프트를 수정하는 방식이었다.

이 프로젝트에서는 다음 구조를 만든다.

```
Mock Data
→ Report Generator
→ Evaluation Agent
→ Evaluation Store
→ Prompt Optimizer
→ 재평가
```

핵심은 Generator와 Evaluator를 분리하는 것이다.

생성하는 LLM과 평가하는 LLM의 역할을 나누어, 생성 결과를 Rubric 기준으로 평가한다.

## 3. Rubric

평가는 아래 다섯 가지 기준으로 한다.

| 평가 항목 | 확인한 내용 |
|---|---|
| 근거성 | 입력 데이터에 근거한 해석인가 |
| 해석 적정성 | 데이터 범위를 넘어 과도하게 일반화하지 않았는가 |
| 불확실성 표현 | 사실과 추측을 구분했는가 |
| 표현 일관성 | 비슷한 상황에서 같은 기준으로 표현했는가 |
| 가독성 | 핵심 내용을 빠르게 이해할 수 있는가 |

각 항목은 1~5점으로 평가한다.

| 점수 | 의미 |
|---|---|
| 5 | 문제 없음 |
| 4 | 경미한 개선 필요 |
| 3 | 일부 문제 있음 |
| 2 | 명확한 문제 있음 |
| 1 | 심각한 문제 있음 |

## 4. 시스템 구성

### 4.1 Mock Data Generator

실제 회사 데이터를 사용하지 않고, 가상의 서비스 지표 데이터를 생성한다.

도메인: Marketplace / App Engagement / Signup Funnel

공통 필드:

```json
{
  "metric_name": "listing_count",
  "current": 572000,
  "previous": 584000,
  "dod": -2.0,
  "wow": -5.2,
  "avg_4w": 618000,
  "trend_7d": [-0.4, -0.8, -1.2, -1.7, -2.0],
  "breakdowns": {
    "platform": {
      "android": -2.5,
      "ios": -0.8
    }
  }
}
```

### 4.2 Report Generator

Mock Data를 입력받아 Markdown 리포트를 생성한다. 입력: Mock Metric Data, Generator Prompt Version. 출력: Markdown Report.

### 4.3 Evaluation Agent

생성된 리포트를 Rubric 기준으로 평가한다. **리포트를 다시 작성하지 않는다. 오직 평가만 한다.**

입력: 원본 Mock Data, 생성된 Report, Rubric, Judge Prompt
출력: 항목별 점수, 실패 문장, 실패 이유, 개선 제안

**채점 방식(결정):** MVP에서는 동일 리포트에 대해 Judge를 1회만 호출한다. Self-consistency(다회 호출/다수결)는 도입하지 않는다. 점수 변동성은 알려진 한계로 명시하고, 필요해지면 이후 버전에서 검토한다.

**LLM 호출 방식(결정):** Judge 호출은 free-text JSON 파싱을 사용하지 않는다. Anthropic SDK의 `tool_use` + `tool_choice={"type": "tool", "name": "output"}`로 강제하고, 결과는 `response.content[0].input`에서 받는다. `max_tokens >= 4096`. (전역 규칙 `python-fastapi.md` 준수)

### 4.4 Evaluation Store

평가 결과를 저장한다. 저장 목적은 Prompt Version별 성능 비교다.

| 필드 | 설명 |
|---|---|
| run_id | 실행 ID |
| dataset_id | Mock Data ID |
| prompt_version | Generator Prompt 버전 (아래 버저닝 정책 참조) |
| report_text | 생성된 리포트 |
| groundedness_score | 근거성 점수 |
| appropriateness_score | 해석 적정성 점수 |
| calibration_score | 불확실성 표현 점수 |
| consistency_score | 표현 일관성 점수 |
| readability_score | 가독성 점수 |
| overall_score | 가중 평균 점수 (가중치 정책 아래 참조) |
| failed_sentences | 실패 문장 |
| judge_feedback | Judge 피드백 |
| created_at | 생성 시각 |

DB는 처음에는 SQLite로 충분하다.

**가중치 정책(결정):** 5개 항목을 동일하게 취급하지 않는다. 해석 적정성(appropriateness)이 가장 중요하고, 근거성(groundedness)이 그 다음이며, 나머지(불확실성 표현/표현 일관성/가독성)는 동일한 가중치를 적용한다.

| 항목 | 가중치 |
|---|---|
| appropriateness_score | 3 |
| groundedness_score | 2 |
| calibration_score | 1 |
| consistency_score | 1 |
| readability_score | 1 |

```
overall_score = (3*appropriateness + 2*groundedness + 1*calibration + 1*consistency + 1*readability) / 8
```

**프롬프트 버저닝 정책(결정):** `prompts/*.yaml` 파일은 사람이 읽는 라벨(`generator_v2` 등)을 위한 것이고, 실제로 DB에 저장되는 `prompt_version` 값은 런타임에 해당 YAML 파일 내용을 해시한 값을 라벨에 덧붙인 형태로 만든다.

```
prompt_version = f"{label}@{sha256(file_bytes)[:8]}"
# 예: "generator_v2@a3f9c1de"
```

이렇게 하면 이후 누군가 `generator_v2.yaml` 내용을 수정해도, 과거 run에 저장된 `prompt_version`은 그 시점의 실제 파일 내용을 가리키므로 재현성이 깨지지 않는다. 파일을 로드하는 공통 유틸(`core/prompt_loader.py` 등)에서 라벨+해시 조합을 계산해 반환하도록 구현한다.

### 4.5 Prompt Optimizer

평가 결과를 바탕으로 프롬프트 개선안을 제안한다.

**자동 루프 정책(결정):** MVP에서는 Optimizer의 제안을 매 회 사람이 먼저 승인하는 방식(사전 승인) 대신, **최대 3회까지 자동으로 루프를 돈다.**

- 1바퀴 = Generator → Evaluation Agent → Evaluation Store → Optimizer → 새 Prompt Version 생성 → 다음 바퀴 Generator에 사용
- 최대 반복 횟수: **3회** (`MAX_LOOP_ITERATIONS = 3`)
- **자동 정지 조건:** 직전 바퀴보다 `overall_score`가 하락하면 즉시 루프를 멈추고, 마지막으로 성공한(점수가 오르거나 유지된) 버전을 최종본으로 표시한다.
- 사람의 역할은 **사전 승인 → 사후 감사**로 바뀐다. 루프가 끝난 뒤(3회 완료 또는 점수 하락으로 조기 종료) 전체 버전별 점수 변화와 적용된 규칙/예시 이력을 사람이 검토한다.
- 모든 중간 버전(`prompt_version`, 적용된 규칙, good/bad example)은 Evaluation Store에 남아 사후 추적이 가능해야 한다.

> 참고: Optimizer가 만드는 `good_example`은 실질적으로 "고쳐 쓴 문장"이라, Evaluation Agent의 "재작성 금지" 원칙과 형태상 완전히 분리되지는 않는다. 현재는 의도된 trade-off로 두고 그대로 진행한다.

## 5. 전체 평가 루프

한 바퀴(iteration)는 Generator부터 Optimizer까지 전부 거친다. 즉 **Evaluation Agent는 매 바퀴마다 실행된다** (그래야 바퀴별 점수를 비교해 정지 여부를 판단할 수 있다).

```
[1바퀴] Mock Data → Generator(prompt v1) → Report → Evaluation Agent → Store → Optimizer → Prompt v2 생성
[2바퀴] Mock Data → Generator(prompt v2) → Report → Evaluation Agent → Store → Optimizer → Prompt v3 생성
[3바퀴] Mock Data → Generator(prompt v3) → Report → Evaluation Agent → Store → Optimizer → Prompt v4 생성
        (최대 3바퀴, 직전 바퀴보다 overall_score 하락 시 그 자리에서 즉시 정지)

루프 종료 후 → Human Review (사후 감사: 바퀴별 점수 변화 + 적용된 규칙/예시 이력 검토)
```

## 6. 기술 스택

| 영역 | 기술 |
|---|---|
| Language | Python |
| API Server | FastAPI |
| LLM Client | OpenAI API 또는 Claude API |
| Schema Validation | Pydantic |
| Database | SQLite |
| Dashboard | Streamlit |
| Prompt 관리 | YAML |
| Test | pytest |
| 배포 | Docker |

처음에는 LangChain 없이 직접 구현한다. 추후 여러 Agent를 연결하거나 상태 기반 워크플로우가 복잡해지면 LangGraph 도입을 고려한다.

## 7. 디렉토리 구조

```
report-eval-loop/
  app/
    main.py
  core/
    generator.py
    evaluation_agent.py
    prompt_optimizer.py
    prompt_loader.py
    schemas.py
  data/
    mock_marketplace.json
    mock_engagement.json
    mock_signup_funnel.json
  prompts/
    generator_v1.yaml
    generator_v2.yaml
    judge.yaml
    optimizer.yaml
  storage/
    db.py
    models.py
  dashboard/
    streamlit_app.py
  tests/
    test_generator.py
    test_evaluation_agent.py
    test_prompt_optimizer.py
  README.md
```

## 8. MVP 구현 순서

1. Mock Data 작성 (Marketplace / App Engagement / Signup Funnel)
2. Report Generator 구현
3. Evaluation Agent 구현 (`tool_use` 강제, JSON 응답)
4. Evaluation Store 구현 (SQLite, 버저닝 정책 적용)
5. Dashboard 구현 (Streamlit)
6. Prompt Optimizer 구현 (최대 3회 자동 루프, 점수 하락 시 자동 정지, 종료 후 Human 사후 검토)

## 9. 성공 기준

| 목표 | 기준 |
|---|---|
| 리포트 생성 | Mock Data 기반 Markdown Report 생성 |
| 평가 자동화 | Rubric 5개 항목에 대해 JSON 평가 생성 |
| 실패 추적 | 실패 문장과 이유 저장 |
| 개선 비교 | Prompt v1, v2 점수 비교 가능 |
| 대시보드 | 평가 결과와 개선 전후 비교 가능 |

## 10. 포트폴리오에서 강조할 점

- Generator와 Evaluation Agent 역할 분리
- Rubric 기반 LLM-as-a-Judge 설계
- Prompt Version별 품질 비교 (해시 기반 재현성 보장)
- 실패 문장과 개선 이유 저장
- Human-in-the-loop 기반 Prompt 개선
- 실제 운영 데이터 없이 Mock Data로 안전하게 재현

## 11. 알려진 한계 (Known Limitations)

- Judge는 1회 호출 기준이므로 동일 리포트에 대해 점수가 약간 흔들릴 수 있다 (self-consistency 미도입).
- Mock Data 필드가 단순해, Judge가 "데이터에 없는 일반적 해석"까지 과도하게 감점할 수 있는 경계가 불명확하다 — 별도 결정 없이 진행, 실제 평가 결과를 보고 Judge Prompt에서 조정.
- `overall_score`는 가중 평균(적정성 3, 근거성 2, 나머지 1)이며, 이 가중치 자체가 임의의 정성적 판단이라 실제 평가 결과를 보고 재조정될 수 있다.
- 자동 루프(최대 3회)는 사람의 사전 승인 없이 진행되므로, Optimizer가 만든 규칙/예시가 다소 부정확해도 점수가 떨어지지 않는 한 다음 바퀴까지 그대로 적용될 수 있다. 이는 의도된 trade-off이며, 루프 종료 후 사람이 사후 검토로 보완한다.

## 12. README 한 줄 요약

LLM이 생성한 수치 해석 리포트를 Rubric 기반으로 평가하고, 평가 결과를 바탕으로 프롬프트를 반복 개선하는 LLM Evaluation Loop 프로젝트입니다.
