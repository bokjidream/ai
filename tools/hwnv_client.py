"""hwnv.cloud 인터뷰 API 클라이언트."""

import json

import httpx

_BASE_URL = "https://hwnv.cloud"
_TIMEOUT = 120.0


async def ask_question(
    field: str,
    re_ask: bool,
    pre_assistant_message: str = "",
    pre_user_message: str = "",
) -> str:
    """Asker 모델로 특정 필드에 대한 질문을 생성합니다.

    Args:
        field: 수집할 항목 (age, region 등)
        re_ask: 재질문 여부
        pre_assistant_message: 직전 봇 발화 (재질문 시 자연스러운 연결용)
        pre_user_message: 직전 사용자 발화

    Returns:
        생성된 질문 문자열
    """
    payload: dict = {"information": field, "re_ask": re_ask}
    if pre_assistant_message:
        payload["pre_assistant_message"] = pre_assistant_message
        payload["pre_user_message"] = pre_user_message

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "asker",
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def extract_value(
    field: str,
    assistant_message: str,
    user_message: str,
) -> dict:
    """Interviewer 모델로 사용자 답변에서 값을 추출합니다.

    Args:
        field: 추출할 항목
        assistant_message: 봇이 했던 질문
        user_message: 사용자 답변

    Returns:
        {"exist": bool, "value": any | None, "re_ask": bool, "reasoning": str}
    """
    payload = {
        "information": field,
        "assistant_message": assistant_message,
        "user_message": user_message,
    }

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "interviewer",
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                ],
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content.strip())
