# 복지 서비스 자가진단 AI 에이전트 개발 계획서

> 작성일: 2026-04-15  
> 최종 수정: 2026-04-17 (RAG JSON 쿼리 / 폴백 제거 / draft_writer → 신청서 작성 가이드 / report_writer 역할 조정 / checkpointer 추가 / messages Reducer 수정 / 모델 설계 개선 / 에러 처리 보강 / 프롬프트 관리 전략 추가 / Web API 모드 추가 / 테스트 파일 누락 추가 / RAG 계약 확정 시점 조정 / rag_detail LLM 명시 / detail_interview pass-through 명세 / 루트 CLAUDE.md 노드 수 수정 / service_select Section 5 interrupt() HitL 명세 추가)
> 브랜치 전략: `main` (배포) ← `develop` (통합) ← `feat/*` / `fix/*` / `chore/*`

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [데이터 모델](#3-데이터-모델)
4. [개발 단계별 계획](#4-개발-단계별-계획)
   - [Phase 1: 핵심 상태 및 그래프 기반 구축](#phase-1-핵심-상태-및-그래프-기반-구축)
   - [Phase 2: 에이전트 노드 구현](#phase-2-에이전트-노드-구현)
   - [Phase 3: RAG 통합 (ChromaDB)](#phase-3-rag-통합-chromadb)
   - [Phase 4: 로컬 LLM 전환 (Ollama)](#phase-4-로컬-llm-전환-ollama)
   - [Phase 5: 최종 통합 및 품질 개선](#phase-5-최종-통합-및-품질-개선)
5. [에이전트 노드 상세 명세](#5-에이전트-노드-상세-명세)
6. [테스트 전략](#6-테스트-전략)
7. [디렉터리 구조 (목표)](#7-디렉터리-구조-목표)
8. [프롬프트 관리 전략](#8-프롬프트-관리-전략)
9. [환경 변수 관리](#9-환경-변수-관리)
10. [협업 규칙](#10-협업-규칙)

---

## 1. 프로젝트 개요

### 목표

사용자가 최소한의 정보를 입력하면 AI 에이전트가 RAG로 지원 가능한 복지 서비스 후보 목록을 제시하고, 사용자가 원하는 서비스를 선택하면 해당 서비스에 특화된 추가 인터뷰를 진행하여 신청서 각 항목별 작성 가이드와 최종 보고서를 생성하는 챗봇 시스템.

### 사용자 흐름

```
사용자 입력
    │
    ▼
[1단계 인터뷰 에이전트]  ──(정보 부족)──▶ (재인터뷰 루프)
  최소 정보 수집
  (나이, 소득, 장애여부 등 핵심 필드만)
    │ 최소 정보 수집 완료
    ▼
[RAG 검색 — 후보 목록]
  수집된 최소 정보로 RAG 쿼리
  → 지원 가능해 보이는 복지 서비스 N개 반환
    │
    ▼
[서비스 선택]  ← 사용자가 목록 중 하나 선택
    │
    ▼
[RAG 검색 — 상세 정보]
  선택된 서비스의 상세 정보 조회
  (자격 요건, 필요 서류, 신청 방법 등)
    │
    ▼
[2단계 인터뷰 에이전트]  ──(정보 부족)──▶ (재인터뷰 루프)
  선택된 서비스에 특화된 추가 정보 수집
    │ 필요 정보 모두 수집 완료
    ▼
[서류 안내 에이전트]  ──▶ 필요 서류 목록 안내
    │
    ▼
[신청서 작성 가이드 에이전트]  ──▶ 신청서 항목별 작성 방법 가이드 생성
  (HWP 파일 생성 불가 → 각 항목을 어떻게 써야 하는지 사용자 정보 기반으로 안내)
    │
    ▼
[최종 보고서 에이전트]  ──▶ 가이드 내용을 사용자가 읽기 좋게 재구성하여 출력
```

### 기술 스택

| 분류 | 현재 | 향후 전환 |
|------|------|-----------|
| LLM | Google Gemini 2.5 Flash | Ollama (로컬 Llama) |
| 오케스트레이션 | LangGraph | LangGraph (유지) |
| LLM 추상화 | LangChain | LangChain (유지) |
| 벡터 DB | - | ChromaDB (RAG 서비스 via HTTP) |
| 데이터 검증 | Pydantic v2 | Pydantic v2 (유지) |
| 패키지 관리 | uv | uv (유지) |

---

## 2. 시스템 아키텍처

### LangGraph 노드 구성

```
┌──────────────────────────────────────────────────────────────────┐
│                        LangGraph Graph                           │
│                                                                  │
│  ┌───────┐   ┌─────────────────┐                                 │
│  │ START │──▶│ initial_interview│◀─────────────────────┐         │
│  └───────┘   └────────┬────────┘  (정보 부족 루프)      │         │
│                       │ 최소 정보 완료                           │
│                       ▼                                          │
│              ┌─────────────────┐                                 │
│              │  rag_search     │  JSON 전송 → RAG가 자연어 변환   │
│              └────────┬────────┘                                 │
│                  결과 있음│        │결과 없음                      │
│                         │        └──────────────▶ END            │
│                         ▼          (LLM 폴백 없음)               │
│              ┌─────────────────┐                                 │
│              │ service_select  │  사용자가 서비스 선택 (HitL)     │
│              └────────┬────────┘                                 │
│                       │                                          │
│                       ▼                                          │
│              ┌─────────────────┐                                 │
│              │ rag_detail      │  선택 서비스 상세 RAG 조회       │
│              └────────┬────────┘                                 │
│                       │                                          │
│              ┌─────────────────┐                                 │
│              │ detail_interview│◀─────────────────────┐         │
│              └────────┬────────┘  (정보 부족 루프)      │         │
│                       │ 서비스 특화 정보 완료                     │
│                       ▼                                          │
│              ┌─────────────────┐                                 │
│              │document_guidance│                                 │
│              └────────┬────────┘                                 │
│                       ▼                                          │
│              ┌─────────────────┐                                 │
│              │  draft_writer   │                                 │
│              └────────┬────────┘                                 │
│                       ▼                                          │
│              ┌─────────────────┐                                 │
│              │  report_writer  │                                 │
│              └────────┬────────┘                                 │
│                       ▼                                          │
│                  ┌─────────┐                                     │
│                  │   END   │                                     │
│                  └─────────┘                                     │
└──────────────────────────────────────────────────────────────────┘
```

### RAG 호출 패턴

RAG 서비스(`rag/`)는 HTTP API로 제공됩니다. AI 에이전트는 두 시점에 RAG를 호출합니다.

| 호출 시점 | 노드 | 전송 형식 | 반환값 |
|-----------|------|-----------|--------|
| 1차 (후보 목록) | `rag_search` | JSON (구조화된 사용자 프로필) → RAG가 내부적으로 자연어 변환 | 지원 가능 서비스 N개 (요약 수준), 결과 없으면 빈 목록 |
| 2차 (상세 조회) | `rag_detail` | JSON (서비스 ID) | 해당 서비스 상세 정보 (자격 요건, 필요 서류, 신청 URL 등) |

**RAG 결과 없음 처리 원칙:** RAG에서 결과를 찾지 못하면 LLM 폴백 없이 "해당 서비스를 제공할 수 없음"을 사용자에게 안내하고 파이프라인을 종료합니다. LLM이 임의로 복지 서비스를 생성하는 것은 정확성 훼손이므로 허용하지 않습니다.

### 상태 흐름

모든 노드는 `AgentState`를 입력받아 업데이트된 `AgentState`를 반환합니다. LangGraph가 노드 간 상태 병합을 자동으로 처리합니다.

---

## 3. 데이터 모델

`graph/state.py`에 Pydantic 모델로 정의합니다.

### UserProfile

```python
from enum import Enum
from pydantic import BaseModel, computed_field

class IncomeLevel(str, Enum):
    BASIC = "기초수급"        # RAG 팀 필드값 기준으로 통일
    NEAR_POOR = "차상위"
    LOW_INCOME = "저소득"
    GENERAL = "일반"

class EmploymentStatus(str, Enum):
    EMPLOYED = "취업"
    UNEMPLOYED = "실업"
    INACTIVE = "비경제활동"

class MaritalStatus(str, Enum):
    SINGLE = "미혼"
    MARRIED = "기혼"
    DIVORCED = "이혼"
    WIDOWED = "사별"

class DisabilitySeverity(StrEnum):
    MILD = "경증"
    SEVERE = "중증"

class Gender(StrEnum):
    MALE = "남성"
    FEMALE = "여성"

class UserProfile(BaseModel):
    # ── 1단계: RAG 검색 최소 필드 ──
    age: int | None = None
    gender: Gender | None = None           # 여성 전용 서비스 필터링, 임신 여부 조건부 수집
    region: str | None = None
    household_size: int | None = None      # 소득 구간 판단 선행 조건
    marital_status: MaritalStatus | None = None
    has_children: bool | None = None
    disability: bool | None = None
    disability_severity: DisabilitySeverity | None = None  # disability=True일 때만
    employment_status: EmploymentStatus | None = None
    income_level: IncomeLevel | None = None  # LLM이 대화로 판단, 직접 입력 X

    @computed_field
    @property
    def is_elderly(self) -> bool | None:
        return self.age >= 65 if self.age is not None else None

    # ── 2단계: 서비스 특화 필드 ──
    disability_type: str | None = None
    disability_grade: str | None = None
    children_ages: list[int] | None = None
    housing_type: str | None = None
    household_type: str | None = None
    is_veteran: bool | None = None
    is_single_parent: bool | None = None

    extra_fields: dict[str, str | int | bool] = {}
```

### WelfareCandidate

```python
class WelfareCandidate(BaseModel):
    # ── 1차 RAG 검색 후 채워짐 (필드명 RAG 응답 기준) ──
    serv_id: str                           # RAG /welfare/search 응답의 "serv_id"
    serv_nm: str                           # RAG /welfare/search 응답의 "serv_nm"
    serv_dgst: str                         # RAG /welfare/search 응답의 "serv_dgst"
    department: str = ""                   # 담당 기관명 — RAG /welfare/search 응답의 "department"
    eligibility_reason: str = ""           # rag_search_node에서 LLM으로 생성
    score: float = 0.0
    priority: int = 0                      # score 내림차순 정렬 후 rag_search_node가 부여
    # ── 2차 RAG 상세 조회 후 채워짐 (Phase 2 rag_detail_node 구현 시 추가) ──
    # GET /welfare/{serv_id} 응답 필드:
    #   tgtr_dtl_cn: str   — 수급 대상 상세 (detail_missing_fields 결정에 사용)
    #   slct_crit_cn: str  — 선정 기준
    #   alw_serv_cn: str   — 서비스 내용
    #   sprt_cyc_nm: str   — 지원 주기
    #   srv_pvsn_nm: str   — 제공 방법
    #   trgter_indvdl: list[str]
    #   intrs_thema: list[str]
    required_documents: list[str] = []    # 현재 빈 배열로 수신 (RAG 미구현)
    application_fields: list[str] = []    # 현재 빈 배열로 수신 (RAG 미구현)
    application_url: str | None = None
    detail_fetched: bool = False
```

### AgentState

```python
from typing import Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # add_messages Reducer 필수: 노드 실행 시 기존 메시지를 덮어쓰지 않고 누적
    messages: Annotated[list[BaseMessage], add_messages]
    user_profile: UserProfile              # 수집된 사용자 정보
    # ── 1단계 인터뷰 ──
    initial_missing_fields: list[str]      # 최소 수집 필드 중 아직 미수집 목록
    # ── RAG 검색 ──
    welfare_candidates: list[WelfareCandidate]  # 후보 복지 서비스 목록 (1차 RAG 결과)
    selected_service: WelfareCandidate | None   # 사용자가 선택한 서비스
    # ── 2단계 인터뷰 ──
    # 정규 필드: 필드명 그대로  예) "household_size"
    # extra 필드: "extra:" 접두사  예) "extra:deposit_amount"
    detail_missing_fields: list[str]       # 서비스 특화 추가 수집 필드 목록
    # ── 후속 에이전트 ──
    document_guidance: str                 # 서류 안내 텍스트
    application_guide: str                 # 신청서 항목별 작성 가이드 텍스트 (초안 X)
    final_report: str                      # 가이드 내용을 사용자 친화적으로 재구성한 최종 보고서
    # current_node 제거: LangGraph가 내부적으로 노드 추적을 처리하므로 별도 관리 불필요
```

> **구현 시 주의:** `AgentState`는 `TypedDict`이므로 기본값을 선언부에 지정할 수 없습니다. 그래프 진입 시 `graph.invoke()`에 전달하는 초기 상태 딕셔너리에서 모든 필드의 기본값(예: `initial_missing_fields=[]`, `welfare_candidates=[]`, `document_guidance=""` 등)을 명시적으로 채워줘야 합니다. 누락된 필드에 접근하면 `KeyError`가 발생합니다.

---

## 4. 개발 단계별 계획

### Phase 1: 핵심 상태 및 그래프 기반 구축

**목표:** 에이전트가 실제로 동작할 수 있는 뼈대(state, graph builder)를 구현합니다.

**작업 목록:**

| # | 작업 | 파일 | 브랜치 |
|---|------|------|--------|
| 1-1 | `AgentState`, `UserProfile`, `WelfareCandidate` Pydantic 모델 정의 | `graph/state.py` | `feat/state-models` |
| 1-2 | LangGraph 그래프 빌더 구현 (노드 등록 + 엣지 연결) | `graph/builder.py` | `feat/graph-builder` |
| 1-3 | 조건부 엣지 함수 구현 (1단계 재인터뷰 / 서비스 선택 후 2단계 재인터뷰) | `graph/builder.py` | `feat/graph-builder` |
| 1-4 | **Checkpointer 설정**: `MemorySaver`(개발용) 또는 `SqliteSaver`(운영용) 그래프에 연결, `interrupt()` 기반 HitL 패턴 확인 | `graph/builder.py` | `feat/graph-builder` |
| 1-5 | `main.py`에서 그래프 실행 진입점 구현 | `main.py` | `feat/graph-builder` |
| 1-6 | Phase 1 단위 테스트 작성 | `tests/test_state.py`, `tests/test_graph.py` | `feat/graph-builder` |

> **`graph/builder.py` 역할:** 이 파일이 LangGraph 그래프 전체를 조립합니다. ①노드 등록(8개 에이전트 함수를 그래프에 추가), ②엣지 연결(노드 간 실행 순서 정의), ③조건부 엣지(재인터뷰 루프 등 분기 처리), ④Checkpointer 연결의 네 가지 역할을 담당합니다.

> **Checkpointer란?** LangGraph가 그래프 실행 중간에 `AgentState`를 저장하는 저장소입니다. `service_select` 노드에서 `interrupt()`로 그래프가 일시 중단되고 사용자 입력을 기다리는데, 이 "멈춤 → 재개" 사이에 서버가 재시작되더라도 저장된 상태에서 이어서 실행할 수 있게 해줍니다. Checkpointer 없이는 `interrupt()` 기반 HitL 패턴이 동작하지 않습니다.

> **Checkpointer 선택 기준:** CLI(개발·테스트)에서는 `MemorySaver`(RAM 저장, 프로세스 종료 시 소멸), 운영(FastAPI 서버 모드)에서는 `SqliteSaver` 또는 `PostgresSaver` 사용. `graph/builder.py`에서 환경 변수(`GRAPH_CHECKPOINTER=memory|sqlite|postgres`)로 분기.
>
> - `memory`: RAM에만 저장. 서버 재시작 시 모든 대화 상태 소멸. 개발/테스트에 적합.
> - `sqlite`: 파일 하나(`checkpoints.db`)에 영구 저장. 별도 DB 서버 불필요 — LangGraph가 테이블 생성·읽기·쓰기를 자동 처리. Phase 5 운영 환경에 적합.
> - `postgres`: 별도 DB 서버 필요. 트래픽이 많아졌을 때 고려.

**완료 기준:**
- `AgentState` 모델 정의 완료 및 Pydantic 검증 통과
- 그래프가 START → END까지 오류 없이 컴파일됨
- Checkpointer를 붙인 상태에서 `interrupt()` 호출 후 재개 동작 확인
- Phase 1 범위 테스트 통과: `uv run pytest tests/test_smoke.py tests/test_state.py tests/test_graph.py -v`
  (Phase 2 이후 테스트는 해당 Phase 완료 기준에서 별도로 검증)

> **RAG API 계약 (`docs/rag_api_contract.md`) 작성은 Phase 2 시작 전까지 완료하면 됩니다.** Phase 2 2-0의 RAG 클라이언트 스텁 인터페이스가 이 계약서를 기준으로 구현되어야 하므로, `feat/rag-client-stub` 브랜치 시작 전 `rag/` 파트와 협의하여 확정합니다.

---

### Phase 2: 에이전트 노드 구현

**목표:** 8개 에이전트/노드를 순서대로 구현합니다. 각 노드는 독립적으로 개발하고 테스트합니다.

> **비동기 통일 원칙:** 모든 에이전트 노드는 `async def`로 구현합니다. RAG HTTP 클라이언트(`tools/rag_client.py`)가 `httpx.AsyncClient`를 사용하므로 이를 호출하는 노드는 반드시 async여야 합니다. LangGraph는 async 노드를 네이티브로 지원하며, sync 노드와 혼재할 경우 런타임 오류가 발생할 수 있으므로 전체를 async로 통일합니다.

#### 2-0. RAG HTTP 클라이언트 사전 구현 (`tools/rag_client.py`)

**브랜치:** `feat/rag-client-stub`

> Phase 2 에이전트 노드(`rag_search`, `rag_detail`)는 `tools/rag_client.py`를 통해 RAG를 호출해야 합니다. 에이전트에서 `httpx`를 직접 호출하는 것은 금지입니다. Phase 2 시작 전에 인터페이스를 먼저 정의하고, Phase 3에서 실제 HTTP 구현으로 교체합니다.

| 작업 | 설명 |
|------|------|
| 인터페이스 정의 | `async def search(profile: dict, top_k: int) -> list[dict]` / `async def get_detail(service_id: str) -> dict` 시그니처 확정 |
| 스텁 구현 | Phase 2에서는 하드코딩된 더미 데이터를 반환하는 스텁으로 구현 (Phase 3에서 실제 HTTP 연동으로 교체) |
| 테스트 | `tests/test_rag_client_stub.py` (인터페이스 계약 검증) |

#### 2-1. 1단계 인터뷰 에이전트 (`agents/initial_interview.py`)

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

#### 2-2. RAG 검색 노드 — 후보 목록 (`agents/rag_search.py`)

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

#### 2-3. 서비스 선택 노드 (`agents/service_select.py`)

**브랜치:** `feat/agent-service-select`

| 작업 | 설명 |
|------|------|
| 후보 목록 표시 | `welfare_candidates`를 사용자에게 번호 목록으로 제시 |
| **HitL 구현** | LangGraph `interrupt(value={"candidates": candidates_list})`로 그래프 실행 중단 → checkpointer가 상태 저장 → 사용자 입력 후 `graph.invoke(Command(resume=user_input), config)` 로 재개 |
| 선택 입력 처리 및 유효성 검사 | `Command(resume=...)` 수신 후 입력값 파싱 → 유효하면 `selected_service` 설정, **유효하지 않으면 오류 메시지를 포함하여 `interrupt()` 재호출** (노드 내부에서 루프 없이 재중단) |
| 테스트 | `tests/test_service_select.py` (interrupt → resume 흐름, 잘못된 입력 → 재interrupt 흐름 포함) |

> **HitL 패턴:** CLI에서는 `interrupt()` 반환값을 출력 후 `input()` 대기, Web(FastAPI)에서는 `interrupt()` 발생 시 HTTP 응답으로 후보 목록 반환 → 다음 요청에서 `Command(resume=선택값)`으로 재개. 두 환경 모두 동일한 그래프 코드를 사용하며 인터페이스 계층에서만 분기.

> **잘못된 입력 처리 패턴:** `interrupt()` 이후 유효하지 않은 입력이 들어오면 노드 내부 루프 없이 `interrupt(value={"candidates": candidates_list, "error": "잘못된 입력입니다. 번호를 입력해 주세요."})`를 다시 호출합니다. 이 방식이 노드 내부 루프 방식보다 안전한 이유는 Checkpointer가 매 중단 시점의 상태를 저장하므로 서버 재시작 시에도 재개가 가능하기 때문입니다.

#### 2-4. RAG 상세 조회 노드 (`agents/rag_detail.py`)

**브랜치:** `feat/agent-rag-detail`

| 작업 | 설명 |
|------|------|
| 상세 조회 구현 | `selected_service.service_id`로 RAG 상세 정보 조회 |
| 상태 업데이트 | `selected_service`의 `required_documents`, `application_url` 등 상세 필드 채우기 |
| `detail_missing_fields` 계산 | RAG에서 반환된 자격 요건(`eligibility`)을 LLM에 전달하여 현재 `user_profile`에서 부족한 필드 목록을 추론 (structured output으로 `list[str]` 반환) |
| **HTTP 장애 처리** | 네트워크 오류 시 "상세 정보 조회 실패" 안내 후 그래프 종료 |
| 테스트 | `tests/test_rag_detail.py` (HTTP 오류 시나리오 포함) |

#### 2-5. 2단계 인터뷰 에이전트 (`agents/detail_interview.py`)

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

#### 2-6. 서류 안내 에이전트 (`agents/document_guidance.py`)

**브랜치:** `feat/agent-document`

| 작업 | 설명 |
|------|------|
| 프롬프트 작성 | 선택된 서비스의 상세 정보(RAG 조회 결과)를 기반으로 서류 안내 (`prompts/document_guidance.txt`) |
| 서류 목록 정리 | 필요 서류를 사용자 상황에 맞게 필터링하여 안내 텍스트 생성 |
| 테스트 | `tests/test_document_guidance.py` |

#### 2-7. 신청서 작성 가이드 에이전트 (`agents/draft_writer.py`)

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

#### 2-8. 보고서 에이전트 (`agents/report_writer.py`)

**브랜치:** `feat/agent-report`

> `draft_writer`가 생성한 가이드 원문을 사용자가 읽기 좋은 형태로 재구성합니다. 새로운 정보를 추가하거나 생성하지 않고, 가이드의 내용을 자연스러운 문장과 구조로 변환하는 역할입니다.

| 작업 | 설명 |
|------|------|
| 프롬프트 작성 | `application_guide`를 사용자 친화적 문체와 구조로 변환하는 프롬프트 (`prompts/report_writer.txt`) |
| 보고서 포맷 정의 | 마크다운 구조화 텍스트 (섹션별 안내, 핵심 내용 강조) |
| 테스트 | `tests/test_report_writer.py` |

**Phase 2 완료 기준:**
- 8개 노드 모두 `AgentState`를 입력받아 올바른 상태 업데이트 반환
- 1단계 및 2단계 인터뷰 재진입 루프가 정상 동작
- RAG 결과 없음 시 파이프라인이 적절히 종료됨
- 전체 파이프라인 E2E 테스트 통과 (`tests/test_e2e.py`)

---

### Phase 3: RAG 통합 (ChromaDB)

**목표:** `rag/` 서비스와 실제 연동하여 복지 서비스 데이터 기반의 2단계 RAG 검색을 구현합니다.

**브랜치:** `feat/rag-integration`

| # | 작업 | 파일 |
|---|------|------|
| 3-1 | `tools/rag_client.py` 스텁을 실제 `httpx.AsyncClient` HTTP 구현으로 교체 | `tools/rag_client.py` |
| 3-2 | 1차 RAG 쿼리: 최소 프로필 → 서비스 후보 N개 실제 연동 검증 | `agents/rag_search.py` |
| 3-3 | 2차 RAG 쿼리: 서비스 ID → 상세 정보 조회 실제 연동 검증 | `agents/rag_detail.py` |
| 3-4 | 환경 변수에 `RAG_SERVICE_URL` 설정 추가 | `.env.example` 수정 |
| 3-5 | RAG 통합 테스트 | `tests/test_rag_integration.py` |

**RAG API 계약** (Phase 2 모킹의 기준 — 아래 스키마 기준으로 스텁 및 모킹 구현):

> **확정 스펙 (2026-04-20 rag/ 팀 PR #7 기준):** 엔드포인트 경로 및 메서드가 아래와 같이 확정되었습니다.

```
# 1차: 후보 목록 검색 — AI는 JSON을 전송, 자연어 변환은 RAG 내부에서 처리
POST /welfare/search
Body: {
  "profile": {
    "age": 65,
    "income_level": "기초생활수급자",
    "disability": false,
    "employment_status": "비경제활동",
    "region": "서울"
  },
  "top_k": 5
}
Response: [
  {
    "id": "welfare_001",
    "name": "기초연금",
    "department": "보건복지부",          # WelfareCandidate.department
    "summary": "만 65세 이상 저소득 노인 연금",
    "eligibility_reason": "나이 65세 이상, 기초생활수급자 조건 충족",  # WelfareCandidate.eligibility_reason
    "score": 0.92                         # WelfareCandidate.score → priority로 변환
  },
  ...
]
# 결과 없으면: []  (LLM 폴백 없음 — 빈 목록 그대로 반환)

# 2차: 상세 정보 조회 — 서비스 ID를 경로 파라미터로 조회 (POST → GET 변경)
GET /welfare/{serv_id}
Response: {
  "id": "welfare_001",
  "name": "기초연금",
  "department": "보건복지부",
  "eligibility": { ... },
  "application_fields": ["신청인 성명", "생년월일", "소득 수준", ...],  # draft_writer 필수 의존
  "required_documents": ["신분증", "통장사본", ...],
  "application_url": "https://www.bokjiro.go.kr"
}
```

> **필드 책임 분리:** `eligibility_reason`과 `department`는 RAG `/search` 응답에 포함해야 합니다. `application_fields`는 RAG `/services/detail` 응답에 반드시 포함해야 합니다. 두 필드 모두 `rag/` 파트에서 제공하지 않으면 `WelfareCandidate` 모델이 제대로 채워지지 않습니다.

**완료 기준:**
- 실제 RAG 서비스를 통해 후보 목록과 상세 정보 조회 가능
- RAG 결과 없음(빈 목록) 시 에이전트가 LLM 생성 없이 사용자에게 안내 후 종료
- 검색 관련성(relevance) 기준 테스트 통과

---

### Phase 4: 로컬 LLM 전환 (Ollama)

**목표:** Google Gemini API 의존성을 제거하고 로컬 Ollama로 전환합니다.

**브랜치:** `feat/ollama-migration`

| # | 작업 | 파일 |
|---|------|------|
| 4-1 | `langchain-community` Ollama 통합 확인 | `tools/llm.py` |
| 4-2 | `tools/llm.py`에서 Ollama 코드 활성화, Gemini 코드 제거 | `tools/llm.py` |
| 4-3 | `.env.example`에 `OLLAMA_BASE_URL`, `OLLAMA_MODEL` 추가 | `.env.example` |
| 4-4 | CI 환경에서 Ollama 없이 테스트 가능하도록 LLM 모킹 구성 | `tests/conftest.py` |
| 4-5 | 전환 후 전체 파이프라인 동작 검증 | E2E 테스트 재실행 |

**완료 기준:**
- `GOOGLE_API_KEY` 없이 로컬에서 전체 파이프라인 동작
- 기존 테스트 코드 수정 없이 CI 통과

---

### Phase 5: 최종 통합 및 품질 개선

**목표:** 전체 시스템 안정화, 에러 처리 강화, 실사용 품질 확보.

**브랜치:** `feat/final-integration`

| # | 작업 |
|---|------|
| 5-1 | 에러 처리 보강: LLM 응답 파싱 실패 최대 재시도 횟수 조정, 회복 불가 시 사용자 친화적 메시지 출력 |
| 5-2 | 대화 히스토리 관리: 컨텍스트 길이 초과 방지 (요약 또는 슬라이딩 윈도우) |
| 5-3 | `main.py` CLI 인터페이스 구현 (대화형 루프, 서비스 선택 UX 포함, `interrupt()` 재개 패턴 포함) |
| 5-4 | **FastAPI 서버 모드 구현** (`server.py`): Next.js 프론트엔드 연동을 위한 REST API 래퍼, `POST /chat` 엔드포인트, `interrupt()` 발생 시 대기 응답 반환, `POST /resume`으로 선택값 수신 후 재개. **`thread_id` 세션 관리 방식(쿠키, 응답 바디 등)은 Phase 5에서 프론트엔드 팀과 협의하여 확정** |
| 5-5 | 통합 E2E 테스트 시나리오 확장 (다양한 사용자 유형) |
| 5-6 | `README.md` 업데이트 (CLI 사용 방법, API 사용 방법, 아키텍처 다이어그램) |
| 5-7 | `develop` → `main` 머지 및 v1.0.0 태그 |

---

## 5. 에이전트 노드 상세 명세

### 1단계 인터뷰 에이전트 (`initial_interview_node`)

**입력:** `AgentState` (초기 또는 재진입 상태)

**출력:** 업데이트된 `user_profile`(최소 필드), `initial_missing_fields`, `messages`

**핵심 동작:**
1. `initial_missing_fields`를 확인하여 아직 수집 안 된 최소 필드를 파악
2. LLM에 시스템 프롬프트 + 대화 히스토리를 전달하여 다음 질문 생성
3. 사용자 응답에서 structured output으로 최소 필드값 추출
4. 모든 최소 필드가 채워지면 `initial_missing_fields = []`로 설정

---

### RAG 검색 노드 — 후보 목록 (`rag_search_node`)

**입력:** `AgentState` (완성된 최소 `user_profile`)

**출력:** 업데이트된 `welfare_candidates`

**핵심 동작:**
1. `user_profile` 최소 필드를 JSON으로 직렬화하여 RAG 서비스 `POST /welfare/search`에 전송
2. 자연어 변환은 RAG 서비스 내부에서 처리 — AI 파트는 JSON 전송만 담당
3. 응답을 `WelfareCandidate` 목록으로 변환 (상세 정보 미포함 상태)
4. **결과가 빈 목록인 경우 LLM 폴백 없이 사용자에게 "해당하는 서비스를 찾지 못했습니다" 안내 후 END로 라우팅**

---

### 서비스 선택 노드 (`service_select_node`)

**입력:** `AgentState` (완성된 `welfare_candidates`)

**출력:** 업데이트된 `selected_service`, `messages`

**핵심 동작:**
1. `welfare_candidates` 목록을 번호와 함께 사용자에게 표시한 후 `interrupt(value={"candidates": ...})`로 그래프 실행 중단 — checkpointer가 상태 저장 → `Command(resume=user_input)`으로 재개
2. 유효한 입력이면 `selected_service` 설정, 유효하지 않으면 오류 메시지를 포함하여 `interrupt()` 재호출 (노드 내부 루프 없음)
3. Checkpointer 필수: `interrupt()` 기반 HitL은 checkpointer 없이 동작하지 않음

---

### RAG 상세 조회 노드 (`rag_detail_node`)

**입력:** `AgentState` (`selected_service` 설정 완료)

**출력:** 업데이트된 `selected_service`(상세 필드 채워짐), `detail_missing_fields`

**핵심 동작:**
1. `selected_service.service_id`로 RAG `GET /welfare/{serv_id}` 조회
2. 응답으로 `selected_service`의 `required_documents`, `application_url` 등 상세 필드 채우기
3. RAG 응답의 자격 요건(`eligibility`)을 **LLM에 전달(structured output)**하여 현재 `user_profile`에서 부족한 필드 목록을 추론 → `detail_missing_fields`에 설정
   - `UserProfile` 정규 필드에 있으면 → 필드명 그대로 추가 (예: `"household_size"`)
   - `UserProfile`에 없는 필드면 → `"extra:"` 접두사로 추가 (예: `"extra:deposit_amount"`)
   - **`detail_missing_fields`가 빈 목록으로 결정된 경우**: 이후 `detail_interview` 노드는 LLM 호출 없이 즉시 반환(`detail_missing_fields = []` 유지 → `route_after_detail_interview`가 `document_guidance`로 라우팅)

---

### 2단계 인터뷰 에이전트 (`detail_interview_node`)

**입력:** `AgentState` (선택된 서비스 상세 정보 + 현재 `user_profile`)

**출력:** 업데이트된 `user_profile`(서비스 특화 필드), `detail_missing_fields`, `messages`

**핵심 동작:**
1. `detail_missing_fields`가 비어 있으면 LLM 호출 없이 즉시 반환 (pass-through) — `rag_detail`에서 이미 모든 필드가 충족된 경우
2. `detail_missing_fields`를 순회하며 아직 수집 안 된 항목에 대한 질문 생성
3. 정규 필드(`"household_size"` 등) → `user_profile`의 해당 필드에 저장
4. extra 필드(`"extra:deposit_amount"` 등) → `user_profile.extra_fields[키]`에 저장
5. 모든 항목 수집 완료 시 `detail_missing_fields = []`로 설정

---

### 서류 안내 에이전트 (`document_guidance_node`)

**입력:** `AgentState` (완성된 `selected_service` + `user_profile`)

**출력:** 업데이트된 `document_guidance`

**핵심 동작:**
1. `selected_service.required_documents`를 기반으로 서류 목록 정리
2. 사용자 상황에 맞게 필요 서류 필터링 및 발급 방법 안내
3. 안내 텍스트를 사용자 친화적 형식으로 생성

---

### 신청서 작성 가이드 에이전트 (`draft_writer_node`)

**입력:** `AgentState` (완성된 `user_profile` + `selected_service` 상세 정보)

**출력:** 업데이트된 `application_guide`

**핵심 동작:**
1. `selected_service.application_fields`(RAG에서 가져온 신청서 항목 목록)를 순서대로 처리
2. 각 항목에 대해 `user_profile` 정규 필드 → `user_profile.extra_fields` 순서로 값을 탐색하여 "어떻게 써야 하는지" 설명 생성
3. 사용자 정보로 판단 불가한 항목은 `[직접 확인 필요: 이유]` 형식으로 표시
4. HWP 등 실제 서식 파일은 생성하지 않음

---

### 보고서 에이전트 (`report_writer_node`)

**입력:** `AgentState` (`application_guide` + `document_guidance` + `selected_service`)

**출력:** 업데이트된 `final_report`

**핵심 동작:**
1. `draft_writer`가 생성한 `application_guide`를 새로운 정보 추가 없이 사용자 친화적 문체로 재구성
2. `document_guidance`(서류 안내)와 함께 통합하여 읽기 좋은 형태로 출력
3. 에이전트가 정보를 새로 창작하거나 생성하지 않음 — 변환과 재구성만 수행

**최종 보고서 구성:**
```
# 복지 서비스 신청 안내

## 1. 선택한 복지 서비스 안내
## 2. 필요 서류 목록
## 3. 신청서 작성 가이드 (항목별)
## 4. 다음 단계 안내 (신청 방법, 문의처, 신청 URL 등)
```

---

## 6. 테스트 전략

### 테스트 레벨

| 레벨 | 파일 | 목적 |
|------|------|------|
| 스모크 | `tests/test_smoke.py` | CI 기본 통과 확인 (현재 존재) |
| 단위 | `tests/test_state.py` | Pydantic 모델 검증 |
| 단위 | `tests/test_rag_client_stub.py` | RAG 클라이언트 스텁 인터페이스 계약 검증 (Phase 2) |
| 단위 | `tests/test_prompts.py` | 프롬프트 파일 로딩 및 키워드 포함 여부 검증 |
| 단위 | `tests/test_initial_interview.py` | 1단계 인터뷰 노드 로직 |
| 단위 | `tests/test_rag_search.py` | RAG 후보 검색 노드 로직 (RAG 모킹) |
| 단위 | `tests/test_service_select.py` | 서비스 선택 노드 로직 |
| 단위 | `tests/test_rag_detail.py` | RAG 상세 조회 노드 로직 (RAG 모킹) |
| 단위 | `tests/test_detail_interview.py` | 2단계 인터뷰 노드 로직 |
| 단위 | `tests/test_document_guidance.py` | 서류 안내 노드 로직 |
| 단위 | `tests/test_draft_writer.py` | 신청서 작성 가이드 노드 로직 |
| 단위 | `tests/test_report_writer.py` | 보고서 노드 로직 |
| 통합 | `tests/test_graph.py` | 그래프 컴파일 및 노드 연결 |
| 통합 | `tests/test_rag_integration.py` | 실제 RAG 서비스 연동 (Phase 3) |
| E2E | `tests/test_e2e.py` | 전체 파이프라인 시나리오 테스트 |

### LLM 모킹 전략

실제 API 호출 없이 테스트하기 위해 `conftest.py`에서 LLM과 RAG 클라이언트를 모킹합니다.

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.invoke.return_value.content = "모킹된 응답"
    return llm

@pytest.fixture
def mock_rag_client():
    client = AsyncMock()
    # 1차 검색 응답 모킹 (아래는 예시 — 실제 구현 시 RAG API 계약 스키마에 맞춰 모든 필수 필드 포함)
    client.search.return_value = {
        "results": [
            {"serv_id": "WLF00000035", "serv_nm": "기초연금", "serv_dgst": "만 65세 이상 저소득 노인 연금", "score": 0.95},
        ]
    }
    # 2차 상세 조회 응답 모킹
    client.get_detail.return_value = {
        "serv_id": "WLF00000035",
        "required_documents": [],   # 현재 빈 배열로 합의
        "application_fields": [],   # 현재 빈 배열로 합의
        "application_url": "https://www.bokjiro.go.kr",
    }
    return client
```

> **모킹 스키마 준수:** 필드명은 RAG API 응답 기준(`serv_id`, `serv_nm`, `serv_dgst`)을 따릅니다. `required_documents`, `application_fields`는 현재 RAG API 미구현으로 빈 배열로 수신합니다.

### 테스트 시나리오 (E2E)

| 시나리오 | 사용자 유형 | 예상 후보 서비스 | 선택 서비스 |
|----------|------------|-----------------|------------|
| 시나리오 A | 65세 이상 독거노인, 기초생활수급자 | 기초연금, 노인 돌봄, 의료급여 등 | 기초연금 선택 |
| 시나리오 B | 30대 실업자, 장애 2급 | 장애인 고용 지원, 실업급여, 장애인 활동 지원 등 | 장애인 활동 지원 선택 |
| 시나리오 C | 4인 가족, 차상위계층, 미취학 자녀 | 아동 수당, 보육 지원, 한부모 지원 등 | 아동 수당 선택 |

---

## 7. 디렉터리 구조 (목표)

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
    ├── development_plan.md   # 이 파일
    └── rag_api_contract.md   # RAG API 계약서 (Phase 2 시작 전 확정)
```

---

## 8. 프롬프트 관리 전략

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

## 9. 환경 변수 관리

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

## 10. 협업 규칙

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

---

## 진행 상황 트래킹

| Phase | 상태 | 완료 조건 |
|-------|------|-----------|
| Phase 1: 상태 + 그래프 기반 | 대기 | 그래프 컴파일 + checkpointer + interrupt() 동작 + 기본 테스트 통과 |
| Phase 2: 에이전트 노드 8개 | 대기 | E2E 파이프라인 동작 (RAG 모킹 사용), structured output 파싱 실패 처리 포함 |
| Phase 3: RAG 실제 연동 | 대기 | 실제 RAG 서비스 기반 후보 목록 + 상세 조회, HTTP 오류 처리 포함 |
| Phase 4: Ollama 전환 | 대기 | API 키 없이 로컬 동작 |
| Phase 5: 최종 통합 | 대기 | CLI + FastAPI 서버 모드 동작, v1.0.0 릴리즈 |
