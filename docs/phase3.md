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

> **확정 스펙 (2026-04-29 RAG 팀 대면 확인):** 초기 계획과 다르게 실제 구현된 스펙입니다.

```
# 1차: 후보 목록 검색
POST /welfare/search
Body: {                              # profile 래퍼 없이 flat JSON, top_k도 같은 레벨에 포함
  "age": 65,
  "income_level": "기초생활수급자",
  "disability": false,
  "employment_status": "비경제활동",
  "region": "서울",
  "top_k": 5
}
Response: {
  "results": [                       # 배열 직접 반환이 아닌 results 키로 감쌈
    {
      "serv_id": "WLF-001",          # id → serv_id
      "serv_nm": "기초연금",          # name → serv_nm
      "serv_dgst": "만 65세 이상 저소득 노인 연금",  # summary → serv_dgst
      "department": "보건복지부",
      "score": 0.92                  # 항상 float
    },
    ...
  ]
}
# 결과 없으면: HTTP 200 + {"results": []}  (LLM 폴백 없음)
# eligibility_reason은 RAG 응답에 없음 — AI가 serv_dgst 기반으로 LLM 생성

# 2차: 상세 정보 조회
GET /welfare/{serv_id}
Response: {
  "serv_id": "WLF-001",
  "serv_nm": "기초연금",
  "required_documents": ["신분증", "통장사본", ...],  # 현재 [] 반환 (RAG 미구현)
  "application_fields": ["신청인 성명", "생년월일", ...],  # 현재 [] 반환 (RAG 미구현)
  "application_url": "https://www.bokjiro.go.kr"
}
```

> **필드 책임 분리:** `eligibility_reason`과 `department`는 RAG 응답이 아닌 AI 레이어에서 처리합니다. `eligibility_reason`은 LLM이 `serv_dgst` 기반으로 생성, `department`는 RAG 응답에 포함됩니다.

## 완료 기준

- 실제 RAG 서비스를 통해 후보 목록과 상세 정보 조회 가능
- RAG 결과 없음(빈 목록) 시 에이전트가 LLM 생성 없이 사용자에게 안내 후 종료
- 검색 관련성(relevance) 기준 테스트 통과
