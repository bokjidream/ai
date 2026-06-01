"""환경변수 기반 런타임 설정 헬퍼."""

import os


def is_skip_interview() -> bool:
    """SKIP_INTERVIEW 환경변수가 'true'이면 True를 반환합니다."""
    return os.getenv("SKIP_INTERVIEW", "false").lower() == "true"


def skip_service_id() -> str:
    """SKIP_SERVICE_ID 환경변수 값을 반환합니다."""
    return os.getenv("SKIP_SERVICE_ID", "").strip()
