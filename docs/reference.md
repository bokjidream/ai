# 레퍼런스: 디렉터리 구조 · 프롬프트 관리 · 환경 변수 · 협업 규칙

> [← 인덱스로 돌아가기](development_plan.md)

---

## 디렉터리 구조 (목표)

```
ai/
├── agents/
│   ├── __init__.py
│   ├── initial_interview.py  # 1단계 인터뷰: 최소 정보 수집
│   ├── rag_search.py         # RAG 1차 검색: 후보 서비스 목록
│   ├── service_select.py     # 서비스 선택 노드
│   ├── rag_detail.py         # RAG 2차 조회: 선택 서비스 상세 정보
│   ├── detail_interview.py   # 2단계 인터뷰: 서비스 특화 추가 정보
│   ├── document_guidance.py  # 서류 안내 에이전트 노드
│   ├── draft_writer.py       # 신청서 항목별 작성 가이드 에이전트 노드
│   └── report_writer.py      # 가이드를 사용자 친화적으로 재구성하는 보고서 에이전트 노드
├── graph/
│   ├── __init__.py
│   ├── state.py              # AgentState, UserProfile, WelfareCandidate
│   └── builder.py            # 그래프 빌더 및 조건부 엣지
├── tools/
│   ├── __init__.py
│   ├── llm.py                # LLM 팩토리 (현재: Gemini, 향후: Ollama)
│   ├── rag_client.py         # RAG 서비스 HTTP 클라이언트 (Phase 3)
│   └── prompt_loader.py      # prompts/ 디렉터리 파일 로딩 유틸리티
├── prompts/
│   ├── initial_interview.txt
│   ├── detail_interview.txt
│   ├── document_guidance.txt
│   ├── draft_writer.txt      # 신청서 항목별 작성 가이드 생성 프롬프트
│   └── report_writer.txt     # 가이드를 사용자 친화적으로 재구성하는 프롬프트
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # pytest fixtures (LLM 모킹, RAG 모킹)
│   ├── test_smoke.py             # 스모크 테스트 (기존)
│   ├── test_state.py
│   ├── test_rag_client_stub.py   # RAG 클라이언트 스텁 인터페이스 계약 검증
│   ├── test_prompts.py           # 프롬프트 파일 로딩 및 키워드 포함 여부 검증
│   ├── test_initial_interview.py
│   ├── test_rag_search.py
│   ├── test_service_select.py
│   ├── test_rag_detail.py
│   ├── test_detail_interview.py
│   ├── test_document_guidance.py
│   ├── test_draft_writer.py
│   ├── test_report_writer.py
│   ├── test_graph.py
│   ├── test_rag_integration.py
│   └── test_e2e.py
├── main.py                   # 진입점 (CLI 대화 루프)
├── server.py                 # FastAPI 서버 모드 (Phase 5 — Next.js 연동)
├── pyproject.toml
├── .env.example
└── docs/
    ├── development_plan.md   # 인덱스
    ├── overview.md           # 프로젝트 개요 + 아키텍처 + 데이터 모델
    ├── phase1.md             # Phase 1 개발 계획
    ├── phase2.md             # Phase 2 개발 계획
    ├── phase3.md             # Phase 3 개발 계획
    ├── phase4.md             # Phase 4 개발 계획
    ├── phase5.md             # Phase 5 개발 계획
    ├── agent_specs.md        # 에이전트 노드 상세 명세
    ├── testing.md            # 테스트 전략
    ├── reference.md          # 이 파일
    └── rag_api_contract.md   # RAG API 계약서 (Phase 2 시작 전 확정)
```

---

## 프롬프트 관리 전략

에이전트 노드의 시스템 프롬프트는 `prompts/` 디렉터리에 텍스트 파일로 분리하여 관리합니다.

### 로딩 방식

```python
# tools/prompt_loader.py
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def load_prompt(name: str) -> str:
    """prompts/{name}.txt 파일을 읽어 문자열로 반환합니다."""
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")
```

