# Phase 4: 로컬 LLM 전환 (Ollama)

> [← 인덱스로 돌아가기](development_plan.md)

**목표:** Google Gemini API 의존성을 제거하고 로컬 Ollama로 전환합니다.

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

- `GOOGLE_API_KEY` 없이 로컬에서 전체 파이프라인 동작
- 기존 테스트 코드 수정 없이 CI 통과
