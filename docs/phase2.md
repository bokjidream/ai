# Phase 2: 에이전트 노드 구현

> [← 인덱스로 돌아가기](development_plan.md)

**목표:** 8개 에이전트/노드를 순서대로 구현합니다. 각 노드는 독립적으로 개발하고 테스트합니다.

> **비동기 통일 원칙:** 모든 에이전트 노드는 `async def`로 구현합니다. RAG HTTP 클라이언트(`tools/rag_client.py`)가 `httpx.AsyncClient`를 사용하므로 이를 호출하는 노드는 반드시 async여야 합니다. LangGraph는 async 노드를 네이티브로 지원하며, sync 노드와 혼재할 경우 런타임 오류가 발생할 수 있으므로 전체를 async로 통일합니다.

---

## 2-0. RAG HTTP 클라이언트 사전 구현 (`tools/rag_client.py`)

**브랜치:** `feat/rag-client-stub`

> Phase 2 에이전트 노드(`rag_search`, `rag_detail`)는 `tools/rag_client.py`를 통해 RAG를 호출해야 합니다. 에이전트에서 `httpx`를 직접 호출하는 것은 금지입니다. Phase 2 시작 전에 인터페이스를 먼저 정의하고, Phase 3에서 실제 HTTP 구현으로 교체합니다.

| 작업 | 설명 |
|------|------|
| 인터페이스 정의 | `async def search(profile: dict, top_k: int) -> list[dict]` / `async def get_detail(service_id: str) -> dict` 시그니처 확정 |
| 스텁 구현 | Phase 2에서는 하드코딩된 더미 데이터를 반환하는 스텁으로 구현 (Phase 3에서 실제 HTTP 연동으로 교체) |
| 테스트 | `tests/test_rag_client_stub.py` (인터페이스 계약 검증) |

---

## 2-1. 1단계 인터뷰 에이전트 (`agents/initial_interview.py`)

**브랜치:** `feat/agent-initial-interview`

| 작업 | 설명 |
|------|------|
| 프롬프트 작성 | 최소 필드(나이, 소득, 장애 여부, 취업 상태, 거주 지역)만 자연스럽게 수집하는 프롬프트 (`prompts/initial_interview.txt` 외부 파일로 관리) |
| 정보 추출 로직 | LLM 응답에서 UserProfile 핵심 필드값 파싱 (structured output) |
| **파싱 실패 처리** | `with_structured_output()` 실패 시 최대 2회 재시도 후 실패한 필드는 `initial_missing_fields`에 유지 (Phase 5까지 기다리지 않고 기본 처리) |
| 누락 필드 감지 | `initial_missing_fields` 업데이트 로직 |
| 재진입 처리 | 이전 대화 히스토리를 context로 활용하여 중복 질문 방지 |
| 테스트 | `tests/test_initial_interview.py` |

**최소 수집 필드 (우선순위 순):**
- `age` (나이)
- `income_level` (소득 수준)
- `disability` (장애 여부)
- `employment_status` (취업 상태)
- `region` (거주 지역)

**조건부 엣지 함수:**
```python
def route_after_initial_interview(state: AgentState) -> str:
    if state["initial_missing_fields"]:
        return "initial_interview"   # 재진입
    return "rag_search"              # 1차 RAG 검색으로 이동
```

---

## 2-2. RAG 검색 노드 — 후보 목록 (`agents/rag_search.py`)

**브랜치:** `feat/agent-rag-search`

