"""서류 안내 + 신청 방법 안내 노드 — LLM 1회 호출로 JSON 동시 출력.

document_guidance_node: LLM 호출 후 state 커밋 (interrupt 없음)
service_detail_pause_node: interrupt만 수행 → 웹에서 '초안 작성하기' 버튼 클릭 대기
"""

import json
import logging

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from graph.state import AgentState, UserProfile, WelfareCandidate
from tools.json_utils import parse_llm_json
from tools.llm import get_llm
from tools.profile_utils import format_user_profile
from tools.prompt_loader import load_prompt

logger = logging.getLogger("bokjidream.document_guidance")


async def document_guidance_node(state: AgentState) -> dict:
    """required_documents + application_method를 LLM 1회 호출로 JSON 출력.

    출력 state 필드: document_guidance, application_guide
    """
    selected: WelfareCandidate = state["selected_service"]
    profile: UserProfile = state["user_profile"]

    has_documents = bool(selected.required_documents)
    has_method = bool(selected.application_method)

    fallback_doc = (
        f"'{selected.serv_nm}' 신청에 필요한 서류 정보가 없습니다. "
        "해당 기관에 직접 문의하여 필요 서류를 확인해 주세요."
    )
    fallback_guide = (
        f"'{selected.serv_nm}' 신청 방법 정보가 없습니다. "
        "해당 기관에 직접 문의하여 신청 방법을 확인해 주세요."
    )

    if not has_documents and not has_method:
        return {
            "document_guidance": fallback_doc,
            "application_guide": fallback_guide,
            "messages": [AIMessage(content=fallback_doc)],
        }

    required_docs_text = (
        "\n".join(f"- {d}" for d in selected.required_documents)
        if selected.required_documents
        else "서류 목록 정보 없음 — 신청방법 원문을 참고하세요."
    )

    prompt_template = load_prompt("document_guidance")
    prompt = prompt_template.format(
        serv_nm=selected.serv_nm,
        required_documents=required_docs_text,
        application_method=selected.application_method or "신청방법 정보 없음",
        user_info=format_user_profile(profile, bullet=True),
    )

    llm = get_llm()

    try:
        response = await llm.ainvoke(prompt)
        content = response.content
    except Exception as e:
        logger.warning("[document_guidance] LLM 호출 실패: %s", e, exc_info=True)
        return {
            "document_guidance": fallback_doc,
            "application_guide": fallback_guide,
            "messages": [AIMessage(content=fallback_doc)],
        }

    try:
        parsed = parse_llm_json(content)
        doc_guidance = parsed.get("document_guidance") or fallback_doc
        app_guide = parsed.get("application_guide") or fallback_guide
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("[document_guidance] JSON 파싱 실패: %s", e, exc_info=True)
        doc_guidance = fallback_doc
        app_guide = fallback_guide

    return {
        "document_guidance": doc_guidance,
        "application_guide": app_guide,
        "messages": [AIMessage(content=doc_guidance)],
    }


async def service_detail_pause_node(state: AgentState) -> dict:
    """서비스 상세 페이지 표시 후 '초안 작성하기' 클릭 대기.

    document_guidance_node가 state를 커밋한 뒤 이 노드가 interrupt를 발생시키므로
    웹이 받는 service_detail 응답에 guidance 내용이 정상적으로 포함된다.
    """
    interrupt({"type": "service_detail"})
    return {}
