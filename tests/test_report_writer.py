"""최종 보고서 에이전트 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from agents.report_writer import report_writer_node
from graph.state import (
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
        required_documents=["신분증", "사회보장급여 신청서"],
        application_method="읍면동 주민센터 방문 신청, 사회보장급여 신청서 제출",
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
        "final_report": "",
    }
    defaults.update(kwargs)
    return defaults  # type: ignore[return-value]


class TestReportWriterNode:
    @patch("agents.report_writer.get_llm")
    async def test_returns_final_report_string(self, mock_get_llm):
        expected = "## 기초생활수급자 생계급여 신청 안내\n\n### 준비 서류\n..."
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=expected))
        mock_get_llm.return_value = mock_llm

        result = await report_writer_node(_make_state())

        assert result["final_report"] == expected

    @patch("agents.report_writer.get_llm")
    async def test_returns_ai_message(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="보고서 내용"))
        mock_get_llm.return_value = mock_llm

        result = await report_writer_node(_make_state())

        assert isinstance(result["messages"][0], AIMessage)
        assert result["messages"][0].content == "보고서 내용"

    @patch("agents.report_writer.get_llm")
    async def test_no_selected_service_returns_fallback(self, mock_get_llm):
        state = _make_state(selected_service=None)

        result = await report_writer_node(state)

        assert "선택된 서비스가 없습니다" in result["final_report"]
        assert isinstance(result["messages"][0], AIMessage)
        mock_get_llm.assert_not_called()

    @patch("agents.report_writer.get_llm")
    async def test_llm_called_with_service_name(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="결과"))
        mock_get_llm.return_value = mock_llm

        await report_writer_node(_make_state())

        call_args = mock_llm.ainvoke.call_args[0][0]
        assert "기초생활수급자 생계급여" in call_args

    @patch("agents.report_writer.get_llm")
    async def test_llm_called_with_raw_documents(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="결과"))
        mock_get_llm.return_value = mock_llm

        state = _make_state(
            selected_service=_make_selected(
                required_documents=["신분증", "사회보장급여 신청서"],
                application_method="읍면동 주민센터 방문 신청",
            )
        )
        await report_writer_node(state)

        call_args = mock_llm.ainvoke.call_args[0][0]
        assert "신분증" in call_args
        assert "읍면동 주민센터 방문 신청" in call_args
