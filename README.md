# LLM Report Evaluation Loop

LLM이 생성한 수치 해석 리포트를 Rubric 기준으로 평가하고, 그 결과와 human feedback을 바탕으로 프롬프트를 반복 개선하는 실험용 프로젝트입니다.

이 저장소의 핵심은 "리포트를 한 번 잘 쓰는 것"이 아니라, `생성 -> 평가 -> 개선 -> 재평가` 루프를 끝까지 돌려보는 것입니다. mock data로 시작해서, LLM이 리포트를 만들고, judge가 채점하고, optimizer가 다음 prompt를 갱신합니다.

## 프로젝트 목적

이 프로젝트는 다음을 확인하는 데 초점을 둡니다.

1. mock data로 리포트를 생성할 수 있는가
2. rubric judge가 결과를 항목별로 평가할 수 있는가
3. baseline / latest / best를 분리해 개선 여부를 볼 수 있는가
4. human feedback를 raw text가 아니라 구조화된 prompt 규칙으로 반영할 수 있는가
5. runtime / token budget / 반복 횟수 같은 정지 조건으로 루프를 제어할 수 있는가

실제 운영 데이터를 직접 쓰지 않고도, 리포트 품질 개선 루프를 검증할 수 있게 만든 것이 목적입니다.

## 동작 흐름

현재 구현은 다음 순서로 동작합니다.

1. `data/mock_*.json`에서 mock metric을 읽는다
2. `core.generator.ReportGenerator`가 Markdown 리포트를 생성한다
3. `core.evaluation_agent.EvaluationAgent`가 rubric으로 평가한다
4. `core.prompt_optimizer.PromptOptimizer`가 다음 prompt를 만든다
5. `storage.EvaluationStore`가 run과 prompt history를 SQLite에 저장한다
6. acceptance criteria, runtime budget, token budget, score plateau를 기준으로 멈춘다

여기서 중요한 점은 human feedback이 generator에 직접 주입되지 않는다는 것입니다.  
raw feedback는 optimizer가 해석하고, 그 결과를 다음 prompt 규칙으로 반영합니다.

## 아키텍처

<img width="3291" height="2346" alt="image" src="https://github.com/user-attachments/assets/3ba88f55-e172-42ef-8cb5-9485625f7ea9" />

### 구성 요소

- `data/`: Marketplace, App Engagement, Signup Funnel용 mock 데이터
- `.local/prompts/`: generator / judge / optimizer용 YAML prompt
- `core/`: 생성, 평가, 최적화, prompt 로딩, loop orchestration
- `storage/`: SQLite persistence
- `app/`: FastAPI 진입점
- `dashboard/`: Streamlit 진입점
- `tests/`: 핵심 동작을 검증하는 단위 테스트

### 코드 경계

- `app/main.py`와 `dashboard/streamlit_app.py`는 서로를 호출하지 않고, 둘 다 `core.loop`를 직접 사용한다
- `Report Generator`
  - mock metric과 prompt를 받아 초안 리포트를 만든다
- `Evaluation Agent`
  - rubric 점수와 failed sentence를 반환한다
- `Prompt Optimizer`
  - evaluation result와 human feedback를 받아 다음 prompt를 만든다
- `Loop Controller`
  - baseline / feedback refinement / stop criteria를 관리한다
- `SQLite Store`
  - evaluation run과 prompt history를 저장한다
- `Dashboard`
  - baseline / latest / best를 비교해서 보여준다

## 왜 이런 구조로 했는가

### 명확한 정지 조건 (Termination Criteria)

LLM은 스스로 "이제 끝났다"를 판단하지 못하므로, 명시적인 정지 조건이 필요했습니다.  
이 프로젝트는 `overall score`, 필수 섹션 존재 여부, runtime budget, token budget, max feedback iterations를 같이 봅니다.  
점수가 합격선에 도달하면 멈추고, 예산을 넘기거나 더 나아지지 않으면 종료합니다.

### 역할 분리 (Maker-Checker)

생성기와 평가기를 분리했습니다.  
생성기는 리포트를 만들기만 하고, 평가기는 rubric 점수와 실패 문장만 반환합니다.  
이렇게 해야 실패 원인을 분리해서 볼 수 있고, 프롬프트 개선이 실제로 어디에 영향을 줬는지 추적할 수 있습니다.

### 상태 보존 (State Persistence)

baseline / latest / best, prompt history, evaluation runs를 SQLite에 저장합니다.  
대시보드는 저장된 run을 읽어서 현재 결과와 과거 결과를 비교합니다.  
또한 누적 token 수와 경과 시간도 같이 보여줍니다.

### 안전한 가드레일 (Safety Guardrails)

루프는 최대 3번의 feedback refinement만 허용합니다.  
`max_runtime_seconds`와 `max_total_tokens`를 두어 무한 반복과 비용 폭주를 막습니다.  
score가 더 이상 좋아지지 않으면 멈춥니다. tie 또는 decline도 정지 신호로 취급합니다.

### 선택적 Human Feedback

업무에서 들어오는 코멘트를 반영하려고 human feedback 입력을 넣었습니다.  
다만 raw 문장을 generator에 바로 넣지 않고, optimizer가 읽어서 다음 prompt 규칙으로 변환합니다.

### LangChain은 쓰지 않았다

