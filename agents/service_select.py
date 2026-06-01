"""서비스 선택 HitL 노드 — 후보 목록 제시 후 사용자 선택을 interrupt()로 수신."""

import re

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from graph.config import is_skip_interview, skip_service_id
from graph.state import AgentState, WelfareCandidate


def _format_candidates(candidates: list[WelfareCandidate]) -> str:
    """후보 목록을 번호 목록 문자열로 변환."""
    lines = ["지원 가능한 복지 서비스 목록입니다. 번호를 입력하여 선택해 주세요.\n"]
    for c in candidates:
        lines.append(f"{c.priority}. [{c.department}] {c.serv_nm}")
        lines.append(f"   {c.serv_dgst[:60]}...")
        if c.eligibility_reason:
            lines.append(f"   → {c.eligibility_reason}")
        lines.append("")
    return "\n".join(lines)


async def service_select_node(state: AgentState) -> dict:
    """서비스 선택 HitL 노드 — interrupt() → Command(resume=) 패턴."""
    candidates: list[WelfareCandidate] = state["welfare_candidates"]

    # 테스트 모드: 인터뷰 스킵 시 서비스 자동 선택
    if is_skip_interview():
        skip_id = skip_service_id()
        if skip_id:
            # 지정 serv_id가 후보에 있으면 사용, 없으면 stub 생성
            selected = next((c for c in candidates if c.serv_id == skip_id), None)
            if selected is None:
                selected = WelfareCandidate(
                    serv_id=skip_id, serv_nm=skip_id, serv_dgst=""
                )
        else:
            selected = candidates[0]
        return {
            "selected_service": selected,
            "messages": [
                AIMessage(content=f"[SKIP] '{selected.serv_nm}' 자동 선택됨.")
            ],
        }

    # 후보 목록 표시 후 interrupt — 사용자 입력 대기
    candidates_display = _format_candidates(candidates)
    user_input: str = interrupt(value={"candidates": candidates_display, "error": None})

    # 입력 유효성 검사 루프 — 올바른 번호가 올 때까지 재interrupt
    while True:
        match = re.search(r"\d+", user_input)
        if match:
            choice = int(match.group())
            if 1 <= choice <= len(candidates):
                break

        user_input = interrupt(
            value={
                "candidates": candidates_display,
                "error": f"1~{len(candidates)} 사이의 번호를 입력해 주세요.",
            }
        )

    selected = candidates[choice - 1]

    return {
        "selected_service": selected,
        "messages": [
            AIMessage(
                content=(
                    f"'{selected.serv_nm}'을(를) 선택하셨습니다. "
                    "상세 정보를 조회합니다."
                )
            )
        ],
    }
