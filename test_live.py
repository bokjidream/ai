"""hwnv.cloud API 실시간 테스트 — 자동 답변 모드."""

import asyncio

from tools.hwnv_client import ask_question, extract_value

# 필드별 자동 답변 (원하는 값으로 수정하세요)
AUTO_ANSWERS: dict[str, str] = {
    "age": "저는 26살이에요",
    "region": "수원시에 살아요",
    "household_size": "3명이요",
    "marital_status": "미혼입니다",
    "has_children": "자녀 없어요",
    "disability": "장애 없습니다",
    "disability_severity": "경증이에요",
    "employment_status": "취업 중이에요",
    "income_level": "일반 소득이에요",
}

FIELDS = [
    "age",
    "region",
    "household_size",
    "marital_status",
    "has_children",
    "disability",
    "employment_status",
    "income_level",
]


async def interview_field(field: str) -> tuple[str, object]:
    """단일 필드에 대해 질문-답변-추출 루프를 수행합니다."""
    last_question = ""
    last_answer = ""
    is_reask = False

    while True:
        question = await ask_question(
            field=field,
            re_ask=is_reask,
            pre_assistant_message=last_question if is_reask else "",
            pre_user_message=last_answer if is_reask else "",
        )

        user_answer = AUTO_ANSWERS[field]
        print(f"\n[{field}] {question}")
        print(f"  >> {user_answer}  (자동)")

        result = await extract_value(field, question, user_answer)
        print(
            f"  exist={result['exist']}, value={result['value']},"
            f" re_ask={result['re_ask']}"
        )
        print(f"  reasoning: {result['reasoning']}")

        if result["exist"]:
            return field, result["value"]

        last_question = question
        last_answer = user_answer
        is_reask = True


async def main() -> None:
    """모든 인터뷰 필드에 대해 hwnv.cloud API 질문·추출 흐름을 자동으로 테스트합니다."""
    print("=== hwnv.cloud API 자동 테스트 ===\n")

    collected: dict = {}

    for field in FIELDS:
        key, value = await interview_field(field)
        collected[key] = value

        if field == "disability" and value is True:
            key2, value2 = await interview_field("disability_severity")
            collected[key2] = value2

    print("\n=== 수집 결과 ===")
    for k, v in collected.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
