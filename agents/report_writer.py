"""최종 보고서 에이전트 — 안내 텍스트를 마크다운 보고서로 재구성."""

import logging
from pathlib import Path

from langchain_core.messages import AIMessage

from graph.state import AgentState, WelfareCandidate
from tools.llm import get_llm

logger = logging.getLogger("bokjidream.report_writer")

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "report_writer.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_forms_section(filled_forms: list[dict]) -> str:
    """filled_forms status에 따라 신청서 파일 섹션 텍스트를 생성합니다."""
    if not filled_forms:
        return ""

    lines: list[str] = []

    success_items = [f for f in filled_forms if f.get("status") == "success"]
    guide_items = [f for f in filled_forms if f.get("status") == "guide_only"]

    if success_items:
        lines.append("\n## 📎 자동 작성된 신청서 다운로드")
        for item in success_items:
            title = item.get("original_title", "신청서")
            key = item.get("download_key", "")
            lines.append(f"- **{title}** — 다운로드 키: `{key}`")

    if guide_items:
        lines.append("\n## 📝 신청서 작성 가이드 (PDF)")
        for item in guide_items:
            title = item.get("original_title", "신청서")
            guide_text = item.get("guide_text", "")
            original_url = item.get("original_url", "")
            lines.append(f"\n### {title}")
            if guide_text:
                lines.append(guide_text)
            if original_url:
                lines.append(f"\n[원본 PDF 다운로드]({original_url})")

    return "\n".join(lines)


async def report_writer_node(state: AgentState) -> dict:
    """application_guide와 document_guidance를 마크다운 보고서로 재구성.

    LLM 호출 후 filled_forms 섹션을 코드에서 직접 추가합니다.
    """
    selected: WelfareCandidate = state["selected_service"]
    application_guide: str = state["application_guide"]
    document_guidance: str = state["document_guidance"]
    filled_forms: list[dict] = state.get("filled_forms") or []

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

    forms_section = _build_forms_section(filled_forms)
    if forms_section:
        report = report.rstrip() + "\n" + forms_section

    return {
        "final_report": report,
        "messages": [AIMessage(content=report)],
    }