| 작업 | 설명 |
|------|------|
| `rag_client` 호출 | `tools/rag_client.py`의 `search()` 를 통해 RAG 서비스 호출 (Phase 2에서는 스텁 반환 — 직접 `httpx` 호출 금지) |
| JSON 쿼리 직렬화 | `UserProfile` 최소 필드를 JSON으로 직렬화하여 전송 (자연어 변환은 RAG 내부 처리) |
| 후보 목록 파싱 | RAG 응답을 `WelfareCandidate` 목록으로 변환 (`score` → `priority` 변환 포함) |
| 우선순위 정렬 | `score` 내림차순 정렬 후 `priority` 필드에 순위 기록, 상위 N개 반환 (기본 N=5) |
| 결과 없음 처리 | RAG 결과가 빈 목록이면 사용자에게 안내 후 그래프 종료 (LLM 폴백 없음) |
| **HTTP 장애 처리** | `httpx.TimeoutException`, `httpx.ConnectError` 등 네트워크 오류 발생 시 사용자에게 "서비스 연결 실패" 안내 후 그래프 종료 (재시도 1회 허용) |
| 테스트 | `tests/test_rag_search.py` (RAG 서비스 모킹, HTTP 오류 시나리오 포함) |

**조건부 엣지 함수:**
```python
def route_after_rag_search(state: AgentState) -> str:
    if not state["welfare_candidates"]:
        return END     # 결과 없음 → 파이프라인 종료 (LLM 폴백 없음)
    return "service_select"
```

---

## 2-3. 서비스 선택 노드 (`agents/service_select.py`)

**브랜치:** `feat/agent-service-select`

| 작업 | 설명 |
|------|------|
| 후보 목록 표시 | `welfare_candidates`를 사용자에게 번호 목록으로 제시 |
| **HitL 구현** | LangGraph `interrupt(value={"candidates": candidates_list})`로 그래프 실행 중단 → checkpointer가 상태 저장 → 사용자 입력 후 `graph.invoke(Command(resume=user_input), config)` 로 재개 |
| 선택 입력 처리 및 유효성 검사 | `Command(resume=...)` 수신 후 입력값 파싱 → 유효하면 `selected_service` 설정, **유효하지 않으면 오류 메시지를 포함하여 `interrupt()` 재호출** (노드 내부에서 루프 없이 재중단) |
| 테스트 | `tests/test_service_select.py` (interrupt → resume 흐름, 잘못된 입력 → 재interrupt 흐름 포함) |

> **HitL 패턴:** CLI에서는 `interrupt()` 반환값을 출력 후 `input()` 대기, Web(FastAPI)에서는 `interrupt()` 발생 시 HTTP 응답으로 후보 목록 반환 → 다음 요청에서 `Command(resume=선택값)`으로 재개. 두 환경 모두 동일한 그래프 코드를 사용하며 인터페이스 계층에서만 분기.

> **잘못된 입력 처리 패턴:** `interrupt()` 이후 유효하지 않은 입력이 들어오면 노드 내부 루프 없이 `interrupt(value={"candidates": candidates_list, "error": "잘못된 입력입니다. 번호를 입력해 주세요."})`를 다시 호출합니다. 이 방식이 노드 내부 루프 방식보다 안전한 이유는 Checkpointer가 매 중단 시점의 상태를 저장하므로 서버 재시작 시에도 재개가 가능하기 때문입니다.

---

## 2-4. RAG 상세 조회 노드 (`agents/rag_detail.py`)

**브랜치:** `feat/agent-rag-detail`

| 작업 | 설명 |
|------|------|
| 상세 조회 구현 | `selected_service.service_id`로 RAG 상세 정보 조회 |
| 상태 업데이트 | `selected_service`의 `required_documents`, `application_url` 등 상세 필드 채우기 |
| `detail_missing_fields` 계산 | RAG에서 반환된 자격 요건(`eligibility`)을 LLM에 전달하여 현재 `user_profile`에서 부족한 필드 목록을 추론 (structured output으로 `list[str]` 반환) |
| **HTTP 장애 처리** | 네트워크 오류 시 "상세 정보 조회 실패" 안내 후 그래프 종료 |
| 테스트 | `tests/test_rag_detail.py` (HTTP 오류 시나리오 포함) |

---

## 2-5. 2단계 인터뷰 에이전트 (`agents/detail_interview.py`)

**브랜치:** `feat/agent-detail-interview`

