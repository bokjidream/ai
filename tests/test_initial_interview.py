"""1단계 인터뷰 에이전트 테스트."""

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agents.initial_interview import (
    _apply_value,
    _update_missing,
    initial_interview_node,
)
from graph.state import DisabilitySeverity, MaritalStatus, UserProfile


def _base_state(**overrides) -> dict:
    state = {
        "messages": [],
        "user_profile": UserProfile(),
        "initial_missing_fields": [
            "age",
            "region",
            "income_level",
            "disability",
            "employment_status",
        ],
        "welfare_candidates": [],
        "selected_service": None,
        "detail_missing_fields": [],
        "document_guidance": "",
        "application_guide": "",
        "final_report": "",
        "interview_current_field": None,
        "interview_last_question": "",
        "interview_last_answer": "",
    }
    state.update(overrides)
    return state


class TestInitialInterviewNodeBasic:
    async def test_returns_empty_when_no_missing_fields(self):
        state = _base_state(initial_missing_fields=[])
        result = await initial_interview_node(state)
        assert result == {}

    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="저는 40살이에요")
    async def test_first_call_uses_reask_false(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "나이가 어떻게 되세요?"
        mock_extract.return_value = {
            "exist": True,
            "value": 40,
            "re_ask": False,
            "reasoning": "",
        }

        state = _base_state(initial_missing_fields=["age"])
        await initial_interview_node(state)

        mock_ask.assert_called_once_with(
            field="age", re_ask=False, pre_assistant_message="", pre_user_message=""
        )

    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="저는 40살이에요")
    async def test_interrupts_with_question_and_field(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "나이가 어떻게 되세요?"
        mock_extract.return_value = {
            "exist": True,
            "value": 40,
            "re_ask": False,
            "reasoning": "",
        }

        state = _base_state(initial_missing_fields=["age"])
        await initial_interview_node(state)

        call_args = mock_interrupt.call_args[0][0]
        assert call_args["question"] == "나이가 어떻게 되세요?"
        assert call_args["field"] == "age"

    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="저는 40살이에요")
    async def test_messages_contain_ai_and_human(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "나이가 어떻게 되세요?"
        mock_extract.return_value = {
            "exist": True,
            "value": 40,
            "re_ask": False,
            "reasoning": "",
        }

        state = _base_state(initial_missing_fields=["age"])
        result = await initial_interview_node(state)

        msgs = result["messages"]
        assert any(isinstance(m, AIMessage) for m in msgs)
        assert any(isinstance(m, HumanMessage) for m in msgs)
        assert any(
            m.content == "저는 40살이에요" for m in msgs if isinstance(m, HumanMessage)
        )


class TestInitialInterviewNodeExtraction:
    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="40살이에요")
    async def test_extracted_field_removed_from_missing(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "나이가 어떻게 되세요?"
        mock_extract.return_value = {
            "exist": True,
            "value": 40,
            "re_ask": False,
            "reasoning": "",
        }

        state = _base_state(initial_missing_fields=["age", "region", "income_level"])
        result = await initial_interview_node(state)

        assert "age" not in result["initial_missing_fields"]
        assert "region" in result["initial_missing_fields"]
        assert "income_level" in result["initial_missing_fields"]

    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="40살이에요")
    async def test_profile_updated_with_extracted_value(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "나이가 어떻게 되세요?"
        mock_extract.return_value = {
            "exist": True,
            "value": 40,
            "re_ask": False,
            "reasoning": "",
        }

        state = _base_state(initial_missing_fields=["age"])
        result = await initial_interview_node(state)

        assert result["user_profile"].age == 40

    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="잘 모르겠어요")
    async def test_extraction_failure_keeps_missing_and_sets_current_field(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "나이가 어떻게 되세요?"
        mock_extract.return_value = {
            "exist": False,
            "value": None,
            "re_ask": True,
            "reasoning": "불명확",
        }

        state = _base_state(initial_missing_fields=["age", "region"])
        result = await initial_interview_node(state)

        assert "age" in result["initial_missing_fields"]
        assert result["interview_current_field"] == "age"
        assert result["interview_last_question"] == "나이가 어떻게 되세요?"
        assert result["interview_last_answer"] == "잘 모르겠어요"

    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="스물여섯이요")
    async def test_reask_entry_uses_reask_true_with_pre_messages(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "조금 더 구체적으로 말씀해주실 수 있나요?"
        mock_extract.return_value = {
            "exist": True,
            "value": 26,
            "re_ask": False,
            "reasoning": "",
        }

        state = _base_state(
            initial_missing_fields=["age"],
            interview_current_field="age",
            interview_last_question="나이가 어떻게 되세요?",
            interview_last_answer="잘 모르겠어요",
        )
        await initial_interview_node(state)

        mock_ask.assert_called_once_with(
            field="age",
            re_ask=True,
            pre_assistant_message="나이가 어떻게 되세요?",
            pre_user_message="잘 모르겠어요",
        )

    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="26살이요")
    async def test_successful_reask_clears_tracking_fields(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "나이를 숫자로 말씀해주세요."
        mock_extract.return_value = {
            "exist": True,
            "value": 26,
            "re_ask": False,
            "reasoning": "",
        }

        state = _base_state(
            initial_missing_fields=["age"],
            interview_current_field="age",
            interview_last_question="나이가 어떻게 되세요?",
            interview_last_answer="잘 모르겠어요",
        )
        result = await initial_interview_node(state)

        assert result["interview_current_field"] is None
        assert result["interview_last_question"] == ""
        assert result["interview_last_answer"] == ""


class TestDisabilitySeverityHandling:
    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="장애가 있습니다")
    async def test_disability_true_adds_severity_to_missing(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "장애가 있으신가요?"
        mock_extract.return_value = {
            "exist": True,
            "value": True,
            "re_ask": False,
            "reasoning": "",
        }

        state = _base_state(initial_missing_fields=["disability"])
        result = await initial_interview_node(state)

        assert "disability_severity" in result["initial_missing_fields"]

    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="장애 없습니다")
    async def test_disability_false_removes_severity_from_missing(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "장애가 있으신가요?"
        mock_extract.return_value = {
            "exist": True,
            "value": False,
            "re_ask": False,
            "reasoning": "",
        }

        state = _base_state(
            initial_missing_fields=["disability", "disability_severity"]
        )
        result = await initial_interview_node(state)

        assert "disability_severity" not in result["initial_missing_fields"]

    @patch("agents.initial_interview.hwnv_client.extract_value", new_callable=AsyncMock)
    @patch("agents.initial_interview.hwnv_client.ask_question", new_callable=AsyncMock)
    @patch("agents.initial_interview.interrupt", return_value="중증입니다")
    async def test_disability_severity_collected_removes_from_missing(
        self, mock_interrupt, mock_ask, mock_extract
    ):
        mock_ask.return_value = "장애 정도가 어떻게 되세요?"
        mock_extract.return_value = {
            "exist": True,
            "value": "중증",
            "re_ask": False,
            "reasoning": "",
        }

        profile = UserProfile(disability=True)
        state = _base_state(
            user_profile=profile,
            initial_missing_fields=["disability_severity"],
        )
        result = await initial_interview_node(state)

        assert "disability_severity" not in result["initial_missing_fields"]
        assert result["user_profile"].disability_severity == DisabilitySeverity.SEVERE


class TestApplyValue:
    def test_age_converts_to_int(self):
        profile = UserProfile()
        result = _apply_value(profile, "age", "26")
        assert result.age == 26
        assert isinstance(result.age, int)

    def test_marital_status_converts_to_enum(self):
        profile = UserProfile()
        result = _apply_value(profile, "marital_status", "미혼")
        assert result.marital_status == MaritalStatus.SINGLE

    def test_disability_converts_to_bool(self):
        profile = UserProfile()
        result = _apply_value(profile, "disability", True)
        assert result.disability is True


class TestUpdateMissing:
    def test_removes_collected_field(self):
        profile = UserProfile()
        result = _update_missing("age", profile, ["age", "region"])
        assert "age" not in result
        assert "region" in result

    def test_disability_false_removes_severity(self):
        profile = UserProfile(disability=False)
        result = _update_missing(
            "disability", profile, ["disability", "disability_severity"]
        )
        assert "disability_severity" not in result

    def test_disability_true_adds_severity_if_absent(self):
        profile = UserProfile(disability=True)
        result = _update_missing("disability", profile, ["disability"])
        assert "disability_severity" in result

    def test_disability_true_no_duplicate_severity(self):
        profile = UserProfile(disability=True)
        result = _update_missing(
            "disability", profile, ["disability", "disability_severity"]
        )
        assert result.count("disability_severity") == 1
