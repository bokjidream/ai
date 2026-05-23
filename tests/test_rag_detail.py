"""RAG 상세 조회 노드 테스트."""

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from agents.rag_detail import _classify_schemas, rag_detail_node
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
        "interview_current_field": None,
        "interview_last_question": "",
        "interview_last_answer": "",
        "pending_question": None,
        "detail_current_field": None,
        "detail_last_question": "",
        "detail_last_answer": "",
        "extra_field_schemas": [],
    }
    defaults.update(kwargs)
    return defaults  # type: ignore[return-value]


_DUMMY_DETAIL = {
    "serv_id": "WLF-001",
    "serv_nm": "기초생활수급자 생계급여",
    "required_documents": ["사회보장급여 신청서", "신분증"],
    "application_method": "읍면동 주민센터 방문 신청, 사회보장급여 신청서 제출",
    "application_url": "https://www.bokjiro.go.kr",
    "application_forms": [
        {
            "title": "사회보장급여 신청서",
            "url": "https://www.bokjiro.go.kr/form.hwp",
            "file_type": "hwp",
        },
    ],
    "tgtr_dtl_cn": "기초생활수급자 중 생계급여 수급자",
    "slct_crit_cn": "소득인정액이 생계급여 선정기준 이하인 자",
    "trgter_indvdl": ["저소득층"],
}