이 프로젝트는 체인 조합보다 loop 제어와 상태 보존이 더 중요했습니다.  
생성, 평가, 최적화, 저장, 종료 조건을 직접 드러내는 편이 디버깅과 테스트에 유리했습니다.

## 실행 방법

### 환경 설정

루트의 `.env` 파일을 읽습니다. `.env.example`을 복사해서 시작하면 됩니다.

주요 환경 변수:

- `EVAL_LOOP_BACKEND`: `auto`, `ollama`, `claude`
- `OLLAMA_MODEL`: 기본 `qwen2.5:3b`
- `OLLAMA_BASE_URL`: 기본 `http://127.0.0.1:11434`
- `ANTHROPIC_API_KEY`: Claude를 쓸 때 필요
- `ANTHROPIC_BASE_URL`: 기본 `https://api.anthropic.com`
- `ANTHROPIC_MODEL`: 기본 `claude-sonnet-4-6`
- `EVAL_PROMPT_DIR`: prompt YAML 위치
- `EVAL_DB_PATH`: SQLite 저장 경로
- `EVAL_LOOP_MAX_RUNTIME_SECONDS`: 전체 runtime budget
- `EVAL_LOOP_MAX_TOTAL_TOKENS`: 전체 token budget

`EVAL_LOOP_BACKEND`를 비워 두면 `auto`로 처리되고, 현재는 Ollama를 우선 사용합니다.  
Claude를 쓰려면 `EVAL_LOOP_BACKEND=claude`와 `ANTHROPIC_API_KEY`를 설정합니다.

### 로컬 실행

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
uv run streamlit run dashboard/streamlit_app.py
```

### Docker 실행

```bash
docker compose up --build
```

Docker Compose는 API, Dashboard, Ollama를 함께 띄웁니다.  
처음 한 번은 Ollama 모델을 내려받아야 합니다.

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:3b
```

접속 주소:

- API: `http://localhost:8000`
- Dashboard: `http://localhost:8501`

## 결과 해석 기준

대시보드는 다음 값을 함께 보여줍니다.

- `Baseline score`
- `Latest score`
- `Best score`
- `Feedback rounds`
- `Tokens used`
- `Elapsed seconds`

여기서 중요한 것은 항상 점수가 올라가야 한다는 가정이 아니라,  
baseline 대비 latest가 어떻게 바뀌었는지, 그리고 best가 어디에서 나왔는지를 같이 보는 것입니다.  
피드백이 들어갔다고 해서 점수가 항상 오르지는 않으며, 오히려 특정 항목이 좋아지는 대신 다른 항목이 나빠질 수도 있습니다.

## 내가 고민한 점

### 1. 입력 피드백은 어디에 넣을 것인가

처음에는 human feedback를 generator에 직접 넣는 방식도 생각했지만, 그렇게 하면 프롬프트 경계가 흐려질 수 있었습니다.  
그래서 optimizer가 feedback를 읽고, 그 의미를 구조화된 규칙으로 바꿔 다음 prompt에 반영하도록 했습니다.

### 2. baseline과 latest를 왜 분리했는가

피드백 전과 후를 분리해야 개선 여부를 판단할 수 있기 때문입니다.  
이 구조가 있어야 "피드백이 실제로 도움이 됐는지", "중간 버전이 더 나았는지"를 구분할 수 있습니다.

### 3. 왜 canonical fallback을 제거했는가

초기에는 잘못된 숫자나 방향을 막기 위해 fallback을 두기도 했지만, 그 방식은 LLM 출력과 프롬프트 효과를 가릴 수 있었습니다.  
지금은 실제 LLM 출력이 더 직접적으로 드러나도록 두고, judge와 prompt 규칙으로 품질을 잡는 쪽을 택했습니다.

### 4. score가 항상 오르지 않는 이유

LLM 출력은 여러 평가 항목의 균형으로 결정되기 때문입니다.  
한 항목을 고치면 다른 항목이 미세하게 흔들릴 수 있고, 그래서 total score가 그대로이거나 오히려 떨어질 수 있습니다.  
이 프로젝트에서 확인한 중요한 사실은 "피드백이 반영됐다"와 "점수가 올랐다"는 같은 말이 아니라는 점입니다.

## 배운 점

- AI의 강점은 단발성 생성보다 반복 개선 루프에 있다
- raw feedback보다 구조화된 규칙이 안정적이다
- 숫자 표기, 단위, 해석 분리 같은 작은 규칙이 품질에 큰 영향을 준다
- 생성과 평가를 분리해야 문제의 위치가 보인다
- 점수가 오르지 않는 것도 중요한 학습 신호다

## 앞으로의 개선 방향

- feedback를 항목별 정책으로 더 세분화하기
- snapshot / interpretation / watchouts를 별도 규칙으로 더 강하게 분리하기
- judge의 failed sentence 유형별로 optimizer rule을 더 정밀하게 만들기
- latest / best 비교를 UI에서 더 직관적으로 보이게 하기
- 평가 루프를 실제 업무 피드백 흐름에 맞게 더 확장하기

## 레이아웃

- `core/` - 생성, 평가, 프롬프트 로딩, 최적화, 루프 제어
- `storage/` - SQLite 저장
- `app/` - FastAPI API
- `dashboard/` - Streamlit UI
- `data/` - mock 데이터
- `.local/prompts/` - YAML 프롬프트
- `tests/` - 단위 테스트
