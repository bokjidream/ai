"""RAG 클라이언트 스텁 인터페이스 계약 검증 테스트."""

from tools.rag_client import get_detail, search


class TestSearch:
    async def test_returns_list(self):
        result = await search(profile={"age": 65, "income_level": "기초수급"})
        assert isinstance(result, list)

    async def test_each_item_has_required_fields(self):
        result = await search(profile={"age": 65, "income_level": "기초수급"})
        for item in result:
            assert "serv_id" in item
            assert "serv_nm" in item
            assert "serv_dgst" in item
            assert "department" in item
            assert "score" in item

    async def test_top_k_limits_results(self):
        result = await search(profile={"age": 65}, top_k=2)
        assert len(result) <= 2

    async def test_top_k_default_uses_env(self, monkeypatch):
        monkeypatch.setenv("RAG_SEARCH_TOP_K", "1")
        result = await search(profile={"age": 65})
        assert len(result) <= 1

    async def test_empty_profile_still_returns_list(self):
        result = await search(profile={})
        assert isinstance(result, list)

    async def test_score_is_float(self):
        result = await search(profile={"age": 65})
        for item in result:
            assert isinstance(item["score"], float)


class TestGetDetail:
    async def test_returns_dict(self):
        result = await get_detail("WLF-001")
        assert isinstance(result, dict)

    async def test_has_required_fields(self):
        result = await get_detail("WLF-001")
        assert "serv_id" in result
        assert "serv_nm" in result
        assert "required_documents" in result
        assert "application_fields" in result
        assert "application_url" in result

    async def test_required_documents_is_list(self):
        result = await get_detail("WLF-001")
        assert isinstance(result["required_documents"], list)

    async def test_application_fields_is_list(self):
        result = await get_detail("WLF-001")
        assert isinstance(result["application_fields"], list)

    async def test_unknown_service_returns_empty_lists(self):
        result = await get_detail("UNKNOWN-999")
        assert result["serv_id"] == "UNKNOWN-999"
        assert result["required_documents"] == []
        assert result["application_fields"] == []
        assert result["application_url"] is None

    async def test_serv_id_matches_requested(self):
        result = await get_detail("WLF-002")
        assert result["serv_id"] == "WLF-002"
