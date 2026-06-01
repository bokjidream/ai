"""2단계 인터뷰 에이전트: 선택된 서비스의 자격 요건 기반 특화 정보 수집."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command, interrupt

from tools import hwnv_client

logger = logging.getLogger("bokjidream.detail_interview")

if TYPE_CHECKING:
    from graph.state import AgentState, UserProfile

_FIELD_INFO: dict[str, dict] = {
    "disability_type": {
        "key": "disability_type",
        "label": "장애 유형",
        "type": "string",
        "question_hint": "장애 유형(지체, 시각, 청각, 지적 등)을 부드럽게 물어보세요",
    },
    "disability_grade": {
        "key": "disability_grade",
        "label": "장애 등급",
        "type": "string",
        "question_hint": "장애 등급을 물어보세요",
    },
    "children_ages": {
        "key": "children_ages",
        "label": "자녀 나이",
        "type": "string",
        "question_hint": "자녀들의 나이를 모두 알려달라고 물어보세요",
    },
    "housing_type": {
        "key": "housing_type",
        "label": "주거 형태",
        "type": "enum",
        "enum_values": ["자가", "전세", "월세", "공공임대", "기타"],
        "question_hint": "현재 주거 형태를 선택지로 물어보세요",
    },
    "household_type": {
        "key": "household_type",
        "label": "가구 유형",
        "type": "string",
        "question_hint": "가구 형태(1인 가구, 부부 가구, 조손 가구 등)를 물어보세요",
    },
    "is_veteran": {
        "key": "is_veteran",
        "label": "국가보훈 대상 여부",
        "type": "bool",
        "question_hint": "국가보훈처에 등록된 보훈 대상자인지 물어보세요",
    },
    "is_single_parent": {
        "key": "is_single_parent",
        "label": "한부모 가정 여부",
        "type": "bool",
        "question_hint": "한부모 가정(편부/편모 가정)에 해당하는지 물어보세요",
    },
}


def _get_field_info(field: str, extra_schemas: list[dict]) -> dict | None:
    """필드명에 해당하는 field_info 딕셔너리를 반환합니다."""
    if field in _FIELD_INFO:
        return _FIELD_INFO[field]
    if field.startswith("extra:"):
        key = field.removeprefix("extra:")
        return next((s for s in extra_schemas if s.get("key") == key), None)
    return None


def _apply_extracted_value(
    profile: UserProfile,
    field: str,
    value,
) -> UserProfile:
    """추출된 값을 UserProfile에 적용합니다."""
    if field.startswith("extra:"):
        key = field.removeprefix("extra:")
        merged = {**profile.extra_fields, key: value}
        return profile.model_copy(update={"extra_fields": merged})

    if field == "children_ages" and isinstance(value, str):
        ages = [int(m) for m in re.findall(r"\d+", value)]
        value = ages if ages else None

    if value is not None:
        return profile.model_copy(update={field: value})
    return profile


async def detail_interview_node(state: AgentState) -> dict | Command:
    """2단계 인터뷰: hwnv detail_asker/detail_interviewer로 필드별 정보를 수집합니다."""
    missing = list(state["detail_missing_fields"])
    if not missing:
        return {}

    extra_schemas: list[dict] = state.get("extra_field_schemas", [])
    current_field: str | None = state.get("detail_current_field")
    is_reask = current_field is not None
    field = current_field or missing[0]

    field_info = _get_field_info(field, extra_schemas)
    if field_info is None:
        logger.debug("[detail_interview] 알 수 없는 필드 스킵: %s", field)
        return {"detail_missing_fields": [f for f in missing if f != field]}

    question = state.get("pending_question")
    if question is None:
        try:
            question = await hwnv_client.ask_detail_question(
                field_info=field_info,
                re_ask=is_reask,
                pre_assistant_message=state.get("detail_last_question", ""),
                pre_user_message=state.get("detail_last_answer", ""),
            )
        except Exception as e:
            logger.warning(
                "[detail_interview] ask_detail_question 실패 field=%s: %s",
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
            goto="detail_interview",
        )

    user_answer: str = interrupt({"question": question, "field": field})

    # 건너뛰기 요청 — 모든 2단계 필드를 비워 document_guidance로 진행
    if user_answer.strip() == "__skip__":
        logger.info("[detail_interview] 2단계 인터뷰 건너뛰기 요청")
        return {
            "detail_missing_fields": [],
            "detail_current_field": None,
            "pending_question": None,
        }

    try:
        result = await hwnv_client.extract_detail_value(
            field_info, question, user_answer
        )
    except Exception as e:
        logger.warning(
            "[detail_interview] extract_detail_value 실패 field=%s: %s",
            field,
            e,
            exc_info=True,
        )
        return {
            "detail_missing_fields": missing,
            "detail_current_field": field,
            "detail_last_question": question,
            "detail_last_answer": user_answer,
            "pending_question": None,
        }

    ai_msg = AIMessage(content=question)
    human_msg = HumanMessage(content=user_answer)

    logger.debug(
        "[detail_interview] 2단계 필드 추출: field=%s result=%s", field, result
    )

    if result.get("exist") and result.get("value") is not None:
        new_profile = _apply_extracted_value(
            state["user_profile"], field, result["value"]
        )
        new_missing = [f for f in missing if f != field]
        return {
            "messages": [ai_msg, human_msg],
            "user_profile": new_profile,
            "detail_missing_fields": new_missing,
            "detail_current_field": None,
            "detail_last_question": question,
            "detail_last_answer": user_answer,
            "pending_question": None,
        }

    if not result.get("re_ask"):
        new_missing = [f for f in missing if f != field]
        return {
            "messages": [ai_msg, human_msg],
            "detail_missing_fields": new_missing,
            "detail_current_field": None,
            "detail_last_question": question,
            "detail_last_answer": user_answer,
            "pending_question": None,
        }

    return {
        "messages": [ai_msg, human_msg],
        "detail_missing_fields": missing,
        "detail_current_field": field,
        "detail_last_question": question,
        "detail_last_answer": user_answer,
        "pending_question": None,
    }