class TestRagDetailNode:
    @patch(
        "agents.rag_detail.hwnv_client.extract_extra_field_schemas",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_updates_selected_service_on_success(
        self, mock_get_detail, mock_extractor
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_extractor.return_value = []

        result = await rag_detail_node(_make_state())

        updated = result["selected_service"]
        assert updated.detail_fetched is True
        assert updated.required_documents == ["사회보장급여 신청서", "신분증"]
        assert (
            updated.application_method
            == "읍면동 주민센터 방문 신청, 사회보장급여 신청서 제출"
        )
        assert updated.application_url == "https://www.bokjiro.go.kr"
        assert updated.application_forms == _DUMMY_DETAIL["application_forms"]

    @patch(
        "agents.rag_detail.hwnv_client.extract_extra_field_schemas",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_preserves_existing_fields_on_success(
        self, mock_get_detail, mock_extractor
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_extractor.return_value = []

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
    async def test_network_error_returns_empty_detail_missing_fields(
        self, mock_get_detail
    ):
        mock_get_detail.side_effect = Exception("Connection error")

        result = await rag_detail_node(_make_state())

        assert result["detail_missing_fields"] == []

    @patch(
        "agents.rag_detail.hwnv_client.extract_extra_field_schemas",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_missing_optional_fields_default_to_empty(
        self, mock_get_detail, mock_extractor
    ):
        mock_get_detail.return_value = {
            "serv_id": "WLF-001",
            "serv_nm": "기초생활수급자 생계급여",
        }
        mock_extractor.return_value = []

        result = await rag_detail_node(_make_state())

        updated = result["selected_service"]
        assert updated.required_documents == []
        assert updated.application_method == ""
        assert updated.application_url is None
        assert updated.application_forms == []
        assert updated.detail_fetched is True

    @patch(
        "agents.rag_detail.hwnv_client.extract_extra_field_schemas",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_standard_fields_in_detail_missing_fields(
        self, mock_get_detail, mock_extractor
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_extractor.return_value = [
            {
                "key": "housing_type",
                "label": "주거 형태",
                "type": "enum",
                "enum_values": ["자가", "전세", "월세"],
            },
            {"key": "is_veteran", "label": "국가보훈 대상 여부", "type": "bool"},
        ]

        result = await rag_detail_node(_make_state())

        assert "housing_type" in result["detail_missing_fields"]
        assert "is_veteran" in result["detail_missing_fields"]

    @patch(
        "agents.rag_detail.hwnv_client.extract_extra_field_schemas",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_extra_fields_prefixed_in_detail_missing_fields(
        self, mock_get_detail, mock_extractor
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_extractor.return_value = [
            {"key": "deposit_amount", "label": "보증금", "type": "int"},
        ]

        result = await rag_detail_node(_make_state())

        assert "extra:deposit_amount" in result["detail_missing_fields"]

    @patch(
        "agents.rag_detail.hwnv_client.extract_extra_field_schemas",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_extra_field_schemas_stored_in_state(
        self, mock_get_detail, mock_extractor
    ):
        schema = {"key": "deposit_amount", "label": "보증금", "type": "int"}
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_extractor.return_value = [schema]

        result = await rag_detail_node(_make_state())

        assert schema in result["extra_field_schemas"]

    @patch(
        "agents.rag_detail.hwnv_client.extract_extra_field_schemas",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_passes_service_info_to_field_extractor(
        self, mock_get_detail, mock_extractor
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_extractor.return_value = []

        await rag_detail_node(_make_state())

        call_args = mock_extractor.call_args[0][0]
        assert call_args["serv_nm"] == _DUMMY_DETAIL["serv_nm"]
        assert call_args["tgtr_dtl_cn"] == _DUMMY_DETAIL["tgtr_dtl_cn"]
        assert call_args["slct_crit_cn"] == _DUMMY_DETAIL["slct_crit_cn"]
        assert call_args["trgter_indvdl"] == _DUMMY_DETAIL["trgter_indvdl"]

    @patch(
        "agents.rag_detail.hwnv_client.extract_extra_field_schemas",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_field_extractor_error_returns_empty_missing(
        self, mock_get_detail, mock_extractor
    ):
        mock_get_detail.return_value = _DUMMY_DETAIL
        mock_extractor.side_effect = Exception("hwnv 오류")

        result = await rag_detail_node(_make_state())

        assert result["detail_missing_fields"] == []
        assert result["extra_field_schemas"] == []

    @patch(
        "agents.rag_detail.hwnv_client.extract_extra_field_schemas",
        new_callable=AsyncMock,
    )
    @patch("agents.rag_detail.rag_client.get_detail", new_callable=AsyncMock)
    async def test_first_attempt_fails_second_succeeds(
        self, mock_get_detail, mock_extractor
    ):
        """RAG 첫 시도 실패 → 두 번째 성공 → 정상 처리."""
        mock_get_detail.side_effect = [Exception("일시 오류"), _DUMMY_DETAIL]
        mock_extractor.return_value = []

        result = await rag_detail_node(_make_state())

        assert mock_get_detail.call_count == 2
        assert result["selected_service"].detail_fetched is True
        assert result["selected_service"].required_documents == [
            "사회보장급여 신청서",
            "신분증",
        ]


class TestClassifySchemas:
    """_classify_schemas 단위 테스트."""

    def test_standard_field_goes_to_regular_missing(self):
        profile = UserProfile(disability=False)
        schemas = [{"key": "housing_type", "label": "주거 형태", "type": "enum"}]
        regular, extra = _classify_schemas(schemas, profile)
        assert "housing_type" in regular
        assert extra == []

    def test_unknown_field_goes_to_extra_schemas(self):
        profile = UserProfile(disability=False)
        schema = {"key": "deposit_amount", "label": "보증금", "type": "int"}
        regular, extra = _classify_schemas([schema], profile)
        assert regular == []
        assert schema in extra

    def test_already_filled_standard_field_skipped(self):
        profile = UserProfile(disability=False, housing_type="자가")
        schemas = [{"key": "housing_type", "label": "주거 형태", "type": "enum"}]
        regular, extra = _classify_schemas(schemas, profile)
        assert "housing_type" not in regular

    def test_already_filled_extra_field_skipped(self):
        profile = UserProfile(disability=False, extra_fields={"deposit": 5000})
        schemas = [{"key": "deposit", "label": "보증금", "type": "int"}]
        regular, extra = _classify_schemas(schemas, profile)
        assert extra == []

    def test_disability_fields_excluded_when_disability_false(self):
        profile = UserProfile(disability=False)
        schemas = [
            {"key": "disability_type", "label": "장애 유형", "type": "string"},
            {"key": "disability_grade", "label": "장애 등급", "type": "string"},
            {"key": "housing_type", "label": "주거 형태", "type": "enum"},
        ]
        regular, _ = _classify_schemas(schemas, profile)
        assert "disability_type" not in regular
        assert "disability_grade" not in regular
        assert "housing_type" in regular

    def test_disability_fields_included_when_disability_true(self):
        profile = UserProfile(disability=True)
        schemas = [
            {"key": "disability_type", "label": "장애 유형", "type": "string"},
        ]
        regular, _ = _classify_schemas(schemas, profile)
        assert "disability_type" in regular

    def test_mixed_standard_and_extra_fields(self):
        profile = UserProfile(disability=False)
        schemas = [
            {"key": "is_veteran", "label": "보훈 대상", "type": "bool"},
            {"key": "custom_field", "label": "커스텀", "type": "string"},
        ]
        regular, extra = _classify_schemas(schemas, profile)
        assert "is_veteran" in regular
        assert any(s["key"] == "custom_field" for s in extra)

    def test_children_field_excluded_when_has_children_false(self):
        profile = UserProfile(has_children=False)
        schemas = [
            {"key": "has_children_age", "label": "자녀 연령", "type": "int"},
            {"key": "deposit_amount", "label": "보증금", "type": "int"},
        ]
        regular, extra = _classify_schemas(schemas, profile)
        assert not any(s["key"] == "has_children_age" for s in extra)
        assert any(s["key"] == "deposit_amount" for s in extra)

    def test_children_field_included_when_has_children_true(self):
        profile = UserProfile(has_children=True)
        schema = {"key": "has_children_age", "label": "자녀 연령", "type": "int"}
        regular, extra = _classify_schemas([schema], profile)
        assert schema in extra

    def test_children_field_excluded_by_label_keyword(self):
        profile = UserProfile(has_children=False)
        schema = {"key": "child_info", "label": "자녀 나이", "type": "string"}
        regular, extra = _classify_schemas([schema], profile)
        assert extra == []
