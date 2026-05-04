# Phase 4: 로컬 LLM 전환 (Ollama)

> [← 인덱스로 돌아가기](development_plan.md)

**목표:** Groq API 의존성을 제거하고 로컬 Ollama로 전환합니다.

**브랜치:** `feat/ollama-migration`

## 작업 목록

| # | 작업 | 파일 |
|---|------|------|
| 4-1 | `langchain-community` Ollama 통합 확인 | `tools/llm.py` |
| 4-2 | `tools/llm.py`에서 Ollama 코드 활성화, Gemini 코드 제거 | `tools/llm.py` |
| 4-3 | `.env.example`에 `OLLAMA_BASE_URL`, `OLLAMA_MODEL` 추가 | `.env.example` |
| 4-4 | CI 환경에서 Ollama 없이 테스트 가능하도록 LLM 모킹 구성 | `tests/conftest.py` |
| 4-5 | 전환 후 전체 파이프라인 동작 검증 | E2E 테스트 재실행 |

## 완료 기준

- `GROQ_API_KEY` 없이 로컬에서 전체 파이프라인 동작
- 기존 테스트 코드 수정 없이 CI 통과

---

## hwnv.cloud API 제약 사항 (전환 전 사전 확인 필요)

hwnv.cloud API는 **바로 이전 대화 1개만 수신**한다. 전체 대화 히스토리 배열을 전달해도 마지막 메시지만 처리됨.

### B 담당 수정 필요 파일

| 파일 | 현재 구현 | 필요 변경 |
|------|-----------|-----------|
| `agents/detail_interview.py` | `HISTORY_WINDOW_SIZE`로 최대 10개 messages 배열 전달 | 히스토리 전달 로직 제거, `_HISTORY_WINDOW` 변수 및 슬라이딩 윈도우 삭제 |

### B 담당 수정 불필요 파일

| 파일 | 이유 |
|------|------|
| `agents/draft_writer.py` | 단일 프롬프트 문자열만 전달 — 이미 호환 |

### A 담당 확인 필요 파일

`document_guidance.py`, `report_writer.py` 등 히스토리를 messages 배열로 전달하는 노드가 있으면 동일하게 수정 필요. A 담당이므로 A와 협의.
