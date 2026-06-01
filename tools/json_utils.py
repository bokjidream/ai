"""LLM 응답 JSON 파싱 유틸."""

import json
import re

_CTRL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def parse_llm_json(content: str, root: str = "{") -> dict | list:
    """마크다운 펜스 제거 + control char 정리 + strict=False raw_decode."""
    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```", 2)
        inner = parts[1]
        if inner.lower().startswith("json"):
            inner = inner[4:]
        content = inner.strip()
    content = _CTRL_CHAR_RE.sub("", content)
    start = content.find(root)
    if start == -1:
        return json.loads(content)
    obj, _ = json.JSONDecoder(strict=False).raw_decode(content, start)
    return obj
