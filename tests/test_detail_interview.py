"""2단계 인터뷰 에이전트 테스트."""

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agents.detail_interview import (
    _apply_extracted_value,
    _get_field_info,
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
        "detail_current_field": None,
        "detail_last_question": "",
        "detail_last_answer": "",
        "extra_field_schemas": [],
        "pending_question": None,
    }
    state.update(overrides)
    return state


class TestDetailInterviewNodeBasic:
    async def test_returns_empty_when_no_missing_fields(self):
        state = _base_state(detail_missing_fields=[])
        result = await detail_interview_node(state)
        assert result == {}

    async def test_generates_question_and_returns_command(self):
        with patch(
            "agents.detail_interview.hwnv_client.ask_detail_question",
            new_callable=AsyncMock,
            return_value="장애 유형이 어떻게 되세요?",
        ):
            state = _base_state(
                detail_missing_fields=["disability_type"],
                pending_question=None,
            )
            result = await detail_interview_node(state)

        assert hasattr(result, "update")
        assert result.update["pending_question"] == "장애 유형이 어떻게 되세요?"

    async def test_interrupts_with_question_and_field(self):
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": True, "value": "지체장애", "re_ask": False},
        ):
            with patch(
                "agents.detail_interview.interrupt",
                return_value="지체장애입니다",
            ) as mock_interrupt:
                state = _base_state(
                    detail_missing_fields=["disability_type"],
                    pending_question="장애 유형이 어떻게 되세요?",
                )
                await detail_interview_node(state)

        mock_interrupt.assert_called_once()
        call_args = mock_interrupt.call_args[0][0]
        assert call_args["question"] == "장애 유형이 어떻게 되세요?"
        assert call_args["field"] == "disability_type"

    async def test_messages_contain_ai_and_human(self):
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": True, "value": "지체장애", "re_ask": False},
        ):
            with patch(
                "agents.detail_interview.interrupt",
                return_value="지체장애입니다",
            ):
                state = _base_state(
                    detail_missing_fields=["disability_type"],
                    pending_question="장애 유형이 어떻게 되세요?",
                )
                result = await detail_interview_node(state)

        msgs = result["messages"]
        assert any(isinstance(m, AIMessage) for m in msgs)
        assert any(isinstance(m, HumanMessage) for m in msgs)
        assert any(
            m.content == "지체장애입니다" for m in msgs if isinstance(m, HumanMessage)
        )


class TestDetailInterviewNodeExtraction:
    async def test_extracted_field_removed_from_missing(self):
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": True, "value": "지체장애", "re_ask": False},
        ):
            with patch("agents.detail_interview.interrupt", return_value="지체장애"):
                state = _base_state(
                    detail_missing_fields=["disability_type", "housing_type"],
                    pending_question="장애 유형이 어떻게 되세요?",
                )
                result = await detail_interview_node(state)

        assert "disability_type" not in result["detail_missing_fields"]
        assert "housing_type" in result["detail_missing_fields"]

    async def test_profile_updated_with_extracted_field(self):
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": True, "value": "지체장애", "re_ask": False},
        ):
            with patch("agents.detail_interview.interrupt", return_value="지체장애"):
                state = _base_state(
                    detail_missing_fields=["disability_type"],
                    pending_question="장애 유형이 어떻게 되세요?",
                )
                result = await detail_interview_node(state)

        assert result["user_profile"].disability_type == "지체장애"

    async def test_detail_current_field_cleared_on_success(self):
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": True, "value": "자가", "re_ask": False},
        ):
            with patch("agents.detail_interview.interrupt", return_value="자가입니다"):
                state = _base_state(
                    detail_missing_fields=["housing_type"],
                    detail_current_field="housing_type",
                    pending_question="주거 형태가 어떻게 되세요?",
                )
                result = await detail_interview_node(state)

        assert result["detail_current_field"] is None

    async def test_reask_sets_detail_current_field(self):
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": False, "value": None, "re_ask": True},
        ):
            with patch(
                "agents.detail_interview.interrupt", return_value="잘 모르겠어요"
            ):
                state = _base_state(
                    detail_missing_fields=["disability_type"],
                    pending_question="장애 유형이 어떻게 되세요?",
                )
                result = await detail_interview_node(state)

        assert result["detail_current_field"] == "disability_type"
        assert result["pending_question"] is None


