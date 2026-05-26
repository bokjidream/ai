"""HWP 양식 자동 채우기 노드 — draft_writer와 report_writer 사이에 위치."""

import json
import logging
import re

from langchain_core.runnables import RunnableConfig

from graph.state import AgentState, UserProfile, WelfareCandidate
from tools.hwp_filler import download_hwp, fill_hwp, get_output_dir, scan_hwp_labels
from tools.llm import get_llm
from tools.prompt_loader import load_prompt

logger = logging.getLogger("bokjidream.form_filler")

_SUPPORTED_TYPES = {"hwp", "hwpx"}


def _build_user_info(profile: UserProfile) -> str:
    lines = []
    if profile.age is not None:
        lines.append(f"나이: {profile.age}세")
    if profile.region is not None:
        lines.append(f"주소(지역): {profile.region}")
    if profile.income_level is not None:
        lines.append(f"소득 수준: {profile.income_level.value}")
    if profile.disability is not None:
        lines.append(f"장애 여부: {'있음' if profile.disability else '없음'}")
    if profile.disability_type is not None:
        lines.append(f"장애 유형: {profile.disability_type}")
    if profile.disability_grade is not None:
        lines.append(f"장애 등급: {profile.disability_grade}")
    if profile.marital_status is not None:
        lines.append(f"혼인 상태: {profile.marital_status.value}")
    if profile.household_size is not None:
        lines.append(f"가구원 수: {profile.household_size}명")
    if profile.employment_status is not None:
        lines.append(f"취업 상태: {profile.employment_status.value}")
    if profile.housing_type is not None:
        lines.append(f"주거 유형: {profile.housing_type}")
    if profile.is_veteran is not None:
        lines.append(f"국가유공자: {'해당' if profile.is_veteran else '비해당'}")
    if profile.is_single_parent is not None:
        lines.append(f"한부모 가정: {'해당' if profile.is_single_parent else '비해당'}")
    for key, val in profile.extra_fields.items():
        lines.append(f"{key}: {val}")
    return "\n".join(lines) if lines else "수집된 사용자 정보 없음"


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name)[:50]


async def _generate_field_mapping(
    serv_nm: str,
    application_method: str,
    form_title: str,
    user_info: str,
    form_labels: list[str],
) -> dict[str, str]:
    """LLM으로 필드 매핑 JSON을 생성합니다. 실패 시 빈 dict 반환."""
    if form_labels:
        labels_text = ", ".join(f'"{lbl}"' for lbl in form_labels)
    else:
        labels_text = "(추출 실패 — 일반적인 신청서 필드명을 추론하세요)"

    prompt_template = load_prompt("form_field_mapper")
    prompt = prompt_template.format(
        serv_nm=serv_nm,
        application_method=application_method or "정보 없음",
        form_title=form_title,
        user_info=user_info,
        form_labels=labels_text,
    )
    llm = get_llm()
    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        # LLM이 마크다운 펜스를 붙이는 경우 제거
        if content.startswith("```"):
            parts = content.split("```", 2)
            content = parts[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        return json.loads(content)
    except Exception as e:
        logger.warning("[form_filler] LLM 필드 매핑 실패: %s", e)
        return {}


async def form_filler_node(state: AgentState, config: RunnableConfig) -> dict:
    """HWP 양식을 다운로드하고 사용자 정보로 자동 채웁니다.

    - application_forms에 hwp/hwpx가 없으면 즉시 skip.
    - 개별 파일 처리 실패는 graceful skip (status="failed") 후 다음 파일 처리.
    """
    thread_id: str = config["configurable"].get("thread_id", "unknown")
    selected: WelfareCandidate = state["selected_service"]
    profile: UserProfile = state["user_profile"]

    hwp_forms = [
        f
        for f in (selected.application_forms or [])
        if f.get("file_type") in _SUPPORTED_TYPES
    ]

    if not hwp_forms:
        logger.info("[form_filler] HWP/HWPX 양식 없음 — skip")
        return {"filled_forms": []}

    user_info = _build_user_info(profile)
    output_dir = get_output_dir(thread_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    filled: list[dict] = []

    for i, form in enumerate(hwp_forms):
        title = form.get("title", f"form_{i}")
        url = form.get("url", "")
        file_type = form.get("file_type", "hwp")
        safe_name = f"{i:02d}_{_sanitize_filename(title)}.{file_type}"
        raw_path = output_dir / f"raw_{safe_name}"
        filled_path = output_dir / safe_name
        download_key = f"{thread_id}/{safe_name}"

        entry: dict = {
            "original_title": title,
            "original_url": url,
            "file_type": file_type,
            "saved_path": str(filled_path),
            "download_key": download_key,
            "status": "failed",
            "error": None,
        }

        try:
            await download_hwp(url, raw_path)

            form_labels = await scan_hwp_labels(raw_path)
            logger.debug(
                "[form_filler] 스캔된 라벨 %d개: %s", len(form_labels), form_labels
            )

            field_mapping = await _generate_field_mapping(
                serv_nm=selected.serv_nm,
                application_method=selected.application_method,
                form_title=title,
                user_info=user_info,
                form_labels=form_labels,
            )

            if not field_mapping:
                raw_path.rename(filled_path)
                entry["status"] = "skipped"
                entry["error"] = "LLM 필드 매핑 결과 없음"
            else:
                result = await fill_hwp(raw_path, filled_path, field_mapping)
                logger.info(
                    "[form_filler] %s — 치환 %d건",
                    title,
                    result.get("count", 0),
                )
                entry["status"] = "success"
                raw_path.unlink(missing_ok=True)

        except Exception as e:
            logger.warning("[form_filler] 처리 실패 (%s): %s", title, e)
            entry["error"] = str(e)
            if raw_path.exists():
                raw_path.unlink(missing_ok=True)

        filled.append(entry)

    return {"filled_forms": filled}
