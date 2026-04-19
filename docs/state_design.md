# State 설계

> 작성일: 2026-04-19
> 관련 파일: `graph/state.py`
> 참고 문서: `docs/development_plan.md`

---

## 전체 구조

`graph/state.py`에는 세 가지 모델이 정의된다.

| 모델 | 역할 |
|------|------|
| `UserProfile` | 사용자 정보 (인터뷰로 수집) |
| `WelfareCandidate` | RAG가 반환하는 복지 서비스 후보 1개 |
| `AgentState` | 8개 노드가 공유하는 전체 상태 (메모장) |

---

## UserProfile

사용자로부터 수집하는 정보를 두 단계로 나눠 관리한다.

- **1단계 (`initial_interview`)**: RAG 검색에 필요한 최소 필드 수집
- **2단계 (`detail_interview`)**: 선택한 서비스 자격 확인에 필요한 세부 필드 수집

---

## 1단계 최소 수집 필드

RAG 후보 검색(`rag_search`)에 전달되는 기본 프로필

| 필드 | 타입 | 수집 방식 | 비고 |
|------|------|----------|------|
| `age` | `int` | 직접 질문 | |
| `region` | `str` | 직접 질문 | 시/군/구 단위 |
| `household_size` | `int` | 직접 질문 | 소득 구간 판단 선행 조건 |
| `marital_status` | `enum` | 직접 질문 | 미혼/기혼/이혼/사별 |
| `has_children` | `bool` | 직접 질문 | 미성년 자녀 유무 |
| `disability` | `bool` | 직접 질문 | |
| `disability_severity` | `enum \| None` | 조건부 질문 | `disability=True`일 때만, 경증/중증 |
| `employment_status` | `enum` | 직접 질문 | 취업/실업/비경제활동 |
| `income_level` | `enum` | LLM 판단 | 아래 수집 흐름 참고 |

### income_level 수집 흐름

사용자는 자신의 중위소득 %를 모르는 경우가 대부분이므로, 대화를 통해 LLM이 판단한다.

```
1. "현재 기초생활수급자이신가요?"
   → 예: income_level = 기초생활수급자

2. "차상위계층 확인서를 받으신 적 있나요?"
   → 예: income_level = 차상위계층

3. 둘 다 아닌 경우:
   "한 달 가구 전체 소득이 어느 정도인가요?" (범위 선택)
   + household_size 조합
   → LLM이 저소득 / 일반 판단
```

### income_level enum

| 값 | 기준 |
|----|------|
| `기초생활수급자` | 공식 수급자 또는 중위소득 ~50% |
| `차상위계층` | 공식 확인서 또는 중위소득 ~60% |
| `저소득` | 중위소득 ~100% |
| `일반` | 중위소득 100% 초과 |

> **중위소득 참고 (2025년 기준, 100%)**: 1인 239만원 / 2인 393만원 / 3인 502만원 / 4인 609만원
> 가구원 수마다 기준 금액이 다르므로 `household_size` 없이는 구간 판단 불가

---

## 2단계 수집 필드

서비스 선택 후 자격 요건 정밀 확인 단계. `rag_detail`이 반환한 자격 조건을 기준으로 LLM이 필요한 필드를 결정한다.

| 필드 | 타입 | 비고 |
|------|------|------|
| `disability_type` | `str \| None` | 장애 유형 (지체/시각/청각 등) |
| `disability_grade` | `str \| None` | 장애 등급 |
| `children_ages` | `list[int] \| None` | 자녀 나이 목록 |
| `housing_type` | `str \| None` | 자가/전세/월세/공공임대 |
| `household_type` | `str \| None` | 1인/부부/부모+자녀/한부모 — 2단계에서 명시적으로 확인 |
| `is_veteran` | `bool \| None` | 국가유공자 여부 |
| `is_single_parent` | `bool \| None` | `marital_status` + `has_children`으로 파생 가능하나 명시 저장 |
| `extra_fields` | `dict[str, str \| int \| bool]` | 서비스별 특수 필드 catch-all |

---

## 추후 고려사항

현재 설계에서 빠져있지만 서비스 고도화 시 검토할 항목들