class TestExtraFieldsHandling:
    async def test_extra_field_stored_in_extra_fields(self):
        extra_schemas = [
            {"key": "참전유공자", "label": "국가보훈 대상 여부", "type": "bool"}
        ]
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": True, "value": True, "re_ask": False},
        ):
            with patch(
                "agents.detail_interview.interrupt", return_value="참전용사입니다"
            ):
                state = _base_state(
                    detail_missing_fields=["extra:참전유공자"],
                    extra_field_schemas=extra_schemas,
                    pending_question="국가보훈 대상이신가요?",
                )
                result = await detail_interview_node(state)

        assert result["user_profile"].extra_fields.get("참전유공자") is True

    async def test_extra_field_removed_from_missing_after_extraction(self):
        extra_schemas = [
            {"key": "참전유공자", "label": "국가보훈 대상 여부", "type": "bool"}
        ]
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": True, "value": True, "re_ask": False},
        ):
            with patch(
                "agents.detail_interview.interrupt", return_value="참전용사입니다"
            ):
                state = _base_state(
                    detail_missing_fields=["extra:참전유공자"],
                    extra_field_schemas=extra_schemas,
                    pending_question="국가보훈 대상이신가요?",
                )
                result = await detail_interview_node(state)

        assert "extra:참전유공자" not in result["detail_missing_fields"]

    async def test_extra_field_remains_when_not_extracted(self):
        extra_schemas = [
            {"key": "참전유공자", "label": "국가보훈 대상 여부", "type": "bool"}
        ]
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": False, "value": None, "re_ask": True},
        ):
            with patch("agents.detail_interview.interrupt", return_value="모름"):
                state = _base_state(
                    detail_missing_fields=["extra:참전유공자"],
                    extra_field_schemas=extra_schemas,
                    pending_question="국가보훈 대상이신가요?",
                )
                result = await detail_interview_node(state)

        assert "extra:참전유공자" in result["detail_missing_fields"]

    async def test_unknown_extra_field_skipped(self):
        state = _base_state(
            detail_missing_fields=["extra:unknown_field"],
            extra_field_schemas=[],
        )
        result = await detail_interview_node(state)
        assert "extra:unknown_field" not in result["detail_missing_fields"]

    def test_existing_extra_fields_preserved_on_update(self):
        profile = UserProfile(extra_fields={"기존키": "기존값"})
        new_profile = _apply_extracted_value(profile, "extra:새키", "새값")
        assert new_profile.extra_fields["기존키"] == "기존값"
        assert new_profile.extra_fields["새키"] == "새값"


class TestChildrenAgesParsing:
    def test_children_ages_parsed_from_string(self):
        profile = UserProfile()
        new_profile = _apply_extracted_value(profile, "children_ages", "5 8 12")
        assert new_profile.children_ages == [5, 8, 12]

    def test_children_ages_parsed_with_comma(self):
        profile = UserProfile()
        new_profile = _apply_extracted_value(profile, "children_ages", "3, 7")
        assert new_profile.children_ages == [3, 7]

    def test_children_ages_non_digit_ignored(self):
        profile = UserProfile()
        new_profile = _apply_extracted_value(profile, "children_ages", "5살, 8살")
        assert new_profile.children_ages == [5, 8]


class TestGetFieldInfo:
    def test_standard_field_returns_info(self):
        info = _get_field_info("disability_type", [])
        assert info is not None
        assert info["key"] == "disability_type"

    def test_unknown_field_returns_none(self):
        info = _get_field_info("unknown_field", [])
        assert info is None

    def test_extra_field_found_in_schemas(self):
        schemas = [{"key": "my_key", "label": "내 필드", "type": "bool"}]
        info = _get_field_info("extra:my_key", schemas)
        assert info is not None
        assert info["key"] == "my_key"

    def test_extra_field_not_in_schemas_returns_none(self):
        info = _get_field_info("extra:missing_key", [])
        assert info is None


class TestErrorHandling:
    async def test_ask_question_error_returns_error_message(self):
        with patch(
            "agents.detail_interview.hwnv_client.ask_detail_question",
            new_callable=AsyncMock,
            side_effect=Exception("연결 실패"),
        ):
            state = _base_state(
                detail_missing_fields=["disability_type"],
                pending_question=None,
            )
            result = await detail_interview_node(state)

        msgs = result.get("messages", [])
        assert any(isinstance(m, AIMessage) for m in msgs)

    async def test_extract_value_error_keeps_reask_state(self):
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            side_effect=Exception("파싱 실패"),
        ):
            with patch(
                "agents.detail_interview.interrupt", return_value="지체장애입니다"
            ):
                state = _base_state(
                    detail_missing_fields=["disability_type"],
                    pending_question="장애 유형이 어떻게 되세요?",
                )
                result = await detail_interview_node(state)

        assert result["detail_current_field"] == "disability_type"
        assert result["pending_question"] is None
        assert "disability_type" in result["detail_missing_fields"]

    async def test_exist_false_reask_false_skips_field(self):
        with patch(
            "agents.detail_interview.hwnv_client.extract_detail_value",
            new_callable=AsyncMock,
            return_value={"exist": False, "value": None, "re_ask": False},
        ):
            with patch("agents.detail_interview.interrupt", return_value="없습니다"):
                state = _base_state(
                    detail_missing_fields=["disability_type", "housing_type"],
                    pending_question="장애 유형이 어떻게 되세요?",
                )
                result = await detail_interview_node(state)

        assert "disability_type" not in result["detail_missing_fields"]
        assert "housing_type" in result["detail_missing_fields"]
        assert result["detail_current_field"] is None
        assert result["pending_question"] is None
