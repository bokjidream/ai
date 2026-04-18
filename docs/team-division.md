# ai/ 팀 업무 분장

> 작성일: 2026-04-17
> 개발 인원: 2명 (A, B)
> 기준 문서: `docs/development_plan.md`

---

## 분장 원칙

- **Phase 1은 공동 작업** — `graph/builder.py`와 checkpointer·interrupt 패턴은 LangGraph에서 가장 어려운 부분이므로 둘이 함께 구현하며 학습
- **A** — 인터뷰 계열 에이전트 + 도구 인프라 + 출력 노드
- **B** — RAG 연동 계열 에이전트 + HitL 선택 노드 + 서버
- RAG API 계약(`docs/rag_api_contract.md`)은 **Phase 2 시작 전 확정**

---

## Phase 1 — 공동 작업 (LangGraph 기반 구축)

| 파일 | 작업 내용 |
|------|-----------|
| `graph/state.py` | `UserProfile`, `WelfareCandidate`, `AgentState` Pydantic 모델 |
| `graph/builder.py` | StateGraph 노드 등록·엣지 연결·조건부 엣지·Checkpointer 설정·interrupt() 패턴 확인 |
| `tests/test_state.py` | Pydantic 모델 단위 테스트 |
| `tests/test_graph.py` | 그래프 컴파일 및 노드 연결 통합 테스트 |

**완료 기준:** 그래프가 START → END까지 컴파일되고, checkpointer를 붙인 상태에서 interrupt() → resume 흐름 확인

---

## A 담당

### 역할 요약
LLM 대화 패턴(인터뷰) 중심 노드 + 공통 도구 인프라

### Phase 2 — 도구 인프라

| 파일 | 작업 내용 |
|------|-----------|
| `tools/llm.py` | `get_llm()` 팩토리 (Gemini 현재, Ollama 전환점 유지) |
| `tools/prompt_loader.py` | `load_prompt()` 유틸리티 |
| `tests/conftest.py` | `mock_llm` 픽스처 작성 (`mock_rag_client`는 B와 합의 후 추가) |

### Phase 2 — 인터뷰 계열 에이전트

> 두 노드 모두 "LLM에 묻기 → structured output 파싱 → 누락 필드 감지 → 재진입 루프" 패턴

| 파일 | 작업 내용 |
|------|-----------|
| `agents/initial_interview.py` | 1단계 인터뷰 노드 (5개 최소 필드 수집, structured output, 재진입 루프) |
| `prompts/initial_interview.txt` | 1단계 인터뷰 시스템 프롬프트 |
| `tests/test_initial_interview.py` | 1단계 인터뷰 단위 테스트 |
| `agents/detail_interview.py` | 2단계 인터뷰 노드 (`extra:` 접두사 처리, pass-through 처리, 재진입 루프) |
| `prompts/detail_interview.txt` | 2단계 인터뷰 시스템 프롬프트 |
| `tests/test_detail_interview.py` | 2단계 인터뷰 단위 테스트 |

### Phase 2 — 출력 에이전트

| 파일 | 작업 내용 |
|------|-----------|
| `agents/document_guidance.py` | 서류 안내 노드 (사용자 상황 기반 서류 필터링) |
| `prompts/document_guidance.txt` | 서류 안내 시스템 프롬프트 |
| `tests/test_document_guidance.py` | 서류 안내 노드 단위 테스트 |
| `agents/report_writer.py` | 보고서 에이전트 노드 (Markdown 재구성, 정보 추가 금지) |
| `prompts/report_writer.txt` | 보고서 시스템 프롬프트 |
| `tests/test_report_writer.py` | 보고서 노드 단위 테스트 |

### Phase 4 — Ollama 전환

