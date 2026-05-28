"""서류 안내 + 신청 방법 안내 노드 — LLM 1회 호출로 JSON 동시 출력."""

import json
import logging

from langchain_core.messages import AIMessage

from graph.state import AgentState, UserProfile, WelfareCandidate
from tools.llm import get_llm
from tools.prompt_loader import load_prompt

logger = logging.getLogger("bokjidream.document_guidance")


def _format_user_info(profile: UserProfile) -> str:
    lines = []
    if profile.age is not None:
        lines.append(f"- 나이: {profile.age}세")
    if profile.region is not None:
        lines.append(f"- 지역: {profile.region}")
    if profile.income_level is not None:
        lines.append(f"- 소득 수준: {profile.income_level.value}")
    if profile.disability is not None:
        lines.append(f"- 장애 여부: {'있음' if profile.disability else '없음'}")
    if profile.disability_type is not None:
        lines.append(f"- 장애 유형: {profile.disability_type}")
    if profile.disability_grade is not None:
        lines.append(f"- 장애 등급: {profile.disability_grade}")
    if profile.household_size is not None:
        lines.append(f"- 가구원 수: {profile.household_size}명")
    if profile.employment_status is not None:
        lines.append(f"- 취업 상태: {profile.employment_status.value}")
    if profile.housing_type is not None:
        lines.append(f"- 주거 유형: {profile.housing_type}")
    if profile.is_veteran is not None:
        lines.append(f"- 국가유공자: {'해당' if profile.is_veteran else '비해당'}")
    if profile.is_single_parent is not None:
        val = "해당" if profile.is_single_parent else "비해당"
        lines.append(f"- 한부모 가정: {val}")
    for key, val in profile.extra_fields.items():
        lines.append(f"- {key}: {val}")
    return "\n".join(lines) if lines else "수집된 사용자 정보 없음"


def _parse_json_response(content: str) -> dict:
    """LLM 응답에서 JSON을 파싱합니다. 마크다운 펜스 제거 후 시도."""
    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```", 2)
        inner = parts[1]
        if inner.lower().startswith("json"):
            inner = inner[4:]
        content = inner.strip()
    return json.loads(content)


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
        user_info=_format_user_info(profile),
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
        parsed = _parse_json_response(content)
        doc_guidance = parsed.get("document_guidance") or fallback_doc
        app_guide = parsed.get("application_guide") or fallback_guide
    except json.JSONDecodeError as e:
        logger.warning("[document_guidance] JSON 파싱 실패: %s", e, exc_info=True)
        doc_guidance = fallback_doc
        app_guide = fallback_guide

    return {
        "document_guidance": doc_guidance,
        "application_guide": app_guide,
        "messages": [AIMessage(content=doc_guidance)],
    }