| 작업 | 설명 |
|------|------|
| 프롬프트 작성 | 선택된 서비스의 자격 요건을 context로 활용하여 서비스 특화 추가 질문 생성 (`prompts/detail_interview.txt`) |
| 정보 추출 로직 | UserProfile의 서비스 특화 필드값 파싱 (structured output) |
| **파싱 실패 처리** | structured output 실패 시 최대 2회 재시도 후 해당 필드는 `detail_missing_fields`에 유지 |
| 누락 필드 감지 | `detail_missing_fields` 업데이트 로직 (`"extra:"` 접두사 필드는 `user_profile.extra_fields`에 저장) |
| 테스트 | `tests/test_detail_interview.py` |

**조건부 엣지 함수:**
```python
def route_after_detail_interview(state: AgentState) -> str:
    if state["detail_missing_fields"]:
        return "detail_interview"    # 재진입
    return "document_guidance"       # 다음 단계
```

---

## 2-6. 서류 안내 에이전트 (`agents/document_guidance.py`)

**브랜치:** `feat/agent-document`

| 작업 | 설명 |
|------|------|
| 프롬프트 작성 | 선택된 서비스의 상세 정보(RAG 조회 결과)를 기반으로 서류 안내 (`prompts/document_guidance.txt`) |
| 서류 목록 정리 | 필요 서류를 사용자 상황에 맞게 필터링하여 안내 텍스트 생성 |
| 테스트 | `tests/test_document_guidance.py` |

---

## 2-7. 신청서 작성 가이드 에이전트 (`agents/draft_writer.py`)

**브랜치:** `feat/agent-draft`

> HWP 등 실제 서식 파일 생성은 기술적으로 불가능하므로, 신청서의 각 항목을 **어떻게 작성해야 하는지** 사용자 정보를 근거로 설명하는 가이드를 생성합니다.

| 작업 | 설명 |
|------|------|
| 프롬프트 작성 | 선택된 서비스의 신청서 항목 목록(RAG 상세 정보의 `application_fields`)과 완성된 `UserProfile`을 기반으로 항목별 작성 방법 생성 (`prompts/draft_writer.txt`) |
| 가이드 포맷 정의 | 항목명 → 사용자가 써야 할 내용 및 근거 형식으로 구조화 |
| 미확인 항목 처리 | 사용자 정보로 판단 불가한 항목은 `[직접 확인 필요: 이유]` 형식으로 표시 |
| 테스트 | `tests/test_draft_writer.py` |

**가이드 출력 예시:**
```
[신청인 성명] → 본인 성명 기재
[생년월일]   → 수집된 나이 기반으로 YYYYMMDD 형식 기재
[소득 수준]  → "기초생활수급자"로 기재 (인터뷰 답변 기반)
[장애 등급]  → [직접 확인 필요: 장애인 등록증 확인 후 기재]
```

---

## 2-8. 보고서 에이전트 (`agents/report_writer.py`)

**브랜치:** `feat/agent-report`

> `draft_writer`가 생성한 가이드 원문을 사용자가 읽기 좋은 형태로 재구성합니다. 새로운 정보를 추가하거나 생성하지 않고, 가이드의 내용을 자연스러운 문장과 구조로 변환하는 역할입니다.

| 작업 | 설명 |
|------|------|
| 프롬프트 작성 | `application_guide`를 사용자 친화적 문체와 구조로 변환하는 프롬프트 (`prompts/report_writer.txt`) |
| 보고서 포맷 정의 | 마크다운 구조화 텍스트 (섹션별 안내, 핵심 내용 강조) |
| 테스트 | `tests/test_report_writer.py` |

---

## 완료 기준

- 8개 노드 모두 `AgentState`를 입력받아 올바른 상태 업데이트 반환
- 1단계 및 2단계 인터뷰 재진입 루프가 정상 동작
- RAG 결과 없음 시 파이프라인이 적절히 종료됨
- 전체 파이프라인 E2E 테스트 통과 (`tests/test_e2e.py`)
