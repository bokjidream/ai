"""1단계 인터뷰 에이전트: RAG 검색에 필요한 최소 사용자 정보 수집."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command, interrupt

from graph.state import (  # noqa: TCH001
    DisabilitySeverity,
    EmploymentStatus,
    IncomeLevel,
    MaritalStatus,
    UserProfile,
)
from tools import hwnv_client

logger = logging.getLogger("bokjidream.initial_interview")

if TYPE_CHECKING:
    from graph.state import AgentState

_VALUE_CONVERTERS: dict = {
    "age": int,
    "region": str,
    "household_size": int,
    "marital_status": MaritalStatus,
    "has_children": bool,
    "disability": bool,
    "disability_severity": DisabilitySeverity,
    "employment_status": EmploymentStatus,
    "income_level": IncomeLevel,
}


def _apply_value(profile: UserProfile, field: str, raw_value) -> UserProfile:
    """추출된 원시 값을 올바른 타입으로 변환해 프로필에 적용합니다."""
    converter = _VALUE_CONVERTERS.get(field)
    value = converter(raw_value) if converter else raw_value
    return profile.model_copy(update={field: value})


def _update_missing(
    collected_field: str,
    profile: UserProfile,
    missing: list[str],
) -> list[str]:
    """수집 완료된 필드를 제거하고 disability 특수 케이스를 처리합니다."""
    new_missing = [f for f in missing if f != collected_field]

    if profile.disability is False:
        new_missing = [f for f in new_missing if f != "disability_severity"]
    elif (
        profile.disability is True
        and profile.disability_severity is None
        and "disability_severity" not in new_missing
    ):
        new_missing.append("disability_severity")

    return new_missing


async def initial_interview_node(state: AgentState) -> dict | Command:
    """1단계 인터뷰: hwnv.cloud API로 필드별 질문·추출을 수행합니다."""
    missing = list(state["initial_missing_fields"])
    if not missing:
        return {}

    current_field: str | None = state.get("interview_current_field")
    is_reask = current_field is not None
    field = current_field or missing[0]

    # pending_question이 없으면 ask_question을 호출하고 state에 저장한 뒤 재진입.
    # LangGraph는 resume 시 노드를 처음부터 재실행하므로, 저장해두지 않으면
    # ask_question이 중복 호출된다.
    question = state.get("pending_question")
    if question is None:
        try:
            question = await hwnv_client.ask_question(
                field=field,
                re_ask=is_reask,
                pre_assistant_message=state.get("interview_last_question", ""),
                pre_user_message=state.get("interview_last_answer", ""),
            )
        except Exception as e:
            logger.warning(
                "[initial_interview] ask_question 실패 field=%s: %s",
                field,
                e,
                exc_info=True,
            )
            error_msg = (
                "죄송합니다. 질문 생성 중 오류가 발생했습니다. "
                "잠시 후 다시 시도해 주세요."
            )
            return {"messages": [AIMessage(content=error_msg)]}
        return Command(
            update={"pending_question": question},
            goto="initial_interview",
        )

    user_answer: str = interrupt({"question": question, "field": field})

    try:
        result = await hwnv_client.extract_value(field, question, user_answer)
    except Exception as e:
        logger.warning(
            "[initial_interview] extract_value 실패 field=%s: %s",
            field,
            e,
            exc_info=True,
        )
        return {
            "initial_missing_fields": missing,
            "interview_current_field": field,
            "interview_last_question": question,
            "interview_last_answer": user_answer,
            "pending_question": None,
        }

    ai_msg = AIMessage(content=question)
    human_msg = HumanMessage(content=user_answer)

    if result.get("exist") and result.get("value") is not None:
        new_profile = _apply_value(state["user_profile"], field, result["value"])
        new_missing = _update_missing(field, new_profile, missing)
        return {
            "messages": [ai_msg, human_msg],
            "user_profile": new_profile,
            "initial_missing_fields": new_missing,
            "interview_current_field": None,
            "interview_last_question": question,
            "interview_last_answer": user_answer,
            "pending_question": None,
        }

    return {
        "messages": [ai_msg, human_msg],
        "initial_missing_fields": missing,
        "interview_current_field": field,
        "interview_last_question": question,
        "interview_last_answer": user_answer,
        "pending_question": None,
    }
