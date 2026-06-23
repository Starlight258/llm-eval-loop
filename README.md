# LLM Report Evaluation Loop

LLM 제품을 만들면서 가장 어려웠던 점은 프롬프트를 수정하는 것이 아니라 **수정이 실제로 품질을 개선했는지 판단하는 일**이었다.

분석가의 피드백을 반영해 프롬프트를 계속 수정했지만, 한 부분을 고치면 다른 부분의 품질이 떨어지기도 했고, 이전 결과와 직접 비교하지 않으면 정말 좋아졌는지 확인하기 어려웠다.

이 프로젝트는 이런 과정을 사람이 반복하는 대신 **LLM-as-a-Judge**와 **Loop Engineering**을 적용해 자동화해 본 실험이다.

핵심은 리포트를 한 번 잘 생성하는 것이 아니라,

> **생성 → 평가 → 개선 → 재평가**

를 반복하는 **품질 개선 Loop**를 만드는 것이다.

---

# 프로젝트 목표

이 프로젝트에서는 다음 세 가지를 확인하는 데 집중했다.

- LLM이 리포트를 생성하고 평가하는 품질 개선 Loop를 만들 수 있는가
- Human Feedback을 구조화된 규칙으로 변환해 반복적으로 프롬프트를 개선할 수 있는가
- 반복 과정에서 품질과 실행 비용을 함께 제어할 수 있는가

실제 운영 데이터를 사용하지 않고도 품질 개선 과정을 검증할 수 있도록 Mock Data 기반으로 구현했다.

---

# 동작 흐름

```text
Mock Data
    │
    ▼
Report Generator
    │
    ▼
Evaluation Agent
(LLM-as-a-Judge)
    │
    ▼
Prompt Optimizer
    │
    ▼
SQLite Store
    │
    ▼
Loop Controller
```

1. Mock Data로 리포트를 생성한다.
2. Evaluation Agent가 Rubric 기준으로 평가한다.
3. Prompt Optimizer가 평가 결과와 Human Feedback을 다음 프롬프트 규칙으로 변환한다.
4. 모든 실행 결과를 SQLite에 저장한다.
5. Loop Controller가 종료 조건을 확인하고 반복 여부를 결정한다.

> Human Feedback을 Generator에 직접 전달하지 않는다. Optimizer가 먼저 해석한 뒤 구조화된 규칙으로 변환하고, 다음 프롬프트에만 반영한다.

---

# 아키텍처

<img width="3291" height="2346" alt="architecture" src="https://github.com/user-attachments/assets/3ba88f55-e172-42ef-8cb5-9485625f7ea9" />

## 구성 요소

| 컴포넌트 | 역할 |
|----------|------|
| Report Generator | Mock Data로 리포트 생성 |
| Evaluation Agent | Rubric 기준으로 평가하고 실패 원인 반환 |
| Prompt Optimizer | 평가 결과와 Human Feedback을 다음 프롬프트 규칙으로 변환 |
| SQLite Store | 실행 결과와 프롬프트 이력 저장 |
| Loop Controller | 반복과 종료 조건 제어 |
| Dashboard | Baseline / Latest / Best 비교 |

---

# 설계에서 고민한 점

## Maker-Checker Pattern

생성과 평가를 같은 모델이 수행하면 자기 결과를 후하게 평가할 가능성이 있다.

그래서 Generator는 리포트 생성만, Evaluation Agent는 Rubric 기반 평가만 수행하도록 역할을 분리했다.

---

## Termination Criteria

Loop는 오래 실행할수록 품질보다 실행 비용이 더 빠르게 증가할 수 있다.

그래서 다음 조건 중 하나를 만족하면 반복을 종료하도록 설계했다.

- 목표 점수를 만족한 경우
- 이전보다 점수가 낮아진 경우
- 최대 반복 횟수에 도달한 경우
- 최대 실행 시간을 초과한 경우
- 최대 토큰 사용량을 초과한 경우

추가로 반복해도 얻는 품질보다 실행 비용이 더 커지는 시점에 Loop를 멈추도록 했다.

---

## State Persistence

몇 번만 반복해도 어떤 프롬프트를 사용했고 어떤 피드백을 반영했는지 추적하기 어려워졌다.

그래서 모든 실행 결과를 SQLite에 저장하고 다음 세 가지 상태를 관리했다.

- **Baseline** : 최초 결과
- **Latest** : 현재 결과
- **Best** : 가장 높은 점수의 결과

덕분에 현재 결과뿐 아니라 중간에 더 좋은 결과가 있었는지도 함께 비교할 수 있었다.

---

## Human Feedback 처리

Human Feedback을 Generator에 직접 넣는 방법도 고려했다.

