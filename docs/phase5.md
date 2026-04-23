# Phase 5: 최종 통합 및 품질 개선

> [← 인덱스로 돌아가기](development_plan.md)

**목표:** 전체 시스템 안정화, 에러 처리 강화, 실사용 품질 확보.

**브랜치:** `feat/final-integration`

## 작업 목록

| # | 작업 |
|---|------|
| 5-0 | **`graph/builder.py` SQLite checkpointer 수정** (B 담당): `langgraph-checkpoint-sqlite` 패키지 설치 + `AsyncSqliteSaver.from_conn_string()`을 `async with` 컨텍스트로 올바르게 사용하도록 `_build_checkpointer()` 리팩터링 필요. 현재 sqlite 모드 실행 시 오류 발생 |
| 5-1 | 에러 처리 보강: LLM 응답 파싱 실패 최대 재시도 횟수 조정, 회복 불가 시 사용자 친화적 메시지 출력 |
| 5-2 | 대화 히스토리 관리: 컨텍스트 길이 초과 방지 (요약 또는 슬라이딩 윈도우) |
| 5-3 | `main.py` CLI 인터페이스 구현 (대화형 루프, 서비스 선택 UX 포함, `interrupt()` 재개 패턴 포함) |
| 5-4 | **FastAPI 서버 모드 구현** (`server.py`): Next.js 프론트엔드 연동을 위한 REST API 래퍼, `POST /chat` 엔드포인트, `interrupt()` 발생 시 대기 응답 반환, `POST /resume`으로 선택값 수신 후 재개. **`thread_id` 세션 관리 방식(쿠키, 응답 바디 등)은 Phase 5에서 프론트엔드 팀과 협의하여 확정** |
| 5-5 | 통합 E2E 테스트 시나리오 확장 (다양한 사용자 유형) |
| 5-6 | `README.md` 업데이트 (CLI 사용 방법, API 사용 방법, 아키텍처 다이어그램) |
| 5-7 | `develop` → `main` 머지 및 v1.0.0 태그 |
