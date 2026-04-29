"""RAG 서비스 HTTP 클라이언트."""

import os

import httpx

_TIMEOUT = 10.0


def _base_url() -> str:
    return os.getenv("RAG_SERVICE_URL", "http://localhost:8000")


async def search(profile: dict, top_k: int | None = None) -> list[dict]:
    """복지 서비스 후보 목록 검색.

    Args:
        profile: UserProfile 핵심 필드를 담은 flat dict (age, income_level 등)
        top_k: 반환할 최대 후보 수. None이면 RAG_SEARCH_TOP_K 환경변수 사용 (기본 5)

    Returns:
        [{"serv_id", "serv_nm", "serv_dgst", "department", "score"}, ...]
        결과 없으면 빈 리스트 반환.
    """
    if top_k is None:
        top_k = int(os.getenv("RAG_SEARCH_TOP_K", "5"))

    async with httpx.AsyncClient(base_url=_base_url(), timeout=_TIMEOUT) as client:
        response = await client.post(
            "/welfare/search",
            json={**profile, "top_k": top_k},
        )
        response.raise_for_status()
        return response.json()["results"]


async def get_detail(service_id: str) -> dict:
    """특정 복지 서비스 상세 정보 조회.

    Args:
        service_id: RAG 서비스 ID (WelfareCandidate.serv_id)

    Returns:
        {"serv_id", "serv_nm", "required_documents", "application_fields",
        "application_url", ...}
    """
    async with httpx.AsyncClient(base_url=_base_url(), timeout=_TIMEOUT) as client:
        response = await client.get(f"/welfare/{service_id}", timeout=_TIMEOUT)
        response.raise_for_status()
        return response.json()
