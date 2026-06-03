"""최종 보고서 에이전트 — 서비스 정보를 마크다운 보고서로 구성."""

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
    """서비스 상세 정보를 마크다운 보고서로 구성."""
    selected: WelfareCandidate = state["selected_service"]

    if not selected:
        fallback = "선택된 서비스가 없습니다. 이전 단계를 다시 진행해 주세요."
        return {
            "final_report": fallback,
            "messages": [AIMessage(content=fallback)],
        }

    required_documents_text = (
        "\n".join(f"- {d}" for d in selected.required_documents)
        if selected.required_documents
        else "서류 목록 정보 없음"
    )

    prompt = _load_prompt().format(
        serv_nm=selected.serv_nm,
        serv_dgst=selected.serv_dgst or "정보 없음",
        tgtr_dtl_cn=selected.tgtr_dtl_cn or "정보 없음",
        slct_crit_cn=selected.slct_crit_cn or "정보 없음",
        alw_serv_cn=selected.alw_serv_cn or "정보 없음",
        sprt_cyc_nm=selected.sprt_cyc_nm or "",
        srv_pvsn_nm=selected.srv_pvsn_nm or "",
        required_documents=required_documents_text,
        application_method=selected.application_method or "신청방법 정보 없음",
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
