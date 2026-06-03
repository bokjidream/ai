"""서비스 상세 안내 후 HWP 스캔 대기 노드."""

import logging

from langgraph.types import interrupt

from graph.state import AgentState, WelfareCandidate

logger = logging.getLogger("bokjidream.document_guidance")

_REFERENCE_KEYWORDS = ("안내", "공문", "리플릿", "팸플릿", "매뉴얼", "홍보")


def _classify_application_forms(
    forms: list[dict],
) -> tuple[list[dict], list[dict]]:
    """application_forms를 실제 신청서와 참고자료(안내문/공문)로 분류.

    Returns:
        (application_forms, reference_docs)
        - application_forms: draft_writer로 전달할 신청서 목록
        - reference_docs: 보고서에 링크로만 제공할 참고자료 [{"title", "url"}]
    """
    app_forms: list[dict] = []
    ref_docs: list[dict] = []

    for form in forms:
        title: str = form.get("title", "")
        if any(kw in title for kw in _REFERENCE_KEYWORDS):
            ref_docs.append({"title": title, "url": form.get("url", "")})
        else:
            app_forms.append(form)

    return app_forms, ref_docs


async def service_detail_pause_node(state: AgentState) -> dict:
    """application_forms 분류 후 interrupt → 웹이 /report로 이동.

    /report에서 __start_draft__를 보내면 draft_field_extractor가 이어서 실행된다.
    """
    selected: WelfareCandidate = state["selected_service"]
    app_forms, ref_docs = _classify_application_forms(selected.application_forms)
    interrupt({"type": "service_detail"})
    return {
        "selected_service": selected.model_copy(
            update={"application_forms": app_forms}
        ),
        "reference_docs": ref_docs,
    }
