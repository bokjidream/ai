"""UserProfile 문자열 변환 유틸."""

from graph.state import UserProfile


def format_user_profile(profile: UserProfile, *, bullet: bool = False) -> str:
    """UserProfile을 사람이 읽기 좋은 문자열로 변환.

    bullet=True이면 각 줄 앞에 "- "를 붙인다 (LLM 프롬프트 마크다운용).
    """
    prefix = "- " if bullet else ""
    lines = []
    if profile.age is not None:
        lines.append(f"{prefix}나이: {profile.age}세")
    if profile.region is not None:
        lines.append(f"{prefix}지역: {profile.region}")
    if profile.income_level is not None:
        lines.append(f"{prefix}소득 수준: {profile.income_level.value}")
    if profile.disability is not None:
        lines.append(f"{prefix}장애 여부: {'있음' if profile.disability else '없음'}")
    if profile.disability_type is not None:
        lines.append(f"{prefix}장애 유형: {profile.disability_type}")
    if profile.disability_grade is not None:
        lines.append(f"{prefix}장애 등급: {profile.disability_grade}")
    if profile.marital_status is not None:
        lines.append(f"{prefix}혼인 상태: {profile.marital_status.value}")
    if profile.household_size is not None:
        lines.append(f"{prefix}가구원 수: {profile.household_size}명")
    if profile.employment_status is not None:
        lines.append(f"{prefix}취업 상태: {profile.employment_status.value}")
    if profile.housing_type is not None:
        lines.append(f"{prefix}주거 유형: {profile.housing_type}")
    if profile.is_veteran is not None:
        veteran_val = "해당" if profile.is_veteran else "비해당"
        lines.append(f"{prefix}국가유공자: {veteran_val}")
    if profile.is_single_parent is not None:
        single_parent_val = "해당" if profile.is_single_parent else "비해당"
        lines.append(f"{prefix}한부모 가정: {single_parent_val}")
    for key, val in profile.extra_fields.items():
        lines.append(f"{prefix}{key}: {val}")
    return "\n".join(lines) if lines else "수집된 사용자 정보 없음"
