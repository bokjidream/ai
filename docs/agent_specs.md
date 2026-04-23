# 에이전트 노드 상세 명세

> [← 인덱스로 돌아가기](development_plan.md)

---

## `initial_interview_node` (1단계 인터뷰 에이전트)

**입력:** `AgentState` (초기 또는 재진입 상태)

**출력:** 업데이트된 `user_profile`(최소 필드), `initial_missing_fields`, `messages`

**핵심 동작:**
1. `initial_missing_fields`를 확인하여 아직 수집 안 된 최소 필드를 파악
2. LLM에 시스템 프롬프트 + 대화 히스토리를 전달하여 다음 질문 생성
3. 사용자 응답에서 structured output으로 최소 필드값 추출
4. 모든 최소 필드가 채워지면 `initial_missing_fields = []`로 설정

---

## `rag_search_node` (RAG 검색 노드 — 후보 목록)

**입력:** `AgentState` (완성된 최소 `user_profile`)

**출력:** 업데이트된 `welfare_candidates`

**핵심 동작:**
1. `user_profile` 최소 필드를 JSON으로 직렬화하여 RAG 서비스 `POST /welfare/search`에 전송
2. 자연어 변환은 RAG 서비스 내부에서 처리 — AI 파트는 JSON 전송만 담당
3. 응답을 `WelfareCandidate` 목록으로 변환 (상세 정보 미포함 상태)
4. **결과가 빈 목록인 경우 LLM 폴백 없이 사용자에게 "해당하는 서비스를 찾지 못했습니다" 안내 후 END로 라우팅**

---

## `service_select_node` (서비스 선택 노드)

**입력:** `AgentState` (완성된 `welfare_candidates`)

**출력:** 업데이트된 `selected_service`, `messages`

**핵심 동작:**
1. `welfare_candidates` 목록을 번호와 함께 사용자에게 표시한 후 `interrupt(value={"candidates": ...})`로 그래프 실행 중단 — checkpointer가 상태 저장 → `Command(resume=user_input)`으로 재개
2. 유효한 입력이면 `selected_service` 설정, 유효하지 않으면 오류 메시지를 포함하여 `interrupt()` 재호출 (노드 내부 루프 없음)
3. Checkpointer 필수: `interrupt()` 기반 HitL은 checkpointer 없이 동작하지 않음

---

## `rag_detail_node` (RAG 상세 조회 노드)

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

## `detail_interview_node` (2단계 인터뷰 에이전트)

**입력:** `AgentState` (선택된 서비스 상세 정보 + 현재 `user_profile`)

**출력:** 업데이트된 `user_profile`(서비스 특화 필드), `detail_missing_fields`, `messages`

**핵심 동작:**
1. `detail_missing_fields`가 비어 있으면 LLM 호출 없이 즉시 반환 (pass-through) — `rag_detail`에서 이미 모든 필드가 충족된 경우
2. `detail_missing_fields`를 순회하며 아직 수집 안 된 항목에 대한 질문 생성
3. 정규 필드(`"household_size"` 등) → `user_profile`의 해당 필드에 저장
4. extra 필드(`"extra:deposit_amount"` 등) → `user_profile.extra_fields[키]`에 저장
5. 모든 항목 수집 완료 시 `detail_missing_fields = []`로 설정

---

## `document_guidance_node` (서류 안내 에이전트)

**입력:** `AgentState` (완성된 `selected_service` + `user_profile`)

**출력:** 업데이트된 `document_guidance`

**핵심 동작:**
1. `selected_service.required_documents`를 기반으로 서류 목록 정리
2. 사용자 상황에 맞게 필요 서류 필터링 및 발급 방법 안내
3. 안내 텍스트를 사용자 친화적 형식으로 생성

---

## `draft_writer_node` (신청서 작성 가이드 에이전트)

**입력:** `AgentState` (완성된 `user_profile` + `selected_service` 상세 정보)

**출력:** 업데이트된 `application_guide`

**핵심 동작:**
1. `selected_service.application_fields`(RAG에서 가져온 신청서 항목 목록)를 순서대로 처리
2. 각 항목에 대해 `user_profile` 정규 필드 → `user_profile.extra_fields` 순서로 값을 탐색하여 "어떻게 써야 하는지" 설명 생성
3. 사용자 정보로 판단 불가한 항목은 `[직접 확인 필요: 이유]` 형식으로 표시
4. HWP 등 실제 서식 파일은 생성하지 않음

---

## `report_writer_node` (보고서 에이전트)

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
