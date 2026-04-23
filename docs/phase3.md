# Phase 3: RAG 통합 (ChromaDB)

> [← 인덱스로 돌아가기](development_plan.md)

**목표:** `rag/` 서비스와 실제 연동하여 복지 서비스 데이터 기반의 2단계 RAG 검색을 구현합니다.

**브랜치:** `feat/rag-integration`

## 작업 목록

| # | 작업 | 파일 |
|---|------|------|
| 3-1 | `tools/rag_client.py` 스텁을 실제 `httpx.AsyncClient` HTTP 구현으로 교체 | `tools/rag_client.py` |
| 3-2 | 1차 RAG 쿼리: 최소 프로필 → 서비스 후보 N개 실제 연동 검증 | `agents/rag_search.py` |
| 3-3 | 2차 RAG 쿼리: 서비스 ID → 상세 정보 조회 실제 연동 검증 | `agents/rag_detail.py` |
| 3-4 | 환경 변수에 `RAG_SERVICE_URL` 설정 추가 | `.env.example` 수정 |
| 3-5 | RAG 통합 테스트 | `tests/test_rag_integration.py` |

## RAG API 계약

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

## 완료 기준

- 실제 RAG 서비스를 통해 후보 목록과 상세 정보 조회 가능
- RAG 결과 없음(빈 목록) 시 에이전트가 LLM 생성 없이 사용자에게 안내 후 종료
- 검색 관련성(relevance) 기준 테스트 통과
