"""2단계 인터뷰 에이전트: 선택된 서비스의 자격 요건 기반 특화 정보 수집."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel

from graph.state import UserProfile  # noqa: TCH001
from tools.llm import get_llm
from tools.prompt_loader import load_prompt

if TYPE_CHECKING:
    from graph.state import AgentState, WelfareCandidate

_FIELD_LABELS: dict[str, str] = {
    "disability_type": "장애 유형",
    "disability_grade": "장애 등급",
    "children_ages": "자녀 나이",
    "housing_type": "주거 형태",
    "household_type": "가구 유형",
    "is_veteran": "국가보훈 대상 여부",
    "is_single_parent": "한부모 가정 여부",
}

_MAX_RETRY = int(os.getenv("LLM_MAX_RETRY", "2"))
_HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW_SIZE", "10"))
_RETRY_MSG = "이해하지 못했습니다. 좀 더 구체적으로 말씀해주시겠어요?"


class _DetailExtraction(BaseModel):
    """structured output 스키마: 대화에서 추출된 2단계 프로필 필드."""

    disability_type: str | None = None
    disability_grade: str | None = None
    children_ages: list[int] | None = None
    housing_type: str | None = None
    household_type: str | None = None
    is_veteran: bool | None = None
    is_single_parent: bool | None = None
    extra_fields: dict[str, str | int | bool] = {}


async def _generate_question(
    profile: UserProfile,
    missing: list[str],
    selected: WelfareCandidate,
    history: list,
) -> str:
    """선택된 서비스 자격 요건을 참고하여 누락 필드에 대한 질문을 생성합니다."""
    system_prompt = load_prompt("detail_interview")

    missing_labels = [_FIELD_LABELS.get(f, f.removeprefix("extra:")) for f in missing]
    collected = {
        k: v
        for k, v in profile.model_dump(exclude_none=True).items()
        if k not in ("is_elderly", "extra_fields")
    }
    if profile.extra_fields:
        collected["extra_fields"] = profile.extra_fields

    instruction = (
        f"[시스템] 선택된 서비스: {selected.serv_nm}\n"
        f"[시스템] 서비스 설명: {selected.serv_dgst}\n"
        f"[시스템] 아직 수집하지 못한 정보: {', '.join(missing_labels)}\n"
        f"[시스템] 현재까지 파악된 정보: {collected}"
    )
    messages = [
        SystemMessage(content=system_prompt),
        *history,
        HumanMessage(content=instruction),
    ]
    response = await get_llm().ainvoke(messages)
    return response.content


async def _extract_profile(
    profile: UserProfile,
    missing: list[str],
    user_answer: str,
    history: list,
) -> tuple[UserProfile, list[str], bool]:
    """사용자 답변에서 2단계 프로필 필드를 추출합니다.

    실패 시 최대 LLM_MAX_RETRY회 재시도.
    반환값: (profile, missing, extraction_failed)
    - extraction_failed=True: 모든 재시도 소진, 기존 profile/missing 유지
    "extra:KEY" 접두사 필드는 user_profile.extra_fields에 저장합니다.
    """
    regular_missing = [f for f in missing if not f.startswith("extra:")]
    extra_missing = [f for f in missing if f.startswith("extra:")]
    extra_keys_missing = [f.removeprefix("extra:") for f in extra_missing]

    extract_system = (
        "사용자의 답변에서 복지 서비스 신청용 개인 정보를 추출하세요.\n"
        "확실하지 않은 값은 null로 두세요. 추론하거나 가정하지 마세요.\n"
        f"추출 대상 필드: {', '.join(missing)}"
    )
    messages = [
        SystemMessage(content=extract_system),
        *history,
        HumanMessage(content=user_answer),
    ]

    extractor = get_llm().with_structured_output(_DetailExtraction)
    extraction: _DetailExtraction | None = None
    for _ in range(_MAX_RETRY + 1):
        try:
            extraction = await extractor.ainvoke(messages)
            break
        except Exception:
            continue

    if extraction is None:
        return profile, missing, True

    # 일반 필드 업데이트
    regular_updates = {
        k: v
        for k, v in extraction.model_dump(exclude={"extra_fields"}).items()
        if v is not None
    }
    new_profile = profile.model_copy(update=regular_updates)

    # extra_fields 업데이트
    if extraction.extra_fields:
        merged_extra = {**new_profile.extra_fields, **extraction.extra_fields}
        new_profile = new_profile.model_copy(update={"extra_fields": merged_extra})

    # new_missing 계산
    new_missing: list[str] = []
    for field in regular_missing:
        if getattr(new_profile, field, None) is None:
            new_missing.append(field)
    for key in extra_keys_missing:
        if key not in new_profile.extra_fields:
            new_missing.append(f"extra:{key}")

    return new_profile, new_missing, False


async def detail_interview_node(state: AgentState) -> dict:
    """2단계 인터뷰: 선택된 서비스의 자격 요건 기반으로 특화 정보를 수집합니다."""
    profile = state["user_profile"]
    missing = list(state["detail_missing_fields"])
    selected = state["selected_service"]

    if not missing:
        return {}

    history = list(state["messages"])[-_HISTORY_WINDOW:]

    question = await _generate_question(profile, missing, selected, history)
    ai_message = AIMessage(content=question)

    user_answer: str = interrupt({"question": question, "missing_fields": missing})

    new_profile, new_missing, extraction_failed = await _extract_profile(
        profile,
        missing,
        user_answer,
        (history + [ai_message])[-_HISTORY_WINDOW:],
    )

    messages = [ai_message, HumanMessage(content=user_answer)]
    if extraction_failed:
        messages.append(AIMessage(content=_RETRY_MSG))

    return {
        "messages": messages,
        "user_profile": new_profile,
        "detail_missing_fields": new_missing,
    }
