"""1단계 인터뷰 에이전트: RAG 검색에 필요한 최소 사용자 정보 수집."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel

# Pydantic 모델 필드 타입으로 런타임에 필요 — TYPE_CHECKING 블록으로 이동 불가
from graph.state import (  # noqa: TCH001
    DisabilitySeverity,
    EmploymentStatus,
    IncomeLevel,
    MaritalStatus,
    UserProfile,
)
from tools.llm import get_llm
from tools.prompt_loader import load_prompt

if TYPE_CHECKING:
    from graph.state import AgentState

_FIELD_LABELS: dict[str, str] = {
    "age": "나이",
    "region": "거주 지역",
    "household_size": "가구원 수",
    "marital_status": "혼인 상태",
    "has_children": "자녀 유무",
    "disability": "장애 여부",
    "disability_severity": "장애 정도(경증/중증)",
    "employment_status": "취업 상태",
    "income_level": "소득 수준",
}

_MAX_RETRY = 2


class _ProfileExtraction(BaseModel):
    """structured output 스키마: 대화에서 추출된 1단계 프로필 필드."""

    age: int | None = None
    region: str | None = None
    household_size: int | None = None
    marital_status: MaritalStatus | None = None
    has_children: bool | None = None
    disability: bool | None = None
    disability_severity: DisabilitySeverity | None = None
    employment_status: EmploymentStatus | None = None
    income_level: IncomeLevel | None = None


async def _generate_question(
    profile: UserProfile,
    missing: list[str],
    history: list,
) -> str:
    """누락 필드에 대한 자연스러운 인터뷰 질문을 생성합니다."""
    system_prompt = load_prompt("initial_interview")
    missing_labels = [_FIELD_LABELS.get(f, f) for f in missing]
    collected = {
        k: v
        for k, v in profile.model_dump(exclude_none=True).items()
        if k not in ("is_elderly", "extra_fields")
    }

    instruction = (
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
) -> tuple[UserProfile, list[str]]:
    """사용자 답변에서 프로필 필드를 추출합니다. 실패 시 최대 2회 재시도.

    파싱 실패가 모든 재시도에서 발생하면 기존 profile과 missing을 그대로 반환합니다.
    """
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

    extractor = get_llm().with_structured_output(_ProfileExtraction)
    extraction: _ProfileExtraction | None = None
    for _ in range(_MAX_RETRY + 1):
        try:
            extraction = await extractor.ainvoke(messages)
            break
        except Exception:
            continue

    if extraction is None:
        return profile, missing

    updates = {k: v for k, v in extraction.model_dump().items() if v is not None}
    new_profile = profile.model_copy(update=updates)

    # 장애 없음 확정 시 severity 필드 초기화
    if new_profile.disability is False:
        new_profile = new_profile.model_copy(update={"disability_severity": None})

    new_missing: list[str] = []
    for field in missing:
        if field == "disability_severity" and new_profile.disability is False:
            continue
        if getattr(new_profile, field, None) is None:
            new_missing.append(field)

    # 장애 있음으로 확인됐는데 severity 미수집이면 missing에 추가
    if (
        new_profile.disability is True
        and new_profile.disability_severity is None
        and "disability_severity" not in new_missing
    ):
        new_missing.append("disability_severity")

    return new_profile, new_missing


async def initial_interview_node(state: AgentState) -> dict:
    """1단계 인터뷰: 최소 사용자 정보를 수집하여 RAG 검색 기반을 마련합니다."""
    profile = state["user_profile"]
    missing = list(state["initial_missing_fields"])

    if not missing:
        return {}

    question = await _generate_question(profile, missing, list(state["messages"]))
    ai_message = AIMessage(content=question)

    user_answer: str = interrupt({"question": question, "missing_fields": missing})

    new_profile, new_missing = await _extract_profile(
        profile,
        missing,
        user_answer,
        list(state["messages"]) + [ai_message],
    )

    return {
        "messages": [ai_message, HumanMessage(content=user_answer)],
        "user_profile": new_profile,
        "initial_missing_fields": new_missing,
    }
