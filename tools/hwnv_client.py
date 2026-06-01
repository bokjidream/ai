"""hwnv.cloud 인터뷰 API 클라이언트."""

import json
import logging
import os

import httpx
from dotenv import load_dotenv

logger = logging.getLogger("bokjidream.hwnv_client")

load_dotenv()

_BASE_URL = os.getenv("HWNV_SERVICE_URL", "https://hwnv.cloud")
_TIMEOUT = float(os.getenv("HWNV_TIMEOUT", "300.0"))


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
        pre_assistant_message: 직전 봇 발화
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


def _parse_json_content(content: str) -> dict | list:
    """마크다운 펜스를 제거하고 JSON을 파싱합니다."""
    if content.startswith("```"):
        content = content.split("```", 2)[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content.strip())


async def ask_detail_question(
    field_info: dict,
    re_ask: bool,
    pre_assistant_message: str = "",
    pre_user_message: str = "",
) -> str:
    """detail_asker 프로필로 2단계 추가 필드 질문을 생성합니다.

    Args:
        field_info: {key, label, type, enum_values?, question_hint?}
        re_ask: 재질문 여부
        pre_assistant_message: 직전 봇 발화
        pre_user_message: 직전 사용자 발화

    Returns:
        생성된 질문 문자열
    """
    payload: dict = {"field": field_info, "re_ask": re_ask}
    if pre_assistant_message:
        payload["pre_assistant_message"] = pre_assistant_message
        payload["pre_user_message"] = pre_user_message

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "detail_asker",
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


async def extract_detail_value(
    field_info: dict,
    assistant_message: str,
    user_message: str,
) -> dict:
    """detail_interviewer 프로필로 사용자 답변에서 추가 필드 값을 추출합니다.

    Args:
        field_info: {key, label, type, enum_values?}
        assistant_message: 봇이 했던 질문
        user_message: 사용자 답변

    Returns:
        {"exist": bool, "value": any | None, "re_ask": bool, "reasoning": str}
    """
    payload = {
        "field": field_info,
        "assistant_message": assistant_message,
        "user_message": user_message,
    }

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "detail_interviewer",
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                ],
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_json_content(content)


async def extract_extra_field_schemas(
    service_info: dict, user_info: dict | None = None
) -> list[dict]:
    """field_extractor 프로필로 서비스 추가 필드 스키마를 생성합니다.

    Args:
        service_info: {serv_nm, tgtr_dtl_cn, slct_crit_cn, trgter_indvdl}
        user_info: 1차 인터뷰에서 수집한 UserProfile 값 (이미 알고 있는 필드 제외용)

    Returns:
        [{"key", "label", "type", "enum_values"?, "question_hint", "reason"}]
        실패 시 빈 리스트
    """
    payload: dict = {"service": service_info}
    if user_info:
        payload["user"] = user_info

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "field_extractor",
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                ],
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        result = _parse_json_content(content)
        return result.get("extra_fields", [])
