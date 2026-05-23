"""RAG 검색 노드 — UserProfile로 복지 서비스 후보 목록 조회."""

import asyncio
import os

from langchain_core.messages import AIMessage

import tools.hwnv_client as hwnv_client
import tools.rag_client as rag_client
from graph.state import AgentState, UserProfile, WelfareCandidate


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

    # RAG 호출 (1회 재시도)
    results = None
    last_error = None
    for _ in range(2):
        try:
            results = await rag_client.search(
                profile=_profile_to_dict(profile), top_k=top_k
            )
            break
        except Exception as e:
            last_error = e
            continue

    if results is None and last_error is not None:
        print(f"[RAG 오류] {type(last_error).__name__}: {last_error}")

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

    # 후보별 선정 이유를 병렬로 생성
    reasons = await asyncio.gather(
        *[
            hwnv_client.generate_eligibility_reason(
                serv_nm=item["serv_nm"],
                serv_dgst=item["serv_dgst"],
                user=_profile_to_dict(profile),
            )
            for item in results
        ]
    )

    candidates = [
        WelfareCandidate(
            serv_id=item["serv_id"],
            serv_nm=item["serv_nm"],
            serv_dgst=item["serv_dgst"],
            department=item.get("department", ""),
            score=item.get("score", 0.0),
            priority=priority,
            eligibility_reason=reason,
        )
        for priority, (item, reason) in enumerate(
            zip(results, reasons, strict=False), start=1
        )
    ]

    return {"welfare_candidates": candidates}