하지만 그렇게 하면 프롬프트 경계가 흐려지고, 어떤 수정이 실제 영향을 준 것인지 추적하기 어려웠다.

그래서 Feedback은 Optimizer가 먼저 읽고 구조화된 규칙으로 변환한 뒤 다음 프롬프트에만 반영하도록 설계했다.

---

## LangChain을 사용하지 않은 이유

이 프로젝트에서 중요한 것은 체인을 만드는 것이 아니라 **Loop를 어떻게 제어할 것인가**였다.

그래서 생성, 평가, 저장, 종료 조건을 코드에서 직접 드러내는 구조를 선택했다.

덕분에 반복 과정을 추적하기 쉽고, 각 컴포넌트를 독립적으로 테스트할 수 있었다.

---

# 평가 방식

Evaluation Agent는 다섯 개 항목을 각각 1~5점으로 평가한 뒤 가중 평균으로 최종 점수를 계산한다.

```text
overall =
(3 × appropriateness
+ 2 × groundedness
+ calibration
+ consistency
+ readability)
/ 8
```

가장 높은 가중치를 둔 것은 **Appropriateness**와 **Groundedness**였다.

운영 환경에서는 자연스러운 문장보다 **데이터에 근거한 해석과 과도한 일반화를 막는 것**이 더 중요하다고 판단했기 때문이다.

---

# 결과 해석

Dashboard에서는 다음 정보를 함께 확인할 수 있다.

- Baseline Score
- Latest Score
- Best Score
- Feedback Round
- 토큰 사용량
- 실행 시간

여기서 중요한 것은 **점수가 항상 올라가는 것이 아니라는 점**이다.

Latest와 Best를 함께 비교하면

- 실제로 개선됐는지
- 중간에 더 좋은 결과가 있었는지

를 구분할 수 있다.

좋은 피드백이 항상 높은 점수로 이어지는 것은 아니며, 점수 정체 역시 중요한 품질 신호가 될 수 있었다.

---

# 설계 Trade-off

## 피드백은 어디에 반영할 것인가

Feedback을 Generator에 직접 넣으면 프롬프트 경계가 흐려질 수 있었다.

그래서 Optimizer가 Feedback을 구조화된 규칙으로 변환하도록 설계했다.

---

## 왜 Baseline과 Latest를 분리했는가

프롬프트가 정말 개선됐는지 확인하려면 수정 전과 수정 후를 함께 비교할 수 있어야 했다.

또한 Best를 함께 저장하면 중간에 더 좋은 결과가 있었는지도 확인할 수 있다.

---

## 왜 Fallback을 제거했는가

초기에는 잘못된 숫자를 막기 위해 Fallback을 두기도 했다.

하지만 Fallback이 개입하면 LLM의 실제 출력과 프롬프트 효과를 정확하게 확인하기 어려웠다.

그래서 현재는 Judge와 Prompt 규칙만으로 품질을 개선하도록 변경했다.

---

## 왜 점수는 항상 오르지 않는가

처음에는 점수가 계속 오를수록 프롬프트도 좋아질 것이라고 생각했다.

하지만 실제로는 같은 점수라도 핵심 오류가 줄어든 경우가 있었고, 반대로 핵심 오류는 그대로인데 점수만 유지되는 경우도 있었다.

이 경험을 통해 점수는 최적화 목표가 아니라 **품질이 퇴보하지 않았는지 확인하는 가드레일**이라는 것을 알게 됐다.

---

# 실행 방법

## 환경 설정

`.env.example`을 복사해 `.env`를 생성한다.

### 주요 환경 변수

- `EVAL_LOOP_BACKEND`
- `OLLAMA_MODEL`
- `ANTHROPIC_API_KEY`
- `EVAL_DB_PATH`
- `EVAL_LOOP_MAX_RUNTIME_SECONDS`
- `EVAL_LOOP_MAX_TOTAL_TOKENS`

## 실행

### API

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Dashboard

```bash
uv run streamlit run dashboard/streamlit_app.py
```

### Docker

```bash
docker compose up --build
```

---

# 배운 점

이번 프로젝트를 통해 가장 크게 배운 것은 **좋은 프롬프트보다 좋은 품질 개선 Loop가 더 중요하다**는 점이었다.

Rubric으로 평가 기준을 정의하고, LLM-as-a-Judge로 품질을 평가하고, Human Feedback을 구조화하고, 반복을 언제 멈출지 설계하는 과정이 쌓이면서 프롬프트도 점점 안정적으로 개선됐다.

좋은 프롬프트는 한 번의 수정으로 만들어지는 것이 아니라, **좋은 평가 Loop 안에서 반복적으로 만들어진다.**
