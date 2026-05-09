from enum import StrEnum
from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, computed_field
from typing_extensions import TypedDict


class IncomeLevel(StrEnum):
    """소득 수준 구분 (RAG 팀 기준 값)."""

    BASIC = "기초생활수급자"
    NEAR_POOR = "차상위계층"
    LOW_INCOME = "저소득"
    GENERAL = "일반"


class EmploymentStatus(StrEnum):
    """취업 상태."""

    EMPLOYED = "취업"
    UNEMPLOYED = "실업"
    INACTIVE = "비경제활동"


class MaritalStatus(StrEnum):
    """혼인 상태."""

    SINGLE = "미혼"
    MARRIED = "기혼"
    DIVORCED = "이혼"
    WIDOWED = "사별"


class DisabilitySeverity(StrEnum):
    """장애 정도."""

    MILD = "경증"
    SEVERE = "중증"


class UserProfile(BaseModel):
    """인터뷰로 수집하는 사용자 정보."""

    # ── 1단계: RAG 검색 최소 필드 ──
    age: int | None = None
    region: str | None = None
    household_size: int | None = None
    marital_status: MaritalStatus | None = None
    has_children: bool | None = None
    disability: bool | None = None
    disability_severity: DisabilitySeverity | None = None  # disability=True일 때만
    employment_status: EmploymentStatus | None = None
    income_level: IncomeLevel | None = None  # LLM이 대화로 판단, 직접 입력 X

    @computed_field
    @property
    def is_elderly(self) -> bool | None:
        """만 65세 이상 여부 (age로 파생)."""
        return self.age >= 65 if self.age is not None else None

    # ── 2단계: 서비스 특화 필드 ──
    disability_type: str | None = None
    disability_grade: str | None = None
    children_ages: list[int] | None = None
    housing_type: str | None = None
    household_type: str | None = None
    is_veteran: bool | None = None
    is_single_parent: bool | None = None

    extra_fields: dict[str, str | int | bool] = {}


class WelfareCandidate(BaseModel):
    """RAG 검색 결과로 반환되는 복지 서비스 후보."""

    # ── 1차 RAG 검색 후 채워짐 (필드명 RAG 응답 기준) ──
    serv_id: str
    serv_nm: str
    serv_dgst: str
    department: str = ""  # 담당 기관명 — RAG /welfare/search 응답의 "department"
    eligibility_reason: str = ""  # rag_search_node에서 LLM으로 생성
    score: float = 0.0
    priority: int = 0  # rag_search_node가 score 내림차순 정렬 후 부여

    # ── 2차 RAG 상세 조회 후 채워짐 ──
    required_documents: list[str] = []
    application_method: str = ""
    application_url: str | None = None
    detail_fetched: bool = False


class AgentState(TypedDict):
    """8개 노드가 공유하는 전체 그래프 상태."""

    messages: Annotated[list[BaseMessage], add_messages]
    user_profile: UserProfile
    initial_missing_fields: list[str]
    welfare_candidates: list[WelfareCandidate]
    selected_service: WelfareCandidate | None
    detail_missing_fields: list[str]
    document_guidance: str
    application_guide: str
    final_report: str
    # 1단계 인터뷰 재질문 추적 (hwnv_client re_ask 흐름용)
    interview_current_field: str | None  # 현재 처리 중인 필드 (None=새 필드)
    interview_last_question: str  # 직전 봇 질문 (re_ask pre_assistant_message)
    interview_last_answer: str  # 직전 사용자 답변 (re_ask pre_user_message)
