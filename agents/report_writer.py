"""최종 보고서 에이전트 — draft_writer 가이드를 사용자 친화적 마크다운으로 재구성."""

import logging
from pathlib import Path

from langchain_core.messages import AIMessage

from graph.state import AgentState, WelfareCandidate
from tools.llm import get_llm

logger = logging.getLogger("bokjidream.report_writer")

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "report_writer.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


async def report_writer_node(state: AgentState) -> dict:
    """application_guide와 document_guidance를 마크다운 보고서로 재구성."""
    selected: WelfareCandidate = state["selected_service"]
    application_guide: str = state["application_guide"]
    document_guidance: str = state["document_guidance"]

    if not application_guide:
        serv_nm = selected.serv_nm if selected else "선택된 서비스"
        fallback = (
            f"'{serv_nm}' 신청 가이드가 없습니다. 이전 단계를 다시 진행해 주세요."
        )
        return {
            "final_report": fallback,
            "messages": [AIMessage(content=fallback)],
        }

    prompt = _load_prompt().format(
        serv_nm=selected.serv_nm,
        document_guidance=document_guidance,
        application_guide=application_guide,
    )

    llm = get_llm()
    try:
        response = await llm.ainvoke(prompt)
        report = response.content
    except Exception as e:
        logger.warning("[report_writer] LLM 호출 실패: %s", e, exc_info=True)
        report = (
            f"'{selected.serv_nm}' 보고서 생성 중 오류가 발생했습니다. "
            "잠시 후 다시 시도해 주세요."
        )

    return {
        "final_report": report,
        "messages": [AIMessage(content=report)],
    }
