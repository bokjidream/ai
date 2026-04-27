import os

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from agents.rag_detail import rag_detail_node
from agents.rag_search import rag_search_node
from agents.service_select import service_select_node
from graph.state import AgentState

load_dotenv()


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


# ── stub 노드 (Phase 2에서 실제 구현으로 교체) ──


async def initial_interview_node(state: AgentState) -> dict:
    """1단계 인터뷰 stub."""
    return {}


async def detail_interview_node(state: AgentState) -> dict:
    """2단계 인터뷰 stub."""
    return {}


async def document_guidance_node(state: AgentState) -> dict:
    """서류 안내 stub."""
    return {}


async def draft_writer_node(state: AgentState) -> dict:
    """신청서 작성 가이드 stub."""
    return {}


async def report_writer_node(state: AgentState) -> dict:
    """최종 보고서 stub."""
    return {}


# ── Checkpointer 팩토리 ──


def _build_checkpointer():
    """환경변수 GRAPH_CHECKPOINTER에 따라 checkpointer를 반환합니다."""
    mode = os.getenv("GRAPH_CHECKPOINTER", "memory")

    if mode == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        db_path = os.getenv("SQLITE_DB_PATH", "./checkpoints.db")
        return AsyncSqliteSaver.from_conn_string(db_path)

    if mode == "postgres":
        raise NotImplementedError("Postgres checkpointer is not configured yet.")

    return MemorySaver()


# ── 그래프 빌더 ──


def build_graph():
    """StateGraph를 조립하여 컴파일된 그래프를 반환합니다."""
    builder = StateGraph(AgentState)

    # 노드 등록
    builder.add_node("initial_interview", initial_interview_node)
    builder.add_node("rag_search", rag_search_node)
    builder.add_node("service_select", service_select_node)
    builder.add_node("rag_detail", rag_detail_node)
    builder.add_node("detail_interview", detail_interview_node)
    builder.add_node("document_guidance", document_guidance_node)
    builder.add_node("draft_writer", draft_writer_node)
    builder.add_node("report_writer", report_writer_node)

    # 엣지 연결
    builder.add_edge(START, "initial_interview")
    builder.add_conditional_edges("initial_interview", route_after_initial_interview)
    builder.add_conditional_edges("rag_search", route_after_rag_search)
    builder.add_edge("service_select", "rag_detail")
    builder.add_edge("rag_detail", "detail_interview")
    builder.add_conditional_edges("detail_interview", route_after_detail_interview)
    builder.add_edge("document_guidance", "draft_writer")
    builder.add_edge("draft_writer", "report_writer")
    builder.add_edge("report_writer", END)

    checkpointer = _build_checkpointer()
    return builder.compile(checkpointer=checkpointer)


graph = build_graph()
