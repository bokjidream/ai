"""RAG 검색 노드 — UserProfile로 복지 서비스 후보 목록 조회."""

import logging
import os

from langchain_core.messages import AIMessage
from tenacity import retry, stop_after_attempt, wait_exponential

import tools.rag_client as rag_client
from graph.state import AgentState, UserProfile, WelfareCandidate

logger = logging.getLogger("bokjidream.rag_search")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
async def _search_with_retry(profile: dict, top_k: int) -> list[dict]:
    """RAG 검색 — 최대 3회 지수 백오프 재시도 (1s→2s→4s)."""
    return await rag_client.search(profile=profile, top_k=top_k)


def _profile_to_dict(profile: UserProfile) -> dict:
    """UserProfile 최소 필드를 RAG 전송용 flat dict로 변환."""
    data = {}
    if profile.age is not None:
        data["age"] = profile.age
    if profile.income_level is not None:
        data["income_level"] = profile.income_level.value
    if profile.disability is not None:
        data["disability"] = profile.disability
    if profile.disability_severity is not None:
        data["disability_severity"] = profile.disability_severity.value
    if profile.employment_status is not None:
        data["employment_status"] = profile.employment_status.value
    if profile.region is not None:
        data["region"] = profile.region
    if profile.household_size is not None:
        data["household_size"] = profile.household_size
    if profile.marital_status is not None:
        data["marital_status"] = profile.marital_status.value
    if profile.has_children is not None:
        data["has_children"] = profile.has_children
    return data


async def rag_search_node(state: AgentState) -> dict:
    """RAG 후보 검색 노드 — UserProfile → WelfareCandidate 리스트."""
    profile: UserProfile = state["user_profile"]
    top_k = int(os.getenv("RAG_SEARCH_TOP_K", "5"))

    results = None
    try:
        results = await _search_with_retry(_profile_to_dict(profile), top_k)
    except Exception as e:
        logger.warning("[rag_search] RAG 검색 최종 실패: %s", e, exc_info=True)

    if results is None:
        error_msg = (
            "죄송합니다. 복지 서비스 검색 중 연결 오류가 발생했습니다. "
            "잠시 후 다시 시도해 주세요."
        )
        return {
            "welfare_candidates": [],
            "messages": [AIMessage(content=error_msg)],
        }

    if not results:
        no_result_msg = "입력하신 정보로 해당하는 복지 서비스를 찾지 못했습니다."
        return {
            "welfare_candidates": [],
            "messages": [AIMessage(content=no_result_msg)],
        }

    # score 내림차순 정렬
    results.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    candidates = [
        WelfareCandidate(
            serv_id=item["serv_id"],
            serv_nm=item["serv_nm"],
            serv_dgst=item["serv_dgst"],
            department=item.get("department", ""),
            score=item.get("score", 0.0),
            priority=priority,
            eligibility_reason="",
        )
        for priority, item in enumerate(results, start=1)
    ]

    return {"welfare_candidates": candidates}
