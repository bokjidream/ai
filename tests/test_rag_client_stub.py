"""RAG 클라이언트 단위 테스트 — httpx 응답을 모킹하여 검증."""

import json

import httpx
import pytest
from pytest_httpx import HTTPXMock

from tools.rag_client import get_detail, search

_BASE_URL = "http://test-rag"

_SEARCH_RESPONSE = {
    "results": [
        {
            "serv_id": "WLF-001",
            "serv_nm": "기초연금",
            "serv_dgst": "만 65세 이상 저소득 노인 연금",
            "department": "보건복지부",
            "score": 0.92,
        }
    ]
}

_DETAIL_RESPONSE = {
    "serv_id": "WLF-001",
    "serv_nm": "기초연금",
    "required_documents": ["신분증", "통장사본"],
    "application_fields": ["신청인 성명", "생년월일"],
    "application_url": "https://www.bokjiro.go.kr",
}


@pytest.fixture(autouse=True)
def set_rag_url(monkeypatch):
    monkeypatch.setenv("RAG_SERVICE_URL", _BASE_URL)


class TestSearch:
    async def test_returns_list(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_SEARCH_RESPONSE)
        result = await search(profile={"age": 65, "income_level": "기초생활수급자"})
        assert isinstance(result, list)

    async def test_each_item_has_required_fields(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_SEARCH_RESPONSE)
        result = await search(profile={"age": 65, "income_level": "기초생활수급자"})
        for item in result:
            assert "serv_id" in item
            assert "serv_nm" in item
            assert "serv_dgst" in item
            assert "department" in item
            assert "score" in item

    async def test_top_k_default_uses_env(self, httpx_mock: HTTPXMock, monkeypatch):
        monkeypatch.setenv("RAG_SEARCH_TOP_K", "1")
        httpx_mock.add_response(json={"results": _SEARCH_RESPONSE["results"][:1]})
        result = await search(profile={"age": 65})
        assert isinstance(result, list)

    async def test_empty_profile_still_returns_list(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"results": []})
        result = await search(profile={})
        assert isinstance(result, list)

    async def test_score_is_float(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_SEARCH_RESPONSE)
        result = await search(profile={"age": 65})
        for item in result:
            assert isinstance(item["score"], float)

    async def test_raises_on_server_error(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            await search(profile={"age": 65})

    async def test_top_k_included_in_request_body(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"results": []})
        await search(profile={"age": 65}, top_k=3)
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["top_k"] == 3


class TestGetDetail:
    async def test_returns_dict(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_DETAIL_RESPONSE)
        result = await get_detail("WLF-001")
        assert isinstance(result, dict)

    async def test_has_required_fields(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_DETAIL_RESPONSE)
        result = await get_detail("WLF-001")
        assert "serv_id" in result
        assert "serv_nm" in result
        assert "required_documents" in result
        assert "application_fields" in result
        assert "application_url" in result

    async def test_required_documents_is_list(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_DETAIL_RESPONSE)
        result = await get_detail("WLF-001")
        assert isinstance(result["required_documents"], list)

    async def test_application_fields_is_list(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_DETAIL_RESPONSE)
        result = await get_detail("WLF-001")
        assert isinstance(result["application_fields"], list)

    async def test_raises_on_unknown_service(self, httpx_mock: HTTPXMock):
        # 실제 서버는 없는 ID에 404를 반환 → rag_detail_node의 예외 처리가 잡아줌
        httpx_mock.add_response(status_code=404)
        with pytest.raises(httpx.HTTPStatusError):
            await get_detail("UNKNOWN-999")

    async def test_serv_id_matches_requested(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json=_DETAIL_RESPONSE)
        result = await get_detail("WLF-001")
        assert result["serv_id"] == "WLF-001"
