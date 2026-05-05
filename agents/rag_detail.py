"""RAG 상세 조회 노드 — 선택된 서비스의 required_documents 등 상세 필드 보완."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

import tools.rag_client as rag_client
from tools.llm import get_llm

if TYPE_CHECKING:
    from graph.state import AgentState, UserProfile, WelfareCandidate

_MAX_RETRY = int(os.getenv("LLM_MAX_RETRY", "2"))

_STAGE_2_FIELDS = [
    "disability_type",
    "disability_grade",
    "children_ages",
    "housing_type",
    "household_type",
    "is_veteran",
    "is_single_parent",
]


class _RequiredFields(BaseModel):
    regular_fields: list[str] = []
    extra_fields: list[str] = []


async def _infer_missing_fields(
    profile: UserProfile,
    tgtr_dtl_cn: str,
    slct_crit_cn: str,
    trgter_indvdl: list[str],
) -> list[str]:
    """자격 요건 텍스트에서 추가 수집이 필요한 UserProfile 필드를 추론합니다."""
    system = (
        "당신은 복지 서비스 자격 심사 전문가입니다.\n"
        "주어진 서비스 자격 요건을 분석하여,"
        " 사용자의 자격 여부 확인에 필요한 추가 정보를 결정하세요.\n\n"
        f"수집 가능한 표준 필드 목록: {', '.join(_STAGE_2_FIELDS)}\n"
        "규칙:\n"
        "- 서비스 자격 요건에 필요한 표준 필드"
        " → regular_fields에 필드명 추가\n"
        "- 표준 필드에 없는 특수 정보가 필요한 경우"
        " → extra_fields에 영문 snake_case 키 추가\n"
        "- 현재 사용자 프로필에 이미 있는 정보는 포함하지 마세요\n\n"
        f"현재 사용자 프로필: {profile.model_dump(exclude_none=True)}"
    )
    human = (
        f"[대상자 상세]\n{tgtr_dtl_cn}\n\n"
        f"[선정 기준]\n{slct_crit_cn}\n\n"
        f"[대상자 유형]\n{', '.join(trgter_indvdl)}"
    )

    extractor = get_llm().with_structured_output(_RequiredFields)
    result: _RequiredFields | None = None
    for _ in range(_MAX_RETRY + 1):
        try:
            result = await extractor.ainvoke(
                [SystemMessage(content=system), HumanMessage(content=human)]
            )
            break
        except Exception:
            continue

    if result is None:
        return []

    missing: list[str] = []
    for field in result.regular_fields:
        if field in _STAGE_2_FIELDS and getattr(profile, field, None) is None:
            missing.append(field)
    for key in result.extra_fields:
        if key not in profile.extra_fields:
            missing.append(f"extra:{key}")

    return missing


async def rag_detail_node(state: AgentState) -> dict:
    """RAG 상세 조회 후 selected_service와 detail_missing_fields를 갱신합니다."""
    selected: WelfareCandidate = state["selected_service"]
    profile: UserProfile = state["user_profile"]

    detail = None
    for _ in range(2):
        try:
            detail = await rag_client.get_detail(selected.serv_id)
            break
        except Exception:
            continue

    if detail is None:
        error_msg = (
            "서비스 상세 정보를 불러오지 못했습니다. 기본 정보로 계속 진행합니다."
        )
        return {
            "selected_service": selected,
            "detail_missing_fields": [],
            "messages": [AIMessage(content=error_msg)],
        }

    updated = selected.model_copy(
        update={
            "required_documents": detail.get("required_documents", []),
            "application_fields": detail.get("application_fields", []),
            "application_url": detail.get("application_url"),
            "detail_fetched": True,
        }
    )

    missing_fields = await _infer_missing_fields(
        profile=profile,
        tgtr_dtl_cn=detail.get("tgtr_dtl_cn", ""),
        slct_crit_cn=detail.get("slct_crit_cn", ""),
        trgter_indvdl=detail.get("trgter_indvdl", []),
    )

    return {
        "selected_service": updated,
        "detail_missing_fields": missing_fields,
    }
