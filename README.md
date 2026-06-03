# 복지드림 AI 에이전트

사용자가 기본 정보를 입력하면 AI가 지원 가능한 복지 서비스를 검색·추천하고, 선택된 서비스의 신청서 작성 가이드와 최종 보고서를 생성하는 LangGraph 기반 챗봇 서버입니다.

## 아키텍처

```
START
  └─▶ initial_interview ◀─┐  (1단계: 나이·소득·장애 여부 등 최소 정보 수집)
            │ 완료          └─ 정보 부족 시 재진입
            ▼
       rag_search             (수집된 정보로 복지 서비스 후보 검색)
            │ 후보 없음 ──▶ END
            ▼
      service_select          (사용자가 후보 목록 중 서비스 선택 — HitL)
            │
            ▼
       rag_detail             (선택된 서비스 상세 정보 조회)
            │
            ▼
     detail_interview ◀─┐   (2단계: 선택 서비스 특화 추가 정보 수집)
            │ 완료        └─ 정보 부족 시 재진입
            ▼
   document_guidance          (필요 서류 안내)
            │
            ▼
      draft_writer            (신청서 항목별 작성 가이드 생성)
            │
            ▼
     report_writer            (최종 보고서 생성)
            │
           END
```

**1단계 인터뷰** — hwnv.cloud API (asker/interviewer 모델) 사용  
**2단계 이후** — Groq LLM (llama-3.3-70b-versatile) 사용

## 환경 설정

```bash
cp .env.example .env
```

`.env` 파일에서 아래 값을 설정합니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GROQ_API_KEY` | — | Groq API 키 (필수) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | 사용할 Groq 모델 |
| `GRAPH_CHECKPOINTER` | `memory` | `memory` (개발) / `sqlite` (운영) |
| `SQLITE_DB_PATH` | `./checkpoints.db` | SQLite 저장 경로 (sqlite 모드일 때) |
| `RAG_SERVICE_URL` | `http://localhost:8001` | RAG 서버 주소 |
| `RAG_SEARCH_TOP_K` | `5` | RAG 검색 후보 최대 수 |
| `LLM_MAX_RETRY` | `2` | LLM 파싱 실패 시 최대 재시도 횟수 |
| `HISTORY_WINDOW_SIZE` | `10` | LLM에 넘길 최근 대화 메시지 최대 개수 |

## 실행

```bash
# 의존성 설치
uv sync --all-groups

# 서버 실행 (기본 포트 8000)
uv run uvicorn server:app --reload --port 8000
```

> RAG 서버가 별도로 실행 중이어야 합니다. `RAG_SERVICE_URL`을 RAG 서버 주소로 설정하세요.

## API

### `POST /chat/start`

새 대화 세션을 시작합니다. 서버가 첫 번째 인터뷰 질문을 반환합니다.

**요청:** 바디 없음

**응답 예시:**
```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "interview",
  "data": {
    "question": "나이가 어떻게 되세요?",
    "missing_fields": ["age", "region", "household_size", "..."]
  }
}
```

---

### `POST /chat/message`

사용자 메시지를 전송하고 다음 응답을 받습니다.

**요청 바디:**
```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "35살이에요"
}
```

**응답 `type` 종류:**

| type | 설명 | data 주요 필드 |
|------|------|----------------|
| `interview` | 인터뷰 진행 중, 다음 질문 | `question`, `missing_fields` |
| `service_select` | 복지 서비스 선택 요청 | `candidates` (목록 텍스트), `welfare_candidates` (전체 데이터) |
| `done` | 모든 단계 완료 | `final_report`, `document_guidance`, `application_guide`, `selected_service` |
| `no_results` | 해당하는 복지 서비스 없음 | — |

**`service_select` 응답 시** — `message`에 후보 번호(예: `"1"`)를 전송하면 됩니다.

---

### 전체 흐름 예시

```
POST /chat/start
  → type: "interview", question: "나이가 어떻게 되세요?"

POST /chat/message  { message: "35살이에요" }
  → type: "interview", question: "어느 지역에 사세요?"

... (인터뷰 반복) ...

POST /chat/message  { message: "기초생활수급자예요" }
  → type: "service_select", candidates: "1. 기초연금\n2. 장애인활동지원\n..."

POST /chat/message  { message: "1" }
  → type: "interview", question: "장애 유형이 어떻게 되세요?"

... (2단계 인터뷰 반복) ...

POST /chat/message  { message: "지체장애입니다" }
  → type: "done", final_report: "..."
```

## 테스트

```bash
# 단위 테스트 전체 실행
uv run pytest tests/ -v

# 통합 테스트 (RAG 서버 실행 필요)
uv run pytest tests/test_rag_integration.py -v

# hwnv.cloud 연동 테스트 (API 접근 필요)
uv run pytest tests/test_initial_interview_integration.py -v
```