각 에이전트 노드에서:
```python
from tools.prompt_loader import load_prompt

SYSTEM_PROMPT = load_prompt("initial_interview")
```

### 파일 목록

| 파일 | 사용 노드 |
|------|----------|
| `prompts/initial_interview.txt` | `initial_interview_node` |
| `prompts/detail_interview.txt` | `detail_interview_node` |
| `prompts/document_guidance.txt` | `document_guidance_node` |
| `prompts/draft_writer.txt` | `draft_writer_node` |
| `prompts/report_writer.txt` | `report_writer_node` |

### 규칙

- 프롬프트 파일은 Git으로 버전 관리 (코드 변경 없이 프롬프트만 수정 가능)
- 프롬프트 내 변수 치환은 Python f-string 또는 `str.format()` 사용 (Jinja2 등 별도 템플릿 엔진 도입 금지 — 의존성 최소화)
- 테스트에서 프롬프트 파일을 직접 로딩하여 키워드 포함 여부 검증 (`test_prompts.py`)

---

## 환경 변수 관리

### 현재 필요한 변수 (`.env`)

```dotenv
# Google Gemini (Phase 1~3 사용)
GOOGLE_API_KEY=your_api_key_here
GOOGLE_MODEL=gemini-2.5-flash

# Checkpointer 선택 (memory | sqlite | postgres)
GRAPH_CHECKPOINTER=memory
SQLITE_DB_PATH=./checkpoints.db        # GRAPH_CHECKPOINTER=sqlite 시 사용
```

### Phase 3 추가 변수

```dotenv
# RAG 서비스 연동
RAG_SERVICE_URL=http://localhost:8000
RAG_SEARCH_TOP_K=5
RAG_TIMEOUT_SECONDS=10                 # HTTP 타임아웃 (초)
RAG_MAX_RETRIES=1                      # 네트워크 오류 재시도 횟수
```

### Phase 4 추가 변수 (Ollama 전환 시)

```dotenv
# Ollama (로컬 LLM)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

### Phase 5 추가 변수 (FastAPI 서버 모드)

```dotenv
# FastAPI 서버 (Next.js 연동)
SERVER_HOST=0.0.0.0
SERVER_PORT=8001
```

---

## 협업 규칙

### 브랜치 네이밍

```
feat/<기능명>      # 새 기능 (예: feat/agent-initial-interview)
fix/<버그명>       # 버그 수정 (예: fix/rag-search-timeout)
chore/<작업명>     # 설정, 의존성 등 (예: chore/add-rag-client)
refactor/<대상>    # 리팩터링
test/<대상>        # 테스트 추가/수정
```

### PR 체크리스트

- [ ] `uv run ruff check .` 통과
- [ ] `uv run ruff format --check .` 통과
- [ ] `uv run pytest tests/ -v` 통과
- [ ] 새 기능에 대한 테스트 파일 포함
- [ ] CLAUDE.md 또는 development_plan.md 업데이트 필요 여부 확인

### 커밋 메시지 컨벤션

```
<type>: <제목> (한국어 또는 영어)

예시:
feat: 1단계 인터뷰 에이전트 노드 구현
feat: RAG 후보 검색 노드 구현
fix: 서비스 선택 입력 파싱 오류 수정
chore: RAG HTTP 클라이언트 의존성 추가
test: 2단계 인터뷰 에이전트 단위 테스트 추가
```

### 코드 리뷰 기준

- 에이전트 노드는 반드시 `AgentState`를 입력/출력 타입으로 사용
- LLM 호출은 반드시 `get_llm()`을 통해 (직접 import 금지)
- RAG 호출은 반드시 `tools/rag_client.py`를 통해 (직접 HTTP 호출 금지)
- Pydantic 모델 변경 시 관련 테스트도 함께 업데이트
- `| None` 문법 사용 (`Optional` 사용 금지)
