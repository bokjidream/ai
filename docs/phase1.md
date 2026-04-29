# Phase 1: 핵심 상태 및 그래프 기반 구축

> [← 인덱스로 돌아가기](development_plan.md)

**목표:** 에이전트가 실제로 동작할 수 있는 뼈대(state, graph builder)를 구현합니다.

## 작업 목록

| # | 작업 | 파일 | 브랜치 |
|---|------|------|--------|
| 1-1 | `AgentState`, `UserProfile`, `WelfareCandidate` Pydantic 모델 정의 | `graph/state.py` | `feat/state-models` |
| 1-2 | LangGraph 그래프 빌더 구현 (노드 등록 + 엣지 연결) | `graph/builder.py` | `feat/graph-builder` |
| 1-3 | 조건부 엣지 함수 구현 (1단계 재인터뷰 / 서비스 선택 후 2단계 재인터뷰) | `graph/builder.py` | `feat/graph-builder` |
| 1-4 | **Checkpointer 설정**: `MemorySaver`(개발용) 또는 `SqliteSaver`(운영용) 그래프에 연결, `interrupt()` 기반 HitL 패턴 확인 | `graph/builder.py` | `feat/graph-builder` |
| 1-5 | `main.py`에서 그래프 실행 진입점 구현 | `main.py` | `feat/graph-builder` |
| 1-6 | Phase 1 단위 테스트 작성 | `tests/test_state.py`, `tests/test_graph.py` | `feat/graph-builder` |

> **`graph/builder.py` 역할:** 이 파일이 LangGraph 그래프 전체를 조립합니다. ①노드 등록(8개 에이전트 함수를 그래프에 추가), ②엣지 연결(노드 간 실행 순서 정의), ③조건부 엣지(재인터뷰 루프 등 분기 처리), ④Checkpointer 연결의 네 가지 역할을 담당합니다.

> **Checkpointer란?** LangGraph가 그래프 실행 중간에 `AgentState`를 저장하는 저장소입니다. `service_select` 노드에서 `interrupt()`로 그래프가 일시 중단되고 사용자 입력을 기다리는데, 이 "멈춤 → 재개" 사이에 서버가 재시작되더라도 저장된 상태에서 이어서 실행할 수 있게 해줍니다. Checkpointer 없이는 `interrupt()` 기반 HitL 패턴이 동작하지 않습니다.

> **Checkpointer 선택 기준:** CLI(개발·테스트)에서는 `MemorySaver`(RAM 저장, 프로세스 종료 시 소멸), 운영(FastAPI 서버 모드)에서는 `SqliteSaver` 또는 `PostgresSaver` 사용. `graph/builder.py`에서 환경 변수(`GRAPH_CHECKPOINTER=memory|sqlite|postgres`)로 분기.
>
> - `memory`: RAM에만 저장. 서버 재시작 시 모든 대화 상태 소멸. 개발/테스트에 적합.
> - `sqlite`: 파일 하나(`checkpoints.db`)에 영구 저장. 별도 DB 서버 불필요 — LangGraph가 테이블 생성·읽기·쓰기를 자동 처리. Phase 5 운영 환경에 적합.
> - `postgres`: 별도 DB 서버 필요. 트래픽이 많아졌을 때 고려.

## 완료 기준

- `AgentState` 모델 정의 완료 및 Pydantic 검증 통과
- 그래프가 START → END까지 오류 없이 컴파일됨
- Checkpointer를 붙인 상태에서 `interrupt()` 호출 후 재개 동작 확인
- Phase 1 범위 테스트 통과: `uv run pytest tests/test_state.py tests/test_graph.py -v`
  (Phase 2 이후 테스트는 해당 Phase 완료 기준에서 별도로 검증)

> **RAG API 계약 (`docs/rag_api_contract.md`) 작성은 Phase 2 시작 전까지 완료하면 됩니다.** Phase 2 2-0의 RAG 클라이언트 스텁 인터페이스가 이 계약서를 기준으로 구현되어야 하므로, `feat/rag-client-stub` 브랜치 시작 전 `rag/` 파트와 협의하여 확정합니다.