| 항목 | 이유 | 제안 처리 방식 |
|------|------|--------------|
| **자산 정보** | 소득 기준을 통과해도 부동산·금융자산 초과 시 탈락하는 서비스 多 | 민감 정보이므로 2단계 `extra_fields`로 처리 |
| **국적/체류자격** | 외국인 거주자는 일부 서비스 대상 제외 | 서비스 주 타겟이 내국인이면 우선순위 낮음 |
| **고용보험 가입 여부** | 실업급여 자격 조건 (단순 실업 상태와 다름) | `employment_status`와 연계, 2단계에서 수집 |

---

## UserProfile development_plan.md 대비 변경사항

| 항목 | 기존 | 변경 |
|------|------|------|
| `household_size` | 2단계 필드 | **1단계로 이동** (소득 판단 선행 조건) |
| `income_level` enum | 3구간 (기초/차상위/일반) | **4구간** (기초/차상위/저소득/일반) 추가 |
| `marital_status` | 없음 | **1단계 추가** |
| `has_children` | 2단계 필드 | **1단계로 이동** |
| `disability_severity` | 없음 | **1단계 조건부 추가** (경증/중증) |
| `household_type` | 1단계 필드 | **2단계로 이동** (추론 오류 방지) |

---

## WelfareCandidate

RAG 검색 결과로 반환되는 복지 서비스 후보 하나를 담는 모델.

### 1차 RAG 검색 후 채워지는 필드 (`rag_search`)

| 필드 | 타입 | 출처 |
|------|------|------|
| `service_id` | `str` | RAG `/search` 응답 |
| `service_name` | `str` | RAG `/search` 응답 |
| `department` | `str` | RAG `/search` 응답 (담당 기관) |
| `summary` | `str` | RAG `/search` 응답 |
| `eligibility_reason` | `str` | RAG `/search` 응답 (해당 이유) |
| `score` | `float` | RAG `/search` 응답 (유사도 점수) |
| `priority` | `int` | score 기반으로 `rag_search` 노드가 직접 계산 |

### 2차 RAG 조회 후 채워지는 필드 (`rag_detail`)

| 필드 | 타입 | 출처 |
|------|------|------|
| `required_documents` | `list[str]` | RAG `/services/detail` 응답 |
| `application_fields` | `list[str]` | RAG `/services/detail` 응답 |
| `application_url` | `str \| None` | RAG `/services/detail` 응답 |
| `detail_fetched` | `bool` | 상세 조회 완료 여부 (기본값 False) |

> **주의:** `department`, `eligibility_reason`은 RAG `/search` 응답에 반드시 포함되어야 한다. `application_fields`는 RAG `/services/detail` 응답에 반드시 포함되어야 한다. RAG 팀과 API 계약 확정 필요.

### WelfareCandidate 변경사항

`development_plan.md` 설계와 동일. RAG API 계약이 확정되기 전까지 변경 없음.

---

## AgentState

8개 노드가 공유하는 전체 상태. 모든 노드가 여기서 읽고 여기에 쓴다.

| 필드 | 타입 | 역할 |
|------|------|------|
| `messages` | `list[BaseMessage]` | 전체 대화 내역 (add_messages Reducer) |
| `user_profile` | `UserProfile` | 수집된 사용자 정보 |
| `initial_missing_fields` | `list[str]` | 1단계에서 아직 못 받은 필드 목록 |
| `welfare_candidates` | `list[WelfareCandidate]` | RAG 검색 결과 후보 목록 |
| `selected_service` | `WelfareCandidate \| None` | 사용자가 선택한 서비스 |
| `detail_missing_fields` | `list[str]` | 2단계에서 아직 못 받은 필드 목록 |
| `document_guidance` | `str` | 서류 안내 텍스트 |
| `application_guide` | `str` | 신청서 항목별 작성 가이드 |
| `final_report` | `str` | 최종 보고서 |

### AgentState 변경사항

`initial_missing_fields`에 오늘 추가된 UserProfile 1단계 필드가 반영되어야 한다.

```
기존: age, income_level, disability, employment_status, region
변경: age, income_level, disability, disability_severity,
      employment_status, region, household_size, marital_status, has_children
```
