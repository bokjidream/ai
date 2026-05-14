"""2단계 인터뷰 에이전트 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agents.detail_interview import (
    _DetailExtraction,
    _extract_profile,
    _generate_question,
    detail_interview_node,
)
from graph.state import IncomeLevel, UserProfile, WelfareCandidate


def _base_state(**overrides) -> dict:
    state = {
        "messages": [],
        "user_profile": UserProfile(
            age=40,
            income_level=IncomeLevel.BASIC,
            disability=True,
            employment_status="실업",
            region="서울",
        ),
        "initial_missing_fields": [],
        "welfare_candidates": [],
        "selected_service": WelfareCandidate(
            serv_id="SVC001",
            serv_nm="장애인 활동지원",
            serv_dgst="장애인의 자립생활을 지원하는 서비스입니다.",
        ),
        "detail_missing_fields": ["disability_type", "housing_type"],
        "document_guidance": "",
        "application_guide": "",
        "final_report": "",
    }
    state.update(overrides)
    return state


class TestDetailInterviewNodeBasic:
    async def test_returns_empty_when_no_missing_fields(self):
        state = _base_state(detail_missing_fields=[])
        result = await detail_interview_node(state)
        assert result == {}

    async def test_interrupts_with_question(self, mock_llm):
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_DetailExtraction(disability_type="지체장애")
        )
        with patch("agents.detail_interview.get_llm", return_value=mock_llm):
            with patch(
                "agents.detail_interview.load_prompt", return_value="system prompt"
            ):
                with patch(
                    "agents.detail_interview.interrupt",
                    return_value="지체장애입니다",
                ) as mock_interrupt:
                    state = _base_state(detail_missing_fields=["disability_type"])
                    await detail_interview_node(state)

        mock_interrupt.assert_called_once()
        call_args = mock_interrupt.call_args[0][0]
        assert "question" in call_args
        assert "missing_fields" in call_args
        assert "disability_type" in call_args["missing_fields"]

    async def test_messages_contain_ai_and_human(self, mock_llm):
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_DetailExtraction(disability_type="지체장애")
        )
        with patch("agents.detail_interview.get_llm", return_value=mock_llm):
            with patch(
                "agents.detail_interview.load_prompt", return_value="system prompt"
            ):
                with patch(
                    "agents.detail_interview.interrupt",
                    return_value="지체장애입니다",
                ):
                    state = _base_state(detail_missing_fields=["disability_type"])
                    result = await detail_interview_node(state)

        msgs = result["messages"]
        assert any(isinstance(m, AIMessage) for m in msgs)
        assert any(isinstance(m, HumanMessage) for m in msgs)
        assert any(
            m.content == "지체장애입니다" for m in msgs if isinstance(m, HumanMessage)
        )


class TestDetailInterviewNodeExtraction:
    async def test_extracted_fields_removed_from_missing(self, mock_llm):
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_DetailExtraction(
                disability_type="지체장애", housing_type="자가"
            )
        )
        with patch("agents.detail_interview.get_llm", return_value=mock_llm):
            with patch(
                "agents.detail_interview.load_prompt", return_value="system prompt"
            ):
                with patch(
                    "agents.detail_interview.interrupt", return_value="지체장애, 자가"
                ):
                    state = _base_state(
                        detail_missing_fields=[
                            "disability_type",
                            "housing_type",
                            "is_veteran",
                        ]
                    )
                    result = await detail_interview_node(state)

        assert "disability_type" not in result["detail_missing_fields"]
        assert "housing_type" not in result["detail_missing_fields"]
        assert "is_veteran" in result["detail_missing_fields"]

    async def test_profile_updated_with_extracted_fields(self, mock_llm):
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_DetailExtraction(
                disability_type="지체장애", housing_type="자가"
            )
        )
        with patch("agents.detail_interview.get_llm", return_value=mock_llm):
            with patch(
                "agents.detail_interview.load_prompt", return_value="system prompt"
            ):
                with patch(
                    "agents.detail_interview.interrupt", return_value="지체장애, 자가"
                ):
                    state = _base_state(
                        detail_missing_fields=["disability_type", "housing_type"]
                    )
                    result = await detail_interview_node(state)

        profile = result["user_profile"]
        assert profile.disability_type == "지체장애"
        assert profile.housing_type == "자가"


class TestExtraFieldsHandling:
    async def test_extra_field_stored_in_extra_fields(self, mock_llm):
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_DetailExtraction(extra_fields={"참전유공자": True})
        )
        with patch("agents.detail_interview.get_llm", return_value=mock_llm):
            with patch(
                "agents.detail_interview.load_prompt", return_value="system prompt"
            ):
                with patch(
                    "agents.detail_interview.interrupt",
                    return_value="참전용사입니다",
                ):
                    state = _base_state(detail_missing_fields=["extra:참전유공자"])
                    result = await detail_interview_node(state)

        assert result["user_profile"].extra_fields.get("참전유공자") is True

    async def test_extra_field_removed_from_missing_after_extraction(self, mock_llm):
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_DetailExtraction(extra_fields={"참전유공자": True})
        )
        with patch("agents.detail_interview.get_llm", return_value=mock_llm):
            with patch(
                "agents.detail_interview.load_prompt", return_value="system prompt"
            ):
                with patch(
                    "agents.detail_interview.interrupt",
                    return_value="참전용사입니다",
                ):
                    state = _base_state(detail_missing_fields=["extra:참전유공자"])
                    result = await detail_interview_node(state)

        assert "extra:참전유공자" not in result["detail_missing_fields"]

    async def test_extra_field_remains_in_missing_when_not_extracted(self, mock_llm):
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_DetailExtraction()
        )
        with patch("agents.detail_interview.get_llm", return_value=mock_llm):
            with patch(
                "agents.detail_interview.load_prompt", return_value="system prompt"
            ):
                with patch("agents.detail_interview.interrupt", return_value="모름"):
                    state = _base_state(detail_missing_fields=["extra:참전유공자"])
                    result = await detail_interview_node(state)

        assert "extra:참전유공자" in result["detail_missing_fields"]

    async def test_existing_extra_fields_preserved_on_update(self):
        profile = UserProfile(extra_fields={"기존키": "기존값"})
        missing = ["extra:새키"]

        with patch("agents.detail_interview.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
                return_value=_DetailExtraction(extra_fields={"새키": "새값"})
            )
            mock_get_llm.return_value = mock_llm

            new_profile, _, _ = await _extract_profile(profile, missing, "새값", [])

        assert new_profile.extra_fields["기존키"] == "기존값"
        assert new_profile.extra_fields["새키"] == "새값"


class TestStructuredOutputRetry:
    async def test_all_fields_remain_on_max_retry_failure(self):
        profile = UserProfile()
        missing = ["disability_type", "housing_type"]

        with patch("agents.detail_interview.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_extractor = AsyncMock()
            mock_extractor.ainvoke = AsyncMock(side_effect=Exception("파싱 실패"))
            mock_llm.with_structured_output.return_value = mock_extractor
            mock_get_llm.return_value = mock_llm

            new_profile, new_missing, failed = await _extract_profile(
                profile, missing, "내 답변", []
            )

        assert new_profile == profile
        assert new_missing == missing
        assert failed is True

    async def test_retries_exactly_max_retry_plus_one_times(self):
        profile = UserProfile()

        with patch("agents.detail_interview.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_extractor = AsyncMock()
            mock_extractor.ainvoke = AsyncMock(side_effect=Exception("파싱 실패"))
            mock_llm.with_structured_output.return_value = mock_extractor
            mock_get_llm.return_value = mock_llm

            await _extract_profile(profile, ["disability_type"], "내 답변", [])

            assert mock_extractor.ainvoke.call_count == 3  # 1 + _MAX_RETRY(2)

    async def test_succeeds_on_second_attempt(self):
        profile = UserProfile()
        missing = ["housing_type"]

        with patch("agents.detail_interview.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_extractor = AsyncMock()
            mock_extractor.ainvoke = AsyncMock(
                side_effect=[
                    Exception("1차 실패"),
                    _DetailExtraction(housing_type="전세"),
                ]
            )
            mock_llm.with_structured_output.return_value = mock_extractor
            mock_get_llm.return_value = mock_llm

            new_profile, new_missing, failed = await _extract_profile(
                profile, missing, "전세입니다", []
            )

        assert new_profile.housing_type == "전세"
        assert "housing_type" not in new_missing
        assert failed is False


class TestGenerateQuestion:
    @patch("agents.detail_interview.load_prompt", return_value="system prompt")
    @patch("agents.detail_interview.get_llm")
    async def test_returns_llm_content(self, mock_get_llm, mock_load_prompt, mock_llm):
        mock_get_llm.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="장애 유형이 어떻게 되세요?")
        )
        selected = WelfareCandidate(
            serv_id="SVC001", serv_nm="장애인 활동지원", serv_dgst="..."
        )

        question = await _generate_question(
            UserProfile(), ["disability_type"], selected, []
        )

        assert question == "장애 유형이 어떻게 되세요?"

    @patch("agents.detail_interview.load_prompt", return_value="system prompt")
    @patch("agents.detail_interview.get_llm")
    async def test_history_included_in_messages(
        self, mock_get_llm, mock_load_prompt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="질문"))
        selected = WelfareCandidate(
            serv_id="SVC001", serv_nm="장애인 활동지원", serv_dgst="..."
        )

        history = [HumanMessage(content="안녕하세요"), AIMessage(content="안녕하세요!")]
        await _generate_question(UserProfile(), ["disability_type"], selected, history)

        call_messages = mock_llm.ainvoke.call_args[0][0]
        assert any(m.content == "안녕하세요" for m in call_messages)

    @patch("agents.detail_interview.load_prompt", return_value="system prompt")
    @patch("agents.detail_interview.get_llm")
    async def test_service_context_included_in_instruction(
        self, mock_get_llm, mock_load_prompt, mock_llm
    ):
        mock_get_llm.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="질문"))
        selected = WelfareCandidate(
            serv_id="SVC001",
            serv_nm="장애인 활동지원",
            serv_dgst="장애인 자립 지원 서비스",
        )

        await _generate_question(UserProfile(), ["disability_type"], selected, [])

        call_messages = mock_llm.ainvoke.call_args[0][0]
        last_human = next(
            m for m in reversed(call_messages) if isinstance(m, HumanMessage)
        )
        assert "장애인 활동지원" in last_human.content
        assert "장애인 자립 지원 서비스" in last_human.content
