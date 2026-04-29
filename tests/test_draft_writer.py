"""신청서 작성 가이드 노드 테스트."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from agents.draft_writer import _format_user_info, draft_writer_node
from graph.state import (
    AgentState,
    EmploymentStatus,
    IncomeLevel,
    UserProfile,
    WelfareCandidate,
)


def _make_selected(**kwargs) -> WelfareCandidate:
    defaults = dict(
        serv_id="WLF-001",
        serv_nm="기초생활수급자 생계급여",
        serv_dgst="생활이 어려운 기초생활수급자에게 급여를 지급합니다.",
        department="보건복지부",
        score=0.95,
        priority=1,
        application_fields=["신청인 성명", "생년월일", "주소", "소득 수준"],
        required_documents=["신분증", "사회보장급여 신청서"],
        detail_fetched=True,
    )
    defaults.update(kwargs)
    return WelfareCandidate(**defaults)


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


class TestFormatUserInfo:
    def test_includes_filled_fields(self):
        profile = UserProfile(age=65, region="서울", income_level=IncomeLevel.BASIC)
        result = _format_user_info(profile)
        assert "65세" in result
        assert "서울" in result
        assert "기초생활수급자" in result

    def test_excludes_none_fields(self):
        profile = UserProfile(age=40)
        result = _format_user_info(profile)
        assert "지역" not in result
        assert "소득 수준" not in result

    def test_empty_profile_returns_fallback(self):
        profile = UserProfile()
        result = _format_user_info(profile)
        assert "수집된 사용자 정보 없음" in result

    def test_includes_extra_fields(self):
        profile = UserProfile(extra_fields={"복지카드번호": "12345"})
        result = _format_user_info(profile)
        assert "복지카드번호" in result
        assert "12345" in result


class TestDraftWriterNode:
    @patch("agents.draft_writer.get_llm")
    async def test_returns_application_guide_string(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="1. 신청인 성명: 홍길동")
        mock_get_llm.return_value = mock_llm

        result = await draft_writer_node(_make_state())

        assert result["application_guide"] == "1. 신청인 성명: 홍길동"

    @patch("agents.draft_writer.get_llm")
    async def test_returns_ai_message(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="가이드 내용")
        mock_get_llm.return_value = mock_llm

        result = await draft_writer_node(_make_state())

        assert isinstance(result["messages"][0], AIMessage)
        assert result["messages"][0].content == "가이드 내용"

    @patch("agents.draft_writer.get_llm")
    async def test_empty_application_fields_returns_fallback(self, mock_get_llm):
        state = _make_state(selected_service=_make_selected(application_fields=[]))

        result = await draft_writer_node(state)

        assert "직접 문의" in result["application_guide"]
        assert isinstance(result["messages"][0], AIMessage)
        mock_get_llm.assert_not_called()

    @patch("agents.draft_writer.get_llm")
    async def test_llm_called_with_service_name(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="결과")
        mock_get_llm.return_value = mock_llm

        await draft_writer_node(_make_state())

        call_args = mock_llm.invoke.call_args[0][0]
        assert "기초생활수급자 생계급여" in call_args

    @patch("agents.draft_writer.get_llm")
    async def test_llm_called_with_user_info(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="결과")
        mock_get_llm.return_value = mock_llm

        await draft_writer_node(_make_state())

        call_args = mock_llm.invoke.call_args[0][0]
        assert "65세" in call_args
        assert "서울" in call_args
