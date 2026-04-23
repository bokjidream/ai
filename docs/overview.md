# 프로젝트 개요 · 아키텍처 · 데이터 모델

> [← 인덱스로 돌아가기](development_plan.md)

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

class UserProfile(BaseModel):
    # ── 1단계: RAG 검색 최소 필드 ──
    age: int | None = None
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

> **`disability_severity` 유효성 검사 없음:** `UserProfile` 모델 레벨에서 `disability=False`일 때 `disability_severity`를 자동으로 `None`으로 설정하는 validator가 없습니다. `disability=True`일 때만 수집하는 것은 인터뷰 로직이 담당합니다. 모델에 직접 `disability=False, disability_severity="중증"`을 주입하면 오류 없이 저장됩니다. 테스트 시 주의하세요.

> **`extra_fields` 뮤터블 기본값 안전함:** `extra_fields: dict[str, str | int | bool] = {}`처럼 Pydantic `BaseModel`에서 뮤터블 기본값을 선언해도 안전합니다. Pydantic v2는 인스턴스 생성 시마다 새 딕셔너리를 복사하므로 인스턴스 간 상태가 공유되지 않습니다. (`dataclass`나 순수 Python 클래스와 다름)
