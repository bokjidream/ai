"""서비스 선택 HitL 노드 테스트."""

from unittest.mock import patch

from langchain_core.messages import AIMessage

from agents.service_select import service_select_node
from graph.state import (
    AgentState,
    EmploymentStatus,
    IncomeLevel,
    UserProfile,
    WelfareCandidate,
)


def _make_candidates() -> list[WelfareCandidate]:
    return [
        WelfareCandidate(
            serv_id="WLF-001",
            serv_nm="기초생활수급자 생계급여",
            serv_dgst="생활이 어려운 기초생활수급자에게 급여를 지급합니다.",
            department="보건복지부",
            score=0.95,
            priority=1,
            eligibility_reason="기초수급자 해당",
        ),
        WelfareCandidate(
            serv_id="WLF-002",
            serv_nm="노인 돌봄 서비스",
            serv_dgst="혼자 생활하기 어려운 노인에게 돌봄 서비스를 제공합니다.",
            department="보건복지부",
            score=0.80,
            priority=2,
            eligibility_reason="65세 이상 해당",
        ),
    ]


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
        "welfare_candidates": _make_candidates(),
        "selected_service": None,
        "detail_missing_fields": [],
        "document_guidance": "",
        "application_guide": "",
        "final_report": "",
    }
    defaults.update(kwargs)
    return defaults  # type: ignore[return-value]


class TestServiceSelectNode:
    @patch("agents.service_select.interrupt", return_value="1")
    async def test_valid_selection_sets_selected_service(self, mock_interrupt):
        result = await service_select_node(_make_state())

        assert result["selected_service"].serv_id == "WLF-001"
        assert result["selected_service"].serv_nm == "기초생활수급자 생계급여"

    @patch("agents.service_select.interrupt", return_value="2")
    async def test_selects_second_candidate(self, mock_interrupt):
        result = await service_select_node(_make_state())

        assert result["selected_service"].serv_id == "WLF-002"

    @patch("agents.service_select.interrupt", return_value="1")
    async def test_returns_ai_message_on_selection(self, mock_interrupt):
        result = await service_select_node(_make_state())

        assert isinstance(result["messages"][0], AIMessage)
        assert "기초생활수급자 생계급여" in result["messages"][0].content

    @patch("agents.service_select.interrupt", side_effect=["잘못된입력", "0", "1"])
    async def test_invalid_input_reinterrupts(self, mock_interrupt):
        result = await service_select_node(_make_state())

        # 잘못된 입력 2회 후 "1" 선택
        assert mock_interrupt.call_count == 3
        assert result["selected_service"].serv_id == "WLF-001"

    @patch("agents.service_select.interrupt", side_effect=["99", "1"])
    async def test_out_of_range_input_reinterrupts(self, mock_interrupt):
        result = await service_select_node(_make_state())

        assert mock_interrupt.call_count == 2
        assert result["selected_service"].serv_id == "WLF-001"

    @patch("agents.service_select.interrupt", side_effect=["잘못된입력", "1"])
    async def test_error_message_included_on_reinterrupt(self, mock_interrupt):
        await service_select_node(_make_state())

        # 두 번째 interrupt 호출 시 error 포함 확인
        second_call_kwargs = mock_interrupt.call_args_list[1].kwargs
        assert second_call_kwargs["value"]["error"] is not None
