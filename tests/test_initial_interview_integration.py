"""실제 hwnv.cloud API를 호출하는 통합 테스트. 실행: uv run pytest -s -m integration."""

import pytest

from agents.initial_interview import _apply_value, _update_missing
from graph.state import UserProfile
from tools import hwnv_client

# 라운드별 사용자 답변 시나리오 (순서대로 소진)
_USER_ANSWERS = [
    "안녕하세요. 저는 72살이고 경기도 성남에 살고 있어요.",
    "혼자 살고 있고 미혼입니다. 자녀는 없어요.",
    "장애는 없고요, 지금은 일을 안 하고 있어요.",
    "기초생활수급자입니다.",
]


@pytest.mark.integration
class TestFullInterviewFlow:
    async def test_full_interview_until_complete(self):
        """모든 필드가 수집될 때까지 인터뷰 전 과정 시뮬레이션."""
        profile = UserProfile()
        missing = [
            "age",
            "region",
            "household_size",
            "marital_status",
            "has_children",
            "disability",
            "employment_status",
            "income_level",
        ]
        answers = list(_USER_ANSWERS)
        round_num = 0

        print("\n" + "=" * 60)
        print("인터뷰 전 과정 시뮬레이션")
        print("=" * 60)

        while missing:
            round_num += 1
            field = missing[0]
            print(f"\n[라운드 {round_num}] 남은 필드: {missing}, 현재 필드: {field}")

            question = await hwnv_client.ask_question(field=field, re_ask=False)
            print(f"AI  : {question}")

            if not answers:
                print("(시나리오 답변 소진 — 루프 종료)")
                break

            user_answer = answers.pop(0)
            print(f"사용자: {user_answer}")

            result = await hwnv_client.extract_value(field, question, user_answer)
            print(f"추출 결과: {result}")

            if result.get("exist"):
                profile = _apply_value(profile, field, result["value"])
                missing = _update_missing(field, profile, missing)

        print("\n" + "=" * 60)
        print(f"최종 프로필: {profile.model_dump(exclude_none=True)}")
        print(f"미수집 필드: {missing}")
        print("=" * 60)

        assert not missing, f"미수집 필드가 남아있음: {missing}"
