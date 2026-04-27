"""RAG 서비스 HTTP 클라이언트.

Phase 2: 하드코딩 더미 데이터 반환 스텁.
Phase 3: 실제 httpx.AsyncClient 연동으로 교체.
"""

import os


async def search(profile: dict, top_k: int | None = None) -> list[dict]:
    """복지 서비스 후보 목록 검색.

    Args:
        profile: UserProfile 핵심 필드를 담은 flat dict (age, income_level 등)
        top_k: 반환할 최대 후보 수. None이면 RAG_SEARCH_TOP_K 환경변수 사용 (기본 5)

    Returns:
        [{"serv_id", "serv_nm", "serv_dgst", "department", "score"}, ...]
        결과 없으면 빈 리스트 반환.
    """
    if top_k is None:
        top_k = int(os.getenv("RAG_SEARCH_TOP_K", "5"))

    # Phase 3에서 실제 HTTP 연동으로 교체
    return [
        {
            "serv_id": "WLF-001",
            "serv_nm": "기초생활수급자 생계급여",
            "serv_dgst": (
                "생활이 어려운 기초생활수급자에게 생계에 필요한 급여를 지급합니다."
            ),
            "department": "보건복지부",
            "score": 0.95,
        },
        {
            "serv_id": "WLF-002",
            "serv_nm": "장애인 활동지원 서비스",
            "serv_dgst": (
                "장애인의 자립생활을 지원하기 위해 활동보조, 방문목욕 등을 제공합니다."
            ),
            "department": "보건복지부",
            "score": 0.87,
        },
        {
            "serv_id": "WLF-003",
            "serv_nm": "노인 돌봄 종합서비스",
            "serv_dgst": (
                "혼자 힘으로 일상생활을 영위하기 어려운 노인에게 "
                "가사·활동지원 서비스를 제공합니다."
            ),
            "department": "보건복지부",
            "score": 0.80,
        },
    ][:top_k]


async def get_detail(service_id: str) -> dict:
    """특정 복지 서비스 상세 정보 조회.

    Args:
        service_id: RAG 서비스 ID (WelfareCandidate.serv_id)

    Returns:
        {"serv_id", "serv_nm", "required_documents", "application_fields",
        "application_url", ...}
    """
    # Phase 3에서 실제 HTTP 연동으로 교체
    dummy_details = {
        "WLF-001": {
            "serv_id": "WLF-001",
            "serv_nm": "기초생활수급자 생계급여",
            "required_documents": [
                "사회보장급여 신청서",
                "신분증",
                "금융정보 제공 동의서",
            ],
            "application_fields": [
                "신청인 성명",
                "생년월일",
                "주소",
                "소득 수준",
                "가구원 수",
            ],
            "application_url": "https://www.bokjiro.go.kr",
        },
        "WLF-002": {
            "serv_id": "WLF-002",
            "serv_nm": "장애인 활동지원 서비스",
            "required_documents": [
                "장애인 활동지원 신청서",
                "장애인 등록증",
                "건강보험료 납부 확인서",
            ],
            "application_fields": [
                "신청인 성명",
                "장애 유형",
                "장애 등급",
                "활동지원 필요 사유",
            ],
            "application_url": "https://www.ableservice.or.kr",
        },
        "WLF-003": {
            "serv_id": "WLF-003",
            "serv_nm": "노인 돌봄 종합서비스",
            "required_documents": ["서비스 신청서", "신분증", "건강보험료 납부 확인서"],
            "application_fields": ["신청인 성명", "생년월일", "주소", "돌봄 필요 사유"],
            "application_url": "https://www.longtermcare.or.kr",
        },
    }
    return dummy_details.get(
        service_id,
        {
            "serv_id": service_id,
            "serv_nm": "알 수 없는 서비스",
            "required_documents": [],
            "application_fields": [],
            "application_url": None,
        },
    )
