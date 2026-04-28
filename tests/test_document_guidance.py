"""서류 안내 노드 테스트."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from agents.document_guidance import document_guidance_node
from graph.state import EmploymentStatus, IncomeLevel, UserProfile, WelfareCandidate


def _make_selected(**kwargs) -> WelfareCandidate:
    defaults = dict(
        serv_id="WLF-001",
        serv_nm="기초생활수급자 생계급여",
        serv_dgst="생활이 어려운 기초생활수급자에게 급여를 지급합니다.",
        department="보건복지부",
        score=0.95,
        priority=1,
        required_documents=["신분증 사본", "사회보장급여 신청서", "소득 증빙 서류"],
        detail_fetched=True,
    )
    defaults.update(kwargs)
    return WelfareCandidate(**defaults)


def _make_state(**kwargs) -> dict:
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
    return defaults


class TestDocumentGuidanceNode:
    @patch(
        "agents.document_guidance.load_prompt",
        return_value="{serv_nm}\n{required_documents}\n{user_info}",
    )
    @patch("agents.document_guidance.get_llm")
    async def test_returns_document_guidance_string(
        self, mock_get_llm, mock_load_prompt
    ):
        expected = "1. 신분증 사본: 주민센터에서 발급"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content=expected)
        mock_get_llm.return_value = mock_llm

        result = await document_guidance_node(_make_state())

        assert result["document_guidance"] == expected

    @patch(
        "agents.document_guidance.load_prompt",
        return_value="{serv_nm}\n{required_documents}\n{user_info}",
    )
    @patch("agents.document_guidance.get_llm")
    async def test_returns_ai_message(self, mock_get_llm, mock_load_prompt):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="서류 안내 내용")
        mock_get_llm.return_value = mock_llm

        result = await document_guidance_node(_make_state())

        assert isinstance(result["messages"][0], AIMessage)
        assert result["messages"][0].content == "서류 안내 내용"

    @patch("agents.document_guidance.get_llm")
    async def test_empty_required_documents_returns_fallback(self, mock_get_llm):
        state = _make_state(selected_service=_make_selected(required_documents=[]))

        result = await document_guidance_node(state)

        assert "직접 문의" in result["document_guidance"]
        assert isinstance(result["messages"][0], AIMessage)
        mock_get_llm.assert_not_called()

    async def test_fallback_message_contains_service_name(self):
        state = _make_state(selected_service=_make_selected(required_documents=[]))

        result = await document_guidance_node(state)

        assert "기초생활수급자 생계급여" in result["document_guidance"]

    @patch(
        "agents.document_guidance.load_prompt",
        return_value="{serv_nm}\n{required_documents}\n{user_info}",
    )
    @patch("agents.document_guidance.get_llm")
    async def test_llm_called_with_service_name(self, mock_get_llm, mock_load_prompt):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="결과")
        mock_get_llm.return_value = mock_llm

        await document_guidance_node(_make_state())

        call_args = mock_llm.invoke.call_args[0][0]
        assert "기초생활수급자 생계급여" in call_args

    @patch(
        "agents.document_guidance.load_prompt",
        return_value="{serv_nm}\n{required_documents}\n{user_info}",
    )
    @patch("agents.document_guidance.get_llm")
    async def test_llm_called_with_user_info(self, mock_get_llm, mock_load_prompt):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="결과")
        mock_get_llm.return_value = mock_llm

        await document_guidance_node(_make_state())

        call_args = mock_llm.invoke.call_args[0][0]
        assert "65세" in call_args
        assert "서울" in call_args
