# 테스트 전략

> [← 인덱스로 돌아가기](development_plan.md)

---

## 테스트 레벨

| 레벨 | 파일 | 목적 |
|------|------|------|
| 단위 | `tests/test_state.py` | Pydantic 모델 검증 |
| 단위 | `tests/test_rag_client_stub.py` | RAG 클라이언트 httpx mock 기반 계약 검증 |
| 단위 | `tests/test_initial_interview.py` | 1단계 인터뷰 노드 로직 |
| 단위 | `tests/test_rag_search.py` | RAG 후보 검색 노드 로직 (RAG 모킹) |
| 단위 | `tests/test_service_select.py` | 서비스 선택 노드 로직 |
| 단위 | `tests/test_rag_detail.py` | RAG 상세 조회 노드 로직 (RAG 모킹) |
| 단위 | `tests/test_detail_interview.py` | 2단계 인터뷰 노드 로직 |
| 단위 | `tests/test_document_guidance.py` | 서류 안내 노드 로직 |
| 단위 | `tests/test_draft_writer.py` | 신청서 작성 가이드 노드 로직 |
| 단위 | `tests/test_report_writer.py` | 보고서 노드 로직 |
| 통합 | `tests/test_graph.py` | 그래프 컴파일 및 노드 연결 |
| 통합 | `tests/test_initial_interview_integration.py` | 1단계 인터뷰 전체 흐름 |
| 통합 | `tests/test_rag_integration.py` | 실제 RAG 서비스 연동 (`-m integration` 마크 필요) |
| E2E | `tests/test_e2e.py` | 전체 파이프라인 시나리오 테스트 (미구현 — Phase 5 예정) |
| 단위 | `tests/test_prompts.py` | 프롬프트 파일 로딩 및 키워드 검증 (미구현 — Phase 5 예정) |

---

## LLM 모킹 전략

실제 API 호출 없이 테스트하기 위해 `conftest.py`에서 LLM과 RAG 클라이언트를 모킹합니다.

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    # 모든 에이전트 노드는 await llm.ainvoke() 사용 — AsyncMock 필수
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="모킹된 응답"))
    return llm

@pytest.fixture
def mock_rag_client():
    client = AsyncMock()
    # search()는 rag_client 내부에서 {"results": [...]} 언래핑 후 list 반환
    client.search.return_value = [
        {"serv_id": "WLF00000035", "serv_nm": "기초연금", "serv_dgst": "만 65세 이상 저소득 노인 연금", "score": 0.95},
    ]
    # 2차 상세 조회 응답 모킹
    client.get_detail.return_value = {
        "serv_id": "WLF00000035",
        "required_documents": [],   # 현재 빈 배열로 합의
        "application_fields": [],   # 현재 빈 배열로 합의
        "application_url": "https://www.bokjiro.go.kr",
    }
    return client
```

> **모킹 스키마 준수:** 필드명은 RAG API 응답 기준(`serv_id`, `serv_nm`, `serv_dgst`)을 따릅니다. `search()` mock은 list를 직접 반환합니다 — `rag_client.py`가 `{"results": [...]}` 언래핑을 내부적으로 처리하기 때문입니다. `required_documents`, `application_fields`는 현재 RAG API 미구현으로 빈 배열로 수신합니다.

---

## 테스트 시나리오 (E2E)

| 시나리오 | 사용자 유형 | 예상 후보 서비스 | 선택 서비스 |
|----------|------------|-----------------|------------|
| 시나리오 A | 65세 이상 독거노인, 기초생활수급자 | 기초연금, 노인 돌봄, 의료급여 등 | 기초연금 선택 |
| 시나리오 B | 30대 실업자, 장애 2급 | 장애인 고용 지원, 실업급여, 장애인 활동 지원 등 | 장애인 활동 지원 선택 |
| 시나리오 C | 4인 가족, 차상위계층, 미취학 자녀 | 아동 수당, 보육 지원, 한부모 지원 등 | 아동 수당 선택 |
