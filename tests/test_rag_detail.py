"""RAG 상세 조회 노드 테스트."""

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from agents.rag_detail import rag_detail_node
from graph.state import (
    AgentState,
    EmploymentStatus,
    IncomeLevel,
    UserProfile,
    WelfareCandidate,
)


def _make_selected() -> WelfareCandidate:
    return WelfareCandidate(
        serv_id="WLF-001",
        serv_nm="기초생활수급자 생계급여",
        serv_dgst="생활이 어려운 기초생활수급자에게 급여를 지급합니다.",
        department="보건복지부",
        score=0.95,
        priority=1,
    )


def _make_state(**kwargs) -> AgentState:
    defaults = {
        "messages": [],
        "user_profile": UserProfile(
            age=65,
            income_level=IncomeLevel.BASIC,
            disability=False,
            employment_status=EmploymentStatus.INACTIVE,
            region="서울",
        ),
        "initial_missing_fields": [],
        "welfare_candidates": [],
        "selected_service": _make_selected(),
        "detail_missing_fields": [],
        "document_guidance": "",
        "application_guide": "",
        "final_report": "",
    }
    defaults.update(kwargs)
    return defaults  # type: ignore[return-value]


_DUMMY_DETAIL = {
    "serv_id": "WLF-001",
    "serv_nm": "기초생활수급자 생계급여",
    "required_documents": ["사회보장급여 신청서", "신분증"],
    "application_fields": ["신청인 성명", "주소"],
    "application_url": "https://www.bokjiro.go.kr",
    "tgtr_dtl_cn": "기초생활수급자 중 생계급여 수급자",
    "slct_crit_cn": "소득인정액이 생계급여 선정기준 이하인 자",
    "trgter_indvdl": ["저소득층"],
}


