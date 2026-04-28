"""서비스 선택 HitL 노드 — 후보 목록 제시 후 사용자 선택을 interrupt()로 수신."""

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

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

    # 후보 목록 표시 후 interrupt — 사용자 입력 대기
    candidates_display = _format_candidates(candidates)
    user_input: str = interrupt(value={"candidates": candidates_display, "error": None})

    # 입력 유효성 검사 루프 (노드 내부 루프 없이 재interrupt)
    while True:
        try:
            choice = int(user_input.strip())
            if 1 <= choice <= len(candidates):
                break
        except (ValueError, AttributeError):
            pass

        # 잘못된 입력 → 오류 메시지와 함께 재interrupt
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
