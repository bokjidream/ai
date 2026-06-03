"""RAG 통합 테스트 — 실제 RAG 서버가 실행 중일 때만 수행.

실행 방법:
    uv run pytest tests/test_rag_integration.py -m integration -v
"""

import pytest

from tools.rag_client import get_detail, search

pytestmark = pytest.mark.integration

_PROFILE = {
    "age": 65,
    "income_level": "기초생활수급자",
    "disability": False,
    "employment_status": "비경제활동",
    "region": "서울",
}


class TestSearchIntegration:
    async def test_returns_list(self):
        result = await search(profile=_PROFILE)
        assert isinstance(result, list)

    async def test_result_has_required_fields(self):
        result = await search(profile=_PROFILE)
        if not result:
            pytest.skip("검색 결과 없음 — 필드 검증 불가")
        item = result[0]
        assert "serv_id" in item
        assert "serv_nm" in item
        assert "serv_dgst" in item
        assert "score" in item

    async def test_empty_result_on_no_match(self):
        result = await search(profile={"age": 1, "income_level": "일반"})
        assert isinstance(result, list)

    async def test_score_is_float(self):
        result = await search(profile=_PROFILE)
        for item in result:
            assert isinstance(item["score"], float)


@pytest.fixture
async def first_candidate():
    candidates = await search(profile=_PROFILE)
    if not candidates:
        pytest.skip("검색 결과 없음 — 상세 조회 불가")
    return candidates[0]


class TestGetDetailIntegration:
    async def test_returns_dict(self, first_candidate):
        result = await get_detail(first_candidate["serv_id"])
        assert isinstance(result, dict)

    async def test_has_required_fields(self, first_candidate):
        result = await get_detail(first_candidate["serv_id"])
        assert "serv_id" in result
        assert "required_documents" in result
        assert "application_method" in result

    async def test_required_documents_is_list(self, first_candidate):
        result = await get_detail(first_candidate["serv_id"])
        assert isinstance(result["required_documents"], list)

    async def test_application_method_is_string(self, first_candidate):
        result = await get_detail(first_candidate["serv_id"])
        assert isinstance(result["application_method"], str)