class TestRagDetailNode:
    @patch("agents.rag_detail._infer_missing_fields", new_callable=AsyncMock)
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_updates_selected_service_on_success(
        self, mock_get_detail, mock_infer
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_infer.return_value = []

        result = await rag_detail_node(_make_state())

        updated = result["selected_service"]
        assert updated.detail_fetched is True
        assert updated.required_documents == ["사회보장급여 신청서", "신분증"]
        assert updated.application_fields == ["신청인 성명", "주소"]
        assert updated.application_url == "https://www.bokjiro.go.kr"

    @patch("agents.rag_detail._infer_missing_fields", new_callable=AsyncMock)
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_preserves_existing_fields_on_success(
        self, mock_get_detail, mock_infer
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_infer.return_value = []

        result = await rag_detail_node(_make_state())

        updated = result["selected_service"]
        assert updated.serv_id == "WLF-001"
        assert updated.serv_nm == "기초생활수급자 생계급여"
        assert updated.score == 0.95
        assert updated.priority == 1

    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_network_error_retries_twice(self, mock_get_detail):
        mock_get_detail.side_effect = Exception("Connection error")

        await rag_detail_node(_make_state())

        assert mock_get_detail.call_count == 2

    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_network_error_returns_error_message(self, mock_get_detail):
        mock_get_detail.side_effect = Exception("Connection error")

        result = await rag_detail_node(_make_state())

        assert isinstance(result["messages"][0], AIMessage)
        assert "상세 정보" in result["messages"][0].content

    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_network_error_preserves_original_selected_service(
        self, mock_get_detail
    ):
        mock_get_detail.side_effect = Exception("Connection error")
        original = _make_selected()

        result = await rag_detail_node(_make_state())

        assert result["selected_service"].detail_fetched is False
        assert result["selected_service"].serv_id == original.serv_id

    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_network_error_returns_empty_detail_missing_fields(
        self, mock_get_detail
    ):
        mock_get_detail.side_effect = Exception("Connection error")

        result = await rag_detail_node(_make_state())

        assert result["detail_missing_fields"] == []

    @patch("agents.rag_detail._infer_missing_fields", new_callable=AsyncMock)
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_missing_optional_fields_default_to_empty(
        self, mock_get_detail, mock_infer
    ):
        mock_get_detail.return_value = {
            "serv_id": "WLF-001",
            "serv_nm": "기초생활수급자 생계급여",
        }
        mock_infer.return_value = []

        result = await rag_detail_node(_make_state())

        updated = result["selected_service"]
        assert updated.required_documents == []
        assert updated.application_fields == []
        assert updated.application_url is None
        assert updated.detail_fetched is True

    @patch("agents.rag_detail._infer_missing_fields", new_callable=AsyncMock)
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_sets_detail_missing_fields_from_llm(
        self, mock_get_detail, mock_infer
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_infer.return_value = ["housing_type", "is_veteran"]

        result = await rag_detail_node(_make_state())

        assert result["detail_missing_fields"] == ["housing_type", "is_veteran"]

    @patch("agents.rag_detail._infer_missing_fields", new_callable=AsyncMock)
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_passes_eligibility_fields_to_infer(
        self, mock_get_detail, mock_infer
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_infer.return_value = []

        await rag_detail_node(_make_state())

        call_kwargs = mock_infer.call_args.kwargs
        assert call_kwargs["tgtr_dtl_cn"] == _DUMMY_DETAIL["tgtr_dtl_cn"]
        assert call_kwargs["slct_crit_cn"] == _DUMMY_DETAIL["slct_crit_cn"]
        assert call_kwargs["trgter_indvdl"] == _DUMMY_DETAIL["trgter_indvdl"]


class TestInferMissingFields:
    """_infer_missing_fields 단위 테스트 — get_llm만 mock."""

    @patch("agents.rag_detail.get_llm")
    async def test_returns_fields_not_in_profile(self, mock_get_llm):
        from agents.rag_detail import _infer_missing_fields, _RequiredFields

        extractor = AsyncMock()
        extractor.ainvoke = AsyncMock(
            return_value=_RequiredFields(
                regular_fields=["housing_type", "is_veteran"], extra_fields=[]
            )
        )
        mock_get_llm.return_value.with_structured_output.return_value = extractor

        profile = UserProfile(age=65, income_level=IncomeLevel.BASIC, disability=False)
        result = await _infer_missing_fields(
            profile, "대상자", "선정기준", ["저소득층"]
        )

        assert "housing_type" in result
        assert "is_veteran" in result

    @patch("agents.rag_detail.get_llm")
    async def test_skips_already_filled_fields(self, mock_get_llm):
        from agents.rag_detail import _infer_missing_fields, _RequiredFields

        extractor = AsyncMock()
        extractor.ainvoke = AsyncMock(
            return_value=_RequiredFields(
                regular_fields=["housing_type", "is_veteran"], extra_fields=[]
            )
        )
        mock_get_llm.return_value.with_structured_output.return_value = extractor

        profile = UserProfile(
            age=65,
            income_level=IncomeLevel.BASIC,
            disability=False,
            housing_type="아파트",  # already filled
        )
        result = await _infer_missing_fields(
            profile, "대상자", "선정기준", ["저소득층"]
        )

        assert "housing_type" not in result
        assert "is_veteran" in result

    @patch("agents.rag_detail.get_llm")
    async def test_extra_fields_prefixed_correctly(self, mock_get_llm):
        from agents.rag_detail import _infer_missing_fields, _RequiredFields

        extractor = AsyncMock()
        extractor.ainvoke = AsyncMock(
            return_value=_RequiredFields(
                regular_fields=[], extra_fields=["deposit_amount"]
            )
        )
        mock_get_llm.return_value.with_structured_output.return_value = extractor

        profile = UserProfile(age=65, income_level=IncomeLevel.BASIC, disability=False)
        result = await _infer_missing_fields(profile, "대상자", "선정기준", [])

        assert "extra:deposit_amount" in result

    @patch("agents.rag_detail.get_llm")
    async def test_llm_failure_returns_empty_list(self, mock_get_llm):
        from agents.rag_detail import _infer_missing_fields

        extractor = AsyncMock()
        extractor.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
        mock_get_llm.return_value.with_structured_output.return_value = extractor

        profile = UserProfile(age=65, income_level=IncomeLevel.BASIC, disability=False)
        result = await _infer_missing_fields(profile, "대상자", "선정기준", [])

        assert result == []
