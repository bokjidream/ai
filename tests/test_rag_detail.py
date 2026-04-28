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
}


class TestRagDetailNode:
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_updates_selected_service_on_success(self, mock_get_detail):
        mock_get_detail.return_value = _DUMMY_DETAIL

        result = await rag_detail_node(_make_state())

        updated = result["selected_service"]
        assert updated.detail_fetched is True
        assert updated.required_documents == ["사회보장급여 신청서", "신분증"]
        assert updated.application_fields == ["신청인 성명", "주소"]
        assert updated.application_url == "https://www.bokjiro.go.kr"

    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_preserves_existing_fields_on_success(self, mock_get_detail):
        mock_get_detail.return_value = _DUMMY_DETAIL

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
    async def test_missing_optional_fields_default_to_empty(self, mock_get_detail):
        mock_get_detail.return_value = {
            "serv_id": "WLF-001",
            "serv_nm": "기초생활수급자 생계급여",
        }

        result = await rag_detail_node(_make_state())

        updated = result["selected_service"]
        assert updated.required_documents == []
        assert updated.application_fields == []
        assert updated.application_url is None
        assert updated.detail_fetched is True
