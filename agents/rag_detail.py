"""RAG 상세 조회 노드 — 선택된 서비스의 required_documents 등 상세 필드 보완."""

from langchain_core.messages import AIMessage

import tools.rag_client as rag_client
from graph.state import AgentState, WelfareCandidate


async def rag_detail_node(state: AgentState) -> dict:
    """선택된 서비스의 상세 정보를 조회하여 WelfareCandidate를 갱신."""
    selected: WelfareCandidate = state["selected_service"]

    detail = None
    for _ in range(2):
        try:
            detail = await rag_client.get_detail(selected.serv_id)
            break
        except Exception:
            continue

    if detail is None:
        error_msg = (
            "서비스 상세 정보를 불러오지 못했습니다. 기본 정보로 계속 진행합니다."
        )
        return {
            "selected_service": selected,
            "messages": [AIMessage(content=error_msg)],
        }

    updated = selected.model_copy(
        update={
            "required_documents": detail.get("required_documents", []),
            "application_fields": detail.get("application_fields", []),
            "application_url": detail.get("application_url"),
            "detail_fetched": True,
        }
    )

    return {"selected_service": updated}
