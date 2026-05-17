"""RAG 검색 노드 테스트."""

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from agents.rag_search import _profile_to_dict, rag_search_node
from graph.state import (
    AgentState,
    EmploymentStatus,
    IncomeLevel,
    UserProfile,
    WelfareCandidate,
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
        "selected_service": None,
        "detail_missing_fields": [],
        "document_guidance": "",
        "application_guide": "",
        "final_report": "",
    }
    defaults.update(kwargs)
    return defaults  # type: ignore[return-value]


_DUMMY_RAG_RESULTS = [
    {
        "serv_id": "WLF-001",
        "serv_nm": "기초생활수급자 생계급여",
        "serv_dgst": "생활이 어려운 기초생활수급자에게 급여를 지급합니다.",
        "department": "보건복지부",
        "score": 0.95,
    },
    {
        "serv_id": "WLF-002",
        "serv_nm": "노인 돌봄 서비스",
        "serv_dgst": "혼자 생활하기 어려운 노인에게 돌봄 서비스를 제공합니다.",
        "department": "보건복지부",
        "score": 0.80,
    },
]


class TestProfileToDict:
    def test_includes_filled_fields_only(self):
        profile = UserProfile(age=65, income_level=IncomeLevel.BASIC, region="서울")
        result = _profile_to_dict(profile)
        assert result["age"] == 65
        assert result["income_level"] == "기초생활수급자"
        assert result["region"] == "서울"

    def test_excludes_none_fields(self):
        profile = UserProfile(age=40)
        result = _profile_to_dict(profile)
        assert "income_level" not in result
        assert "disability" not in result

    def test_excludes_is_elderly_derived_field(self):
        profile = UserProfile(age=65)
        result = _profile_to_dict(profile)
        assert "is_elderly" not in result

    def test_enum_values_are_strings(self):
        profile = UserProfile(
            employment_status=EmploymentStatus.UNEMPLOYED,
            income_level=IncomeLevel.NEAR_POOR,
        )
        result = _profile_to_dict(profile)
        assert result["employment_status"] == "실업"
        assert result["income_level"] == "차상위계층"

    def test_includes_household_size(self):
        profile = UserProfile(household_size=3)
        result = _profile_to_dict(profile)
        assert result["household_size"] == 3

    def test_includes_marital_status(self):
        from graph.state import MaritalStatus

        profile = UserProfile(marital_status=MaritalStatus.SINGLE)
        result = _profile_to_dict(profile)
        assert result["marital_status"] == "미혼"

    def test_includes_has_children(self):
        profile = UserProfile(has_children=True)
        result = _profile_to_dict(profile)
        assert result["has_children"] is True

    def test_includes_disability_severity_when_disabled(self):
        from graph.state import DisabilitySeverity

        profile = UserProfile(
            disability=True, disability_severity=DisabilitySeverity.SEVERE
        )
        result = _profile_to_dict(profile)
        assert result["disability_severity"] == "중증"

    def test_excludes_disability_severity_when_not_disabled(self):
        profile = UserProfile(disability=False, disability_severity=None)
        result = _profile_to_dict(profile)
        assert "disability_severity" not in result


class TestRagSearchNode:
    @patch(
        "agents.rag_search.hwnv_client.generate_eligibility_reason",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_search.rag_client.search", new_callable=AsyncMock)
    async def test_returns_candidates_on_success(self, mock_search, mock_reason):
        mock_search.return_value = _DUMMY_RAG_RESULTS
        mock_reason.return_value = "해당 서비스 대상자입니다."

        result = await rag_search_node(_make_state())

        assert len(result["welfare_candidates"]) == 2
        assert all(
            isinstance(c, WelfareCandidate) for c in result["welfare_candidates"]
        )

    @patch(
        "agents.rag_search.hwnv_client.generate_eligibility_reason",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_search.rag_client.search", new_callable=AsyncMock)
    async def test_priority_assigned_by_score_order(self, mock_search, mock_reason):
        unsorted = [
            {**_DUMMY_RAG_RESULTS[1], "score": 0.80},
            {**_DUMMY_RAG_RESULTS[0], "score": 0.95},
        ]
        mock_search.return_value = unsorted
        mock_reason.return_value = ""

        result = await rag_search_node(_make_state())

        candidates = result["welfare_candidates"]
        assert candidates[0].priority == 1
        assert candidates[0].score == 0.95
        assert candidates[1].priority == 2
        assert candidates[1].score == 0.80

    @patch(
        "agents.rag_search.hwnv_client.generate_eligibility_reason",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_search.rag_client.search", new_callable=AsyncMock)
    async def test_empty_result_returns_no_candidates_with_message(
        self, mock_search, mock_reason
    ):
        mock_search.return_value = []

        result = await rag_search_node(_make_state())

        assert result["welfare_candidates"] == []
        assert isinstance(result["messages"][0], AIMessage)
        assert "찾지 못했습니다" in result["messages"][0].content

    @patch(
        "agents.rag_search.hwnv_client.generate_eligibility_reason",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_search.rag_client.search", new_callable=AsyncMock)
    async def test_network_error_retries_and_returns_error_message(
        self, mock_search, mock_reason
    ):
        mock_search.side_effect = Exception("Connection error")

        result = await rag_search_node(_make_state())

        assert result["welfare_candidates"] == []
        assert isinstance(result["messages"][0], AIMessage)
        assert "연결 오류" in result["messages"][0].content
        assert mock_search.call_count == 2  # 1회 재시도 확인

    @patch(
        "agents.rag_search.hwnv_client.generate_eligibility_reason",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_search.rag_client.search", new_callable=AsyncMock)
    async def test_eligibility_reason_generated_per_candidate(
        self, mock_search, mock_reason
    ):
        mock_search.return_value = _DUMMY_RAG_RESULTS
        mock_reason.return_value = "적합한 서비스입니다."

        result = await rag_search_node(_make_state())

        assert mock_reason.call_count == len(_DUMMY_RAG_RESULTS)
        for candidate in result["welfare_candidates"]:
            assert candidate.eligibility_reason == "적합한 서비스입니다."
