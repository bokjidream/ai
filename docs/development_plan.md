# 복지 서비스 자가진단 AI 에이전트 개발 계획서

> 작성일: 2026-04-15  
> 최종 수정: 2026-04-23 (문서 세분화)  
> 브랜치 전략: `main` (배포) ← `develop` (통합) ← `feat/*` / `fix/*` / `chore/*`

---

## 문서 목록

| 문서 | 내용 |
|------|------|
| [overview.md](overview.md) | 프로젝트 개요 · 시스템 아키텍처 · 데이터 모델 |
| [phase1.md](phase1.md) | Phase 1: 핵심 상태 및 그래프 기반 구축 |
| [phase2.md](phase2.md) | Phase 2: 에이전트 노드 8개 구현 |
| [phase3.md](phase3.md) | Phase 3: RAG 통합 (ChromaDB) |
| [phase4.md](phase4.md) | Phase 4: 로컬 LLM 전환 (Ollama) |
| [phase5.md](phase5.md) | Phase 5: 최종 통합 및 품질 개선 |
| [agent_specs.md](agent_specs.md) | 에이전트 노드 상세 명세 |
| [testing.md](testing.md) | 테스트 전략 및 시나리오 |
| [reference.md](reference.md) | 디렉터리 구조 · 프롬프트 관리 · 환경 변수 · 협업 규칙 |

---

## 진행 상황

| Phase | 상태 | 완료 조건 |
|-------|------|-----------|
| Phase 1: 상태 + 그래프 기반 | 대기 | 그래프 컴파일 + checkpointer + interrupt() 동작 + 기본 테스트 통과 |
| Phase 2: 에이전트 노드 8개 | 대기 | E2E 파이프라인 동작 (RAG 모킹 사용), structured output 파싱 실패 처리 포함 |
| Phase 3: RAG 실제 연동 | 대기 | 실제 RAG 서비스 기반 후보 목록 + 상세 조회, HTTP 오류 처리 포함 |
| Phase 4: Ollama 전환 | 대기 | API 키 없이 로컬 동작 |
| Phase 5: 최종 통합 | 대기 | CLI + FastAPI 서버 모드 동작, v1.0.0 릴리즈 |
