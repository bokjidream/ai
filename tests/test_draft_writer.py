"""draft_writer_node 단위 테스트 (HWP/HWPX 자동 채우기 + PDF 가이드)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.draft_writer import _extract_field_labels, _has_blanks, draft_writer_node
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


# ── HWP/HWPX 처리 테스트 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_application_forms_returns_empty():
    """application_forms가 없을 때 빈 리스트 반환."""
    state = _make_state(
        selected_service=WelfareCandidate(
            serv_id="S002",
            serv_nm="테스트서비스",
            serv_dgst="설명",
            application_forms=[],
        )
    )
    result = await draft_writer_node(state, _CONFIG)
    assert result == {"filled_forms": []}


@pytest.mark.asyncio
async def test_unsupported_file_type_is_skipped():
    """지원하지 않는 파일 타입(docx 등)은 skip하여 filled_forms에 추가하지 않음."""
    state = _make_state(
        selected_service=WelfareCandidate(
            serv_id="S003",
            serv_nm="테스트서비스",
            serv_dgst="설명",
            application_forms=[
                {"title": "안내문", "url": "http://ex.com/a.docx", "file_type": "docx"}
            ],
        )
    )
    result = await draft_writer_node(state, _CONFIG)
    assert result == {"filled_forms": []}


@pytest.mark.asyncio
async def test_hwp_download_failure_is_graceful():
    """HWP 다운로드 실패 시 status='failed'로 기록하고 계속 진행."""
    state = _make_state()

    with (
        patch(
            "agents.draft_writer.download_hwp",
            side_effect=Exception("Connection refused"),
        ),
        patch("agents.draft_writer.get_output_dir") as mock_dir,
    ):
        mock_output_dir = MagicMock()
        mock_output_dir.mkdir.return_value = None
        mock_output_dir.__truediv__ = lambda self, other: MagicMock(
            exists=lambda: False, unlink=MagicMock()
        )
        mock_dir.return_value = mock_output_dir

        result = await draft_writer_node(state, _CONFIG)

    assert len(result["filled_forms"]) == 1
    assert result["filled_forms"][0]["status"] == "failed"
    assert "Connection refused" in result["filled_forms"][0]["error"]


@pytest.mark.asyncio
async def test_hwp_llm_mapping_failure_results_in_skipped(tmp_path):
    """LLM 매핑 실패 시 status='skipped', 원본 파일 보존."""
    state = _make_state()
    raw_file = tmp_path / "raw_00_기초연금_신청서.hwp"
    raw_file.write_bytes(b"dummy hwp content")

    with (
        patch("agents.draft_writer.download_hwp", new=AsyncMock()) as mock_dl,
        patch("agents.draft_writer.scan_hwp_labels", new=AsyncMock(return_value=[])),
        patch(
            "agents.draft_writer._generate_hwp_field_mapping",
            new=AsyncMock(return_value={}),
        ),
        patch("agents.draft_writer.get_output_dir", return_value=tmp_path),
    ):
        mock_dl.side_effect = lambda url, dest: dest.write_bytes(b"dummy hwp content")

        result = await draft_writer_node(state, _CONFIG)

    assert result["filled_forms"][0]["status"] == "skipped"


@pytest.mark.asyncio
async def test_hwp_successful_fill(tmp_path):
    """정상 흐름: 다운로드 → LLM 매핑 → fill_hwp 호출 → status='success'."""
    state = _make_state()

    mock_fill_result = {"ok": True, "count": 3, "replacements": []}

    with (
        patch("agents.draft_writer.download_hwp", new=AsyncMock()) as mock_dl,
        patch(
            "agents.draft_writer.scan_hwp_labels",
            new=AsyncMock(return_value=["성명", "주소"]),
        ),
        patch(
            "agents.draft_writer._generate_hwp_field_mapping",
            new=AsyncMock(return_value={"성명": "홍길동", "주소": "서울특별시"}),
        ),
        patch(
            "agents.draft_writer.fill_hwp",
            new=AsyncMock(return_value=mock_fill_result),
        ),
        patch("agents.draft_writer.get_output_dir", return_value=tmp_path),
    ):
        mock_dl.side_effect = lambda url, dest: dest.write_bytes(b"dummy")

        result = await draft_writer_node(state, _CONFIG)

    filled = result["filled_forms"]
    assert len(filled) == 1
    assert filled[0]["status"] == "success"
    assert filled[0]["download_key"].startswith("test-thread-001/")
    assert "saved_path" in filled[0]


# ── PDF 처리 테스트 ─────────────────────────────────────────────────────────────


class TestHasBlanks:
    def test_detects_underscores(self):
        assert _has_blanks("성명 ___________") is True

    def test_detects_checkbox(self):
        assert _has_blanks("□ 해당") is True

    def test_no_blanks(self):
        assert _has_blanks("이 문서는 안내서입니다.") is False


class TestExtractFieldLabels:
    def test_extracts_underscore_labels(self):
        text = "성명 ___\n주소 ____\n전화번호 ___"
        labels = _extract_field_labels(text)
        assert "성명" in labels
        assert "주소" in labels

    def test_extracts_checkbox_labels(self):
        text = "□ 장애인\n□ 기초수급자"
        labels = _extract_field_labels(text)
        assert "장애인" in labels

    def test_deduplicates(self):
        text = "성명 ___\n성명 ___"
        labels = _extract_field_labels(text)
        assert labels.count("성명") == 1

    def test_max_20_labels(self):
        lines = "\n".join(f"항목{i} ____" for i in range(30))
        labels = _extract_field_labels(lines)
        assert len(labels) <= 20


@pytest.mark.asyncio
async def test_pdf_no_blanks_is_skipped():
    """빈칸이 없는 PDF(안내서류)는 None 반환 → filled_forms에 추가 안 됨."""
    state = _make_state(
        selected_service=WelfareCandidate(
            serv_id="S004",
            serv_nm="테스트서비스",
            serv_dgst="설명",
            application_forms=[
                {
                    "title": "안내문",
                    "url": "http://ex.com/guide.pdf",
                    "file_type": "pdf",
                }
            ],
        )
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = b"%PDF-1.4 mock"

    with (
        patch("agents.draft_writer.httpx.AsyncClient") as mock_client_cls,
        patch("agents.draft_writer.pdfplumber.open") as mock_pdf_open,
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "이 문서는 기초연금 안내서입니다."
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value = mock_pdf

        result = await draft_writer_node(state, _CONFIG)

    assert result == {"filled_forms": []}


@pytest.mark.asyncio
async def test_pdf_with_blanks_returns_guide_only():
    """빈칸이 있는 PDF는 status='guide_only'로 guide_text 포함."""
    state = _make_state(
        selected_service=WelfareCandidate(
            serv_id="S005",
            serv_nm="기초연금",
            serv_dgst="설명",
            application_forms=[
                {
                    "title": "기초연금 신청서",
                    "url": "http://ex.com/form.pdf",
                    "file_type": "pdf",
                }
            ],
        )
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = b"%PDF-1.4 mock"

    with (
        patch("agents.draft_writer.httpx.AsyncClient") as mock_client_cls,
        patch("agents.draft_writer.pdfplumber.open") as mock_pdf_open,
        patch(
            "agents.draft_writer._generate_pdf_guide",
            new=AsyncMock(return_value="성명란에 홍길동을 입력하세요."),
        ),
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "성명 ___________\n주소 ___________"
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value = mock_pdf

        result = await draft_writer_node(state, _CONFIG)

    filled = result["filled_forms"]
    assert len(filled) == 1
    assert filled[0]["status"] == "guide_only"
    assert "guide_text" in filled[0]
    assert filled[0]["original_url"] == "http://ex.com/form.pdf"
