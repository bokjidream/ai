import os
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from agents.detail_interview import detail_interview_node
from agents.document_guidance import document_guidance_node
from agents.draft_writer import draft_writer_node
from agents.form_filler import form_filler_node
from agents.initial_interview import initial_interview_node
from agents.rag_detail import rag_detail_node
from agents.rag_search import rag_search_node
from agents.report_writer import report_writer_node
from agents.service_select import service_select_node
from graph.state import AgentState

load_dotenv()

# SQLite/Postgres 모드일 때 커넥션 수명을 앱과 동일하게 유지하기 위한 스택
_checkpointer_stack: AsyncExitStack | None = None


def _make_serde() -> JsonPlusSerializer:
    """체크포인터 직렬화기 — graph.state 커스텀 타입을 msgpack 허용 목록에 등록."""
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("graph.state", "UserProfile"),
            ("graph.state", "WelfareCandidate"),
            ("graph.state", "IncomeLevel"),
            ("graph.state", "EmploymentStatus"),
            ("graph.state", "MaritalStatus"),
            ("graph.state", "DisabilitySeverity"),
        ]
    )


# ── 조건부 엣지 함수 ──


def route_after_initial_interview(state: AgentState) -> str:
    """1단계 인터뷰 후 라우팅: 누락 필드 있으면 재진입, 없으면 rag_search."""
    if state["initial_missing_fields"]:
        return "initial_interview"
    return "rag_search"


def route_after_rag_search(state: AgentState) -> str:
    """RAG 검색 후 라우팅: 후보 없으면 END, 있으면 service_select."""
    if not state["welfare_candidates"]:
        return END
    return "service_select"


def route_after_detail_interview(state: AgentState) -> str:
    """2단계 인터뷰 후 라우팅: 누락 필드 있으면 재진입, 없으면 document_guidance."""
    if state["detail_missing_fields"]:
        return "detail_interview"
    return "document_guidance"


# ── 그래프 빌더 ──


async def build_graph():
    """StateGraph를 조립하여 컴파일된 그래프를 반환합니다.

    SQLite 모드: AsyncSqliteSaver를 AsyncExitStack으로 열어 앱 수명 동안 유지.
    Memory 모드: MemorySaver를 사용 (동기, 기본값).
    """
    global _checkpointer_stack

    builder = StateGraph(AgentState)

    # 노드 등록
    builder.add_node("initial_interview", initial_interview_node)
    builder.add_node("rag_search", rag_search_node)
    builder.add_node("service_select", service_select_node)
    builder.add_node("rag_detail", rag_detail_node)
    builder.add_node("detail_interview", detail_interview_node)
    builder.add_node("document_guidance", document_guidance_node)
    builder.add_node("draft_writer", draft_writer_node)
    builder.add_node("form_filler", form_filler_node)
    builder.add_node("report_writer", report_writer_node)

    # 엣지 연결
    builder.add_edge(START, "initial_interview")
    builder.add_conditional_edges("initial_interview", route_after_initial_interview)
    builder.add_conditional_edges("rag_search", route_after_rag_search)
    builder.add_edge("service_select", "rag_detail")
    builder.add_edge("rag_detail", "detail_interview")
    builder.add_conditional_edges("detail_interview", route_after_detail_interview)
    builder.add_edge("document_guidance", "draft_writer")
    builder.add_edge("draft_writer", "form_filler")
    builder.add_edge("form_filler", "report_writer")
    builder.add_edge("report_writer", END)

    mode = os.getenv("GRAPH_CHECKPOINTER", "memory")

    if mode == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        db_path = os.getenv("SQLITE_DB_PATH", "./checkpoints.db")
        _checkpointer_stack = AsyncExitStack()
        checkpointer = await _checkpointer_stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(db_path)
        )
        checkpointer.serde = _make_serde()
        return builder.compile(checkpointer=checkpointer)

    if mode == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        conn_string = os.getenv("POSTGRES_CONN_STRING")
        if not conn_string:
            raise ValueError(
                "GRAPH_CHECKPOINTER=postgres 사용 시 "
                "POSTGRES_CONN_STRING 환경변수가 필요합니다."
            )
        _checkpointer_stack = AsyncExitStack()
        checkpointer = await _checkpointer_stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(conn_string)
        )
        checkpointer.serde = _make_serde()
        # 첫 실행 시 체크포인터 테이블 생성 (멱등 — 이미 있으면 무시)
        await checkpointer.setup()
        return builder.compile(checkpointer=checkpointer)

    return builder.compile(checkpointer=MemorySaver(serde=_make_serde()))
