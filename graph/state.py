from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel
from typing_extensions import TypedDict


class UserProfile(BaseModel):
    """사용자의 기본 인적 사항 및 복지 수급 판별 기준 정보를 담는 모델입니다."""

    age: int | None = None
    region: str | None = None
    monthly_income: int | None = None  # 만원 단위
    household_size: int | None = None
    disability: bool | None = None
    is_single_parent: bool | None = None


class WelfareCandidate(BaseModel):
    """추천된 복지 서비스의 후보군 및 수급 가능성 상태를 정의하는 모델입니다."""

    service_name: str
    eligibility: Literal["가능", "추가확인필요", "불가"]
    reason: str
    required_docs: list[str] = []
    apply_url: str | None = None


class AgentState(TypedDict):
    """LangGraph 내 에이전트 간 공유되는 전체 상태(State) 스키마입니다."""

    messages: Annotated[list, add_messages]
    user_profile: UserProfile
    missing_fields: list[str]
    candidates: list[WelfareCandidate]
    draft: str | None
    report: str | None
    current_step: str