| 파일 | 작업 내용 |
|------|-----------|
| `tools/llm.py` | Ollama 코드 활성화, Gemini 코드 제거 |
| `.env.example` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` 추가 |
| `tests/conftest.py` | CI 환경 LLM 모킹 구성 확인 |

### Phase 5 — CLI 완성

| 파일 | 작업 내용 |
|------|-----------|
| `main.py` | 대화형 루프, `interrupt()` 재개 패턴, 서비스 선택 UX |

---

## B 담당

### 역할 요약
RAG HTTP 연동 패턴 중심 노드 + HitL 선택 노드 + 서버

### Phase 2 — RAG 클라이언트 스텁

| 파일 | 작업 내용 |
|------|-----------|
| `tools/rag_client.py` | `search()` / `get_detail()` 인터페이스 정의 + 더미 스텁 구현 (Phase 3에서 교체) |
| `tests/test_rag_client_stub.py` | 인터페이스 계약 검증 테스트 |
| `tests/conftest.py` | `mock_rag_client` 픽스처 추가 (A와 합의 후) |

### Phase 2 — RAG 계열 에이전트

> 세 노드 모두 "rag_client 호출 → 응답 파싱 → 상태 업데이트" 패턴이 동일

| 파일 | 작업 내용 |
|------|-----------|
| `agents/rag_search.py` | RAG 후보 검색 노드 (JSON 직렬화, priority 계산, 결과 없음 처리) |
| `tests/test_rag_search.py` | RAG 검색 노드 테스트 (HTTP 오류 시나리오 포함) |
| `agents/rag_detail.py` | RAG 상세 조회 노드 (상세 필드 채우기, LLM으로 `detail_missing_fields` 추론) |
| `tests/test_rag_detail.py` | RAG 상세 조회 노드 테스트 (HTTP 오류 시나리오 포함) |

### Phase 2 — HitL 선택 노드 + 작성 에이전트

| 파일 | 작업 내용 |
|------|-----------|
| `agents/service_select.py` | 서비스 선택 노드 (HitL `interrupt()`, 잘못된 입력 재`interrupt`) |
| `tests/test_service_select.py` | interrupt → resume 흐름, 잘못된 입력 흐름 테스트 |
| `agents/draft_writer.py` | 신청서 작성 가이드 노드 (항목별 가이드, `[직접 확인 필요]` 처리) |
| `prompts/draft_writer.txt` | 신청서 작성 가이드 시스템 프롬프트 |
| `tests/test_draft_writer.py` | 신청서 작성 가이드 단위 테스트 |

### Phase 3 — RAG 실제 연동

| 파일 | 작업 내용 |
|------|-----------|
| `tools/rag_client.py` | 스텁 → 실제 `httpx.AsyncClient` HTTP 구현으로 교체 |
| `.env.example` | `RAG_SERVICE_URL`, `RAG_SEARCH_TOP_K` 등 추가 |
| `tests/test_rag_integration.py` | 실제 RAG 서비스 연동 통합 테스트 |

### Phase 5 — FastAPI 서버 모드

| 파일 | 작업 내용 |
|------|-----------|
| `server.py` | `POST /chat`, `POST /resume` 엔드포인트, `thread_id` 세션 관리 |

---

## 공동 작업

| 시점 | 작업 |
|------|------|
| Phase 1 전체 | `graph/state.py`, `graph/builder.py` 구현 및 LangGraph 학습 |
| Phase 2 시작 전 | `docs/rag_api_contract.md` 작성 및 `rag/` 파트와 JSON 스키마 확정 |
| Phase 2 전반 | `tests/conftest.py`의 `mock_rag_client` 필수 필드 합의 |
| Phase 2 완료 | `tests/test_e2e.py` E2E 시나리오 3개 작성 |
| Phase 5 완료 | `README.md` 업데이트, `develop` → `main` 머지, v1.0.0 태그 |

---

## 파일 소유권 요약

```
ai/
├── agents/
│   ├── initial_interview.py     ← A
│   ├── rag_search.py            ← B
│   ├── service_select.py        ← B  (Phase 1 공동 학습 후 구현)
│   ├── rag_detail.py            ← B
│   ├── detail_interview.py      ← A
│   ├── document_guidance.py     ← A
│   ├── draft_writer.py          ← B
│   └── report_writer.py         ← A
├── graph/
│   ├── state.py                 ← 공동
│   └── builder.py               ← 공동
├── tools/
│   ├── llm.py                   ← A
│   ├── rag_client.py            ← B
│   └── prompt_loader.py         ← A
├── prompts/
│   ├── initial_interview.txt    ← A
│   ├── detail_interview.txt     ← A
│   ├── document_guidance.txt    ← A
│   ├── draft_writer.txt         ← B
│   └── report_writer.txt        ← A
├── tests/
│   ├── conftest.py              ← A (mock_llm) + B (mock_rag_client)
│   ├── test_smoke.py            ← 기존
│   ├── test_state.py            ← 공동
│   ├── test_graph.py            ← 공동
│   ├── test_rag_client_stub.py  ← B
│   ├── test_initial_interview.py ← A
│   ├── test_rag_search.py       ← B
│   ├── test_service_select.py   ← B
│   ├── test_rag_detail.py       ← B
│   ├── test_detail_interview.py ← A
│   ├── test_document_guidance.py ← A
│   ├── test_draft_writer.py     ← B
│   ├── test_report_writer.py    ← A
│   ├── test_rag_integration.py  ← B
│   └── test_e2e.py              ← 공동
├── main.py                      ← A
└── server.py                    ← B
```

---

## 난이도 분포

| 난이도 | A | B |
|--------|---|---|
| 높음 | — | `service_select.py` (HitL), `rag_detail.py` (LLM 추론) |
| 중간 | `initial_interview.py`, `detail_interview.py` | `rag_search.py`, `rag_client.py`, `server.py` |
| 낮음 | `document_guidance.py`, `report_writer.py`, `tools/` | `draft_writer.py` |
| 공동 | `graph/builder.py` ★ 가장 어려운 파트 | `graph/builder.py` ★ 가장 어려운 파트 |


---

## Phase별 착수 순서

```
Phase 1 (A·B 공동 선행)
  → graph/state.py + graph/builder.py + interrupt() 패턴 확인
  → 완료 후 Phase 2 병렬 착수

Phase 2 (병렬 진행, RAG 계약 먼저 확정)
  A: tools/ → initial_interview → detail_interview → document_guidance → report_writer
  B: rag_client stub → rag_search → rag_detail → service_select → draft_writer

Phase 3 (B)
  B: rag_client.py 실제 httpx 구현으로 교체

Phase 4 (A)
  A: tools/llm.py Ollama 전환

Phase 5 (A·B 병렬)
  A: main.py CLI 완성
  B: server.py FastAPI 서버
  A·B: test_e2e.py, README.md
```
