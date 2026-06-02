"""서류 안내 + 신청 방법 안내 노드 — LLM 1회 호출로 JSON 동시 출력.

document_guidance_node: LLM 호출 후 state 커밋 (interrupt 없음)
service_detail_pause_node: interrupt만 수행 → 웹이 /report로 이동 후 HWP 스캔 진행
"""

import asyncio
import json
import logging
import os

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from graph.state import AgentState, UserProfile, WelfareCandidate
from tools.json_utils import parse_llm_json
from tools.llm import get_llm
from tools.profile_utils import format_user_profile
from tools.prompt_loader import load_prompt

_LLM_MAX_RETRY = int(os.getenv("LLM_MAX_RETRY", "2"))

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


async def document_guidance_node(state: AgentState) -> dict:
    """required_documents + application_method를 LLM 1회 호출로 JSON 출력.

    출력 state 필드: document_guidance, application_guide
    """
    selected: WelfareCandidate = state["selected_service"]
    profile: UserProfile = state["user_profile"]

    has_documents = bool(selected.required_documents)
    has_method = bool(selected.application_method)

    fallback_doc = (
        f"'{selected.serv_nm}' 신청에 필요한 서류 정보가 없습니다. "
        "해당 기관에 직접 문의하여 필요 서류를 확인해 주세요."
    )
    fallback_guide = (
        f"'{selected.serv_nm}' 신청 방법 정보가 없습니다. "
        "해당 기관에 직접 문의하여 신청 방법을 확인해 주세요."
    )

    app_forms, ref_docs = _classify_application_forms(selected.application_forms)

    if not has_documents and not has_method:
        return {
            "document_guidance": fallback_doc,
            "application_guide": fallback_guide,
            "selected_service": selected.model_copy(
                update={"application_forms": app_forms}
            ),
            "reference_docs": ref_docs,
            "messages": [AIMessage(content=fallback_doc)],
        }

    required_docs_text = (
        "\n".join(f"- {d}" for d in selected.required_documents)
        if selected.required_documents
        else "서류 목록 정보 없음 — 신청방법 원문을 참고하세요."
    )

    prompt_template = load_prompt("document_guidance")
    prompt = prompt_template.format(
        serv_nm=selected.serv_nm,
        required_documents=required_docs_text,
        application_method=selected.application_method or "신청방법 정보 없음",
        user_info=format_user_profile(profile, bullet=True),
    )

    llm = get_llm()
    doc_guidance = fallback_doc
    app_guide = fallback_guide

    for attempt in range(1, _LLM_MAX_RETRY + 1):
        try:
            response = await llm.ainvoke(prompt)
            content = response.content
            parsed = parse_llm_json(content)
            doc_guidance = parsed.get("document_guidance") or fallback_doc
            app_guide = parsed.get("application_guide") or fallback_guide
            break
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "[document_guidance] JSON 파싱 실패 (시도 %d/%d): %s",
                attempt,
                _LLM_MAX_RETRY,
                e,
                exc_info=True,
            )
            if attempt < _LLM_MAX_RETRY:
                await asyncio.sleep(1)
        except Exception as e:
            logger.warning(
                "[document_guidance] LLM 호출 실패 (시도 %d/%d): %s",
                attempt,
                _LLM_MAX_RETRY,
                e,
                exc_info=True,
            )
            break

    return {
        "document_guidance": doc_guidance,
        "application_guide": app_guide,
        "selected_service": selected.model_copy(
            update={"application_forms": app_forms}
        ),
        "reference_docs": ref_docs,
        "messages": [AIMessage(content=doc_guidance)],
    }


async def service_detail_pause_node(state: AgentState) -> dict:
    """서비스 상세 안내 후 HWP 스캔 대기.

    document_guidance_node가 state를 커밋한 뒤 interrupt → 웹이 /report로 이동.
    /report에서 __start_draft__를 보내면 draft_field_extractor가 이어서 실행된다.
    """
    interrupt({"type": "service_detail"})
    return {}
