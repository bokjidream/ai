"""서류 안내 노드 — required_documents를 사용자 상황에 맞게 안내합니다."""

from langchain_core.messages import AIMessage

from graph.state import AgentState, UserProfile, WelfareCandidate
from tools.llm import get_llm
from tools.prompt_loader import load_prompt


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


async def document_guidance_node(state: AgentState) -> dict:
    """required_documents와 user_profile을 기반으로 서류 안내 텍스트 생성."""
    selected: WelfareCandidate = state["selected_service"]
    profile: UserProfile = state["user_profile"]

    if not selected.required_documents:
        fallback = (
            f"'{selected.serv_nm}' 신청에 필요한 서류 정보가 없습니다. "
            "해당 기관에 직접 문의하여 필요 서류를 확인해 주세요."
        )
        return {
            "document_guidance": fallback,
            "messages": [AIMessage(content=fallback)],
        }

    prompt_template = load_prompt("document_guidance")
    prompt = prompt_template.format(
        serv_nm=selected.serv_nm,
        required_documents="\n".join(f"- {d}" for d in selected.required_documents),
        user_info=_format_user_info(profile),
    )

    llm = get_llm()
    try:
        response = await llm.ainvoke(prompt)
        guidance = response.content
    except Exception as e:
        print(f"[LLM 오류] document_guidance {type(e).__name__}: {e}")
        guidance = (
            f"'{selected.serv_nm}' 서류 안내 생성 중 오류가 발생했습니다. "
            "해당 기관에 직접 문의해 주세요."
        )

    return {
        "document_guidance": guidance,
        "messages": [AIMessage(content=guidance)],
    }
