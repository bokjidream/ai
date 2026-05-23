"""RAG 상세 조회 노드 — 선택된 서비스의 required_documents 등 상세 필드 보완."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage

import tools.hwnv_client as hwnv_client
import tools.rag_client as rag_client

if TYPE_CHECKING:
    from graph.state import AgentState, UserProfile, WelfareCandidate

_STAGE_2_FIELDS = [
    "disability_type",
    "disability_grade",
    "children_ages",
    "housing_type",
    "household_type",
    "is_veteran",
    "is_single_parent",
]


def _is_children_field(key: str, label: str) -> bool:
    return (
        "children" in key.lower()
        or "child" in key.lower()
        or "자녀" in label
        or "아동" in label
    )


def _classify_schemas(
    schemas: list[dict],
    profile: UserProfile,
) -> tuple[list[str], list[dict]]:
    """field_extractor 결과를 표준 필드와 extra 필드로 분류합니다.

    Returns:
        (regular_missing, extra_schemas)
        - regular_missing: _STAGE_2_FIELDS 중 아직 수집 안 된 것
        - extra_schemas: 표준 필드에 없는 커스텀 필드 스키마 목록
    """
    regular_missing: list[str] = []
    extra_schemas: list[dict] = []

    for schema in schemas:
        key = schema.get("key", "")
        if key in _STAGE_2_FIELDS:
            if getattr(profile, key, None) is None:
                regular_missing.append(key)
        elif key not in profile.extra_fields:
            if profile.has_children is False and _is_children_field(
                key, schema.get("label", "")
            ):
                continue
            extra_schemas.append(schema)

    if not profile.disability:
        regular_missing = [
            f
            for f in regular_missing
            if f not in ("disability_type", "disability_grade")
        ]

    return regular_missing, extra_schemas


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
            "extra_field_schemas": [],
            "messages": [AIMessage(content=error_msg)],
        }

    updated = selected.model_copy(
        update={
            "required_documents": detail.get("required_documents", []),
            "application_method": detail.get("application_method", ""),
            "application_url": detail.get("application_url"),
            "application_forms": detail.get("application_forms", []),
            "detail_fetched": True,
        }
    )

    schemas: list[dict] = []
    try:
        schemas = await hwnv_client.extract_extra_field_schemas(
            {
                "serv_nm": detail.get("serv_nm", ""),
                "tgtr_dtl_cn": detail.get("tgtr_dtl_cn", ""),
                "slct_crit_cn": detail.get("slct_crit_cn", ""),
                "trgter_indvdl": detail.get("trgter_indvdl", []),
            }
        )
    except Exception as e:
        print(f"[hwnv field_extractor 오류] {type(e).__name__}: {e}")

    regular_missing, extra_schemas = _classify_schemas(schemas, profile)
    missing_fields = regular_missing + [f"extra:{s['key']}" for s in extra_schemas]

    return {
        "selected_service": updated,
        "detail_missing_fields": missing_fields,
        "extra_field_schemas": extra_schemas,
    }
