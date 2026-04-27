"""1단계 인터뷰 에이전트 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agents.initial_interview import (
    _extract_profile,
    _generate_question,
    _ProfileExtraction,
    initial_interview_node,
)
from graph.state import DisabilitySeverity, UserProfile


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
    }
    state.update(overrides)
    return state


class TestInitialInterviewNodeBasic:
    async def test_returns_empty_when_no_missing_fields(self):
        state = _base_state(initial_missing_fields=[])
        result = await initial_interview_node(state)
        assert result == {}

    @patch("agents.initial_interview.interrupt", return_value="저는 40살이에요")
    @patch("agents.initial_interview.load_prompt", return_value="system prompt")
    @patch("agents.initial_interview.get_llm")
    async def test_interrupts_with_question(
        self, mock_get_llm, mock_load_prompt, mock_interrupt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_ProfileExtraction(age=40)
        )

        state = _base_state(initial_missing_fields=["age"])
        await initial_interview_node(state)

        mock_interrupt.assert_called_once()
        call_args = mock_interrupt.call_args[0][0]
        assert "question" in call_args
        assert "missing_fields" in call_args
        assert "age" in call_args["missing_fields"]

    @patch("agents.initial_interview.interrupt", return_value="저는 40살이에요")
    @patch("agents.initial_interview.load_prompt", return_value="system prompt")
    @patch("agents.initial_interview.get_llm")
    async def test_messages_contain_ai_and_human(
        self, mock_get_llm, mock_load_prompt, mock_interrupt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_ProfileExtraction(age=40)
        )

        state = _base_state(initial_missing_fields=["age"])
        result = await initial_interview_node(state)

        msgs = result["messages"]
        assert any(isinstance(m, AIMessage) for m in msgs)
        assert any(isinstance(m, HumanMessage) for m in msgs)
        assert any(
            m.content == "저는 40살이에요" for m in msgs if isinstance(m, HumanMessage)
        )


class TestInitialInterviewNodeExtraction:
    @patch("agents.initial_interview.interrupt", return_value="서울, 40살")
    @patch("agents.initial_interview.load_prompt", return_value="system prompt")
    @patch("agents.initial_interview.get_llm")
    async def test_extracted_fields_removed_from_missing(
        self, mock_get_llm, mock_load_prompt, mock_interrupt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_ProfileExtraction(age=40, region="서울")
        )

        state = _base_state(initial_missing_fields=["age", "region", "income_level"])
        result = await initial_interview_node(state)

        assert "age" not in result["initial_missing_fields"]
        assert "region" not in result["initial_missing_fields"]
        assert "income_level" in result["initial_missing_fields"]

    @patch("agents.initial_interview.interrupt", return_value="서울, 40살")
    @patch("agents.initial_interview.load_prompt", return_value="system prompt")
    @patch("agents.initial_interview.get_llm")
    async def test_profile_updated_with_extracted_fields(
        self, mock_get_llm, mock_load_prompt, mock_interrupt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_ProfileExtraction(age=40, region="서울")
        )

        state = _base_state(initial_missing_fields=["age", "region"])
        result = await initial_interview_node(state)

        profile = result["user_profile"]
        assert profile.age == 40
        assert profile.region == "서울"


class TestDisabilitySeverityHandling:
    @patch("agents.initial_interview.interrupt", return_value="장애가 있습니다")
    @patch("agents.initial_interview.load_prompt", return_value="system prompt")
    @patch("agents.initial_interview.get_llm")
    async def test_disability_true_adds_severity_to_missing(
        self, mock_get_llm, mock_load_prompt, mock_interrupt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_ProfileExtraction(disability=True)
        )

        state = _base_state(initial_missing_fields=["disability"])
        result = await initial_interview_node(state)

        assert "disability_severity" in result["initial_missing_fields"]

    @patch("agents.initial_interview.interrupt", return_value="장애 없습니다")
    @patch("agents.initial_interview.load_prompt", return_value="system prompt")
    @patch("agents.initial_interview.get_llm")
    async def test_disability_false_no_severity_in_missing(
        self, mock_get_llm, mock_load_prompt, mock_interrupt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_ProfileExtraction(disability=False)
        )

        state = _base_state(
            initial_missing_fields=["disability", "disability_severity"]
        )
        result = await initial_interview_node(state)

        assert "disability_severity" not in result["initial_missing_fields"]

    @patch("agents.initial_interview.interrupt", return_value="중증 장애입니다")
    @patch("agents.initial_interview.load_prompt", return_value="system prompt")
    @patch("agents.initial_interview.get_llm")
    async def test_disability_severity_collected_removes_from_missing(
        self, mock_get_llm, mock_load_prompt, mock_interrupt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_ProfileExtraction(
                disability=True,
                disability_severity=DisabilitySeverity.SEVERE,
            )
        )

        state = _base_state(initial_missing_fields=["disability_severity"])
        result = await initial_interview_node(state)

        assert "disability_severity" not in result["initial_missing_fields"]
        assert result["user_profile"].disability_severity == DisabilitySeverity.SEVERE


class TestStructuredOutputRetry:
    async def test_all_fields_remain_on_max_retry_failure(self):
        profile = UserProfile()
        missing = ["age", "region"]

        with patch("agents.initial_interview.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_extractor = AsyncMock()
            mock_extractor.ainvoke = AsyncMock(side_effect=Exception("파싱 실패"))
            mock_llm.with_structured_output.return_value = mock_extractor
            mock_get_llm.return_value = mock_llm

            new_profile, new_missing = await _extract_profile(
                profile, missing, "내 답변", []
            )

        assert new_profile == profile
        assert new_missing == missing

    async def test_retries_exactly_max_retry_plus_one_times(self):
        profile = UserProfile()

        with patch("agents.initial_interview.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_extractor = AsyncMock()
            mock_extractor.ainvoke = AsyncMock(side_effect=Exception("파싱 실패"))
            mock_llm.with_structured_output.return_value = mock_extractor
            mock_get_llm.return_value = mock_llm

            await _extract_profile(profile, ["age"], "내 답변", [])

            assert mock_extractor.ainvoke.call_count == 3  # 1 + _MAX_RETRY(2)

    async def test_succeeds_on_second_attempt(self):
        profile = UserProfile()
        missing = ["age"]

        with patch("agents.initial_interview.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_extractor = AsyncMock()
            mock_extractor.ainvoke = AsyncMock(
                side_effect=[Exception("1차 실패"), _ProfileExtraction(age=55)]
            )
            mock_llm.with_structured_output.return_value = mock_extractor
            mock_get_llm.return_value = mock_llm

            new_profile, new_missing = await _extract_profile(
                profile, missing, "55살", []
            )

        assert new_profile.age == 55
        assert "age" not in new_missing


class TestGenerateQuestion:
    @patch("agents.initial_interview.load_prompt", return_value="system prompt")
    @patch("agents.initial_interview.get_llm")
    async def test_returns_llm_content(self, mock_get_llm, mock_load_prompt, mock_llm):
        mock_get_llm.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="나이가 어떻게 되세요?")
        )

        question = await _generate_question(UserProfile(), ["age"], [])

        assert question == "나이가 어떻게 되세요?"

    @patch("agents.initial_interview.load_prompt", return_value="system prompt")
    @patch("agents.initial_interview.get_llm")
    async def test_history_included_in_messages(
        self, mock_get_llm, mock_load_prompt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="질문"))

        history = [HumanMessage(content="안녕하세요"), AIMessage(content="안녕하세요!")]
        await _generate_question(UserProfile(), ["age"], history)

        call_messages = mock_llm.ainvoke.call_args[0][0]
        assert any(m.content == "안녕하세요" for m in call_messages)
