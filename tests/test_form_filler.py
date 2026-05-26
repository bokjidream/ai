"""form_filler_node 단위 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.form_filler import form_filler_node
from graph.state import AgentState, UserProfile, WelfareCandidate


def _make_state(**overrides) -> AgentState:
    base: AgentState = {
        "messages": [],
        "user_profile": UserProfile(
            age=65,
            region="서울특별시",
            income_level="기초생활수급자",
            disability=False,
            employment_status="비경제활동",
        ),
        "initial_missing_fields": [],
        "welfare_candidates": [],
        "selected_service": WelfareCandidate(
            serv_id="S001",
            serv_nm="기초연금",
            serv_dgst="만 65세 이상 노인에게 연금을 지급합니다.",
            application_method="주민센터 방문 신청",
            application_forms=[
                {
                    "title": "기초연금 신청서",
                    "url": "http://example.com/form.hwp",
                    "file_type": "hwp",
                }
            ],
        ),
        "detail_missing_fields": [],
        "document_guidance": "",
        "application_guide": "기초연금 신청 안내",
        "final_report": "",
        "interview_current_field": None,
        "interview_last_question": "",
        "interview_last_answer": "",
        "pending_question": None,
        "detail_current_field": None,
        "detail_last_question": "",
        "detail_last_answer": "",
        "extra_field_schemas": [],
        "filled_forms": [],
        **overrides,
    }
    return base


_CONFIG = {"configurable": {"thread_id": "test-thread-001"}}


@pytest.mark.asyncio
async def test_no_hwp_forms_returns_empty():
    """application_forms가 없거나 PDF만 있을 때 빈 리스트 반환."""
    state = _make_state(
        selected_service=WelfareCandidate(
            serv_id="S002",
            serv_nm="테스트서비스",
            serv_dgst="설명",
            application_forms=[
                {"title": "안내문", "url": "http://ex.com/a.pdf", "file_type": "pdf"}
            ],
        )
    )
    result = await form_filler_node(state, _CONFIG)
    assert result == {"filled_forms": []}


@pytest.mark.asyncio
async def test_empty_application_forms_returns_empty():
    """application_forms가 빈 리스트일 때 빈 리스트 반환."""
    state = _make_state(
        selected_service=WelfareCandidate(
            serv_id="S003",
            serv_nm="테스트서비스",
            serv_dgst="설명",
            application_forms=[],
        )
    )
    result = await form_filler_node(state, _CONFIG)
    assert result == {"filled_forms": []}


@pytest.mark.asyncio
async def test_download_failure_is_graceful():
    """HWP 다운로드 실패 시 status='failed'로 기록하고 계속 진행."""
    state = _make_state()

    with (
        patch(
            "agents.form_filler.download_hwp",
            side_effect=Exception("Connection refused"),
        ),
        patch("agents.form_filler.get_output_dir") as mock_dir,
    ):
        mock_output_dir = MagicMock()
        mock_output_dir.mkdir.return_value = None
        mock_output_dir.__truediv__ = lambda self, other: MagicMock(
            exists=lambda: False, unlink=MagicMock()
        )
        mock_dir.return_value = mock_output_dir

        result = await form_filler_node(state, _CONFIG)

    assert len(result["filled_forms"]) == 1
    assert result["filled_forms"][0]["status"] == "failed"
    assert "Connection refused" in result["filled_forms"][0]["error"]


@pytest.mark.asyncio
async def test_llm_mapping_failure_results_in_skipped(tmp_path):
    """LLM 매핑 실패 시 status='skipped', 원본 파일 보존."""
    state = _make_state()
    raw_file = tmp_path / "raw_00_기초연금_신청서.hwp"
    raw_file.write_bytes(b"dummy hwp content")

    with (
        patch("agents.form_filler.download_hwp", new=AsyncMock()) as mock_dl,
        patch(
            "agents.form_filler._generate_field_mapping", new=AsyncMock(return_value={})
        ),
        patch("agents.form_filler.get_output_dir", return_value=tmp_path),
    ):
        mock_dl.side_effect = lambda url, dest: dest.write_bytes(b"dummy hwp content")

        result = await form_filler_node(state, _CONFIG)

    assert result["filled_forms"][0]["status"] == "skipped"


@pytest.mark.asyncio
async def test_successful_fill(tmp_path):
    """정상 흐름: 다운로드 → LLM 매핑 → fill_hwp 호출 → status='success'."""
    state = _make_state()

    mock_fill_result = {"ok": True, "count": 3, "replacements": []}

    with (
        patch("agents.form_filler.download_hwp", new=AsyncMock()) as mock_dl,
        patch(
            "agents.form_filler._generate_field_mapping",
            new=AsyncMock(return_value={"성명": "홍길동", "주소": "서울특별시"}),
        ),
        patch(
            "agents.form_filler.fill_hwp",
            new=AsyncMock(return_value=mock_fill_result),
        ),
        patch("agents.form_filler.get_output_dir", return_value=tmp_path),
    ):
        mock_dl.side_effect = lambda url, dest: dest.write_bytes(b"dummy")

        result = await form_filler_node(state, _CONFIG)

    filled = result["filled_forms"]
    assert len(filled) == 1
    assert filled[0]["status"] == "success"
    assert filled[0]["download_key"].startswith("test-thread-001/")
    assert "saved_path" in filled[0]
