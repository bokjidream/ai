"""양식 처리 노드 — HWP/HWPX 자동 채우기 및 PDF 작성 가이드 생성."""

import io
import json
import logging
import re
from pathlib import Path

import httpx
import pdfplumber
from langchain_core.runnables import RunnableConfig

from graph.state import AgentState, UserProfile, WelfareCandidate
from tools.hwp_filler import download_hwp, fill_hwp, get_output_dir, scan_hwp_labels
from tools.llm import get_llm
from tools.prompt_loader import load_prompt

logger = logging.getLogger("bokjidream.draft_writer")

_SUPPORTED_HWP = {"hwp", "hwpx"}


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


# ── HWP/HWPX 처리 ────────────────────────────────────────────────────────────


async def _generate_hwp_field_mapping(
    serv_nm: str,
    application_method: str,
    form_title: str,
    user_info: str,
    form_labels: list[str],
) -> dict[str, str]:
    """LLM으로 HWP 필드 매핑 JSON을 생성합니다. 실패 시 빈 dict 반환."""
    labels_text = (
        ", ".join(f'"{lbl}"' for lbl in form_labels)
        if form_labels
        else "(추출 실패 — 일반적인 신청서 필드명을 추론하세요)"
    )

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
        if content.startswith("```"):
            parts = content.split("```", 2)
            inner = parts[1]
            if inner.lower().startswith("json"):
                inner = inner[4:]
            content = inner.strip()
        return json.loads(content)
    except Exception as e:
        logger.warning("[draft_writer] LLM HWP 필드 매핑 실패: %s", e)
        return {}


async def _process_hwp(
    form: dict,
    index: int,
    serv_nm: str,
    application_method: str,
    user_info: str,
    output_dir: Path,
    thread_id: str,
) -> dict:
    """HWP/HWPX: 다운로드 → LLM 필드 매핑 → Node.js fill_hwp.js 실행."""
    title = form.get("title", f"form_{index}")
    url = form.get("url", "")
    file_type = form.get("file_type", "hwp")
    safe_name = f"{index:02d}_{_sanitize_filename(title)}.{file_type}"
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
        output_dir.mkdir(parents=True, exist_ok=True)
        await download_hwp(url, raw_path)
        form_labels = await scan_hwp_labels(raw_path)
        logger.debug(
            "[draft_writer] 스캔된 라벨 %d개: %s", len(form_labels), form_labels
        )

        field_mapping = await _generate_hwp_field_mapping(
            serv_nm=serv_nm,
            application_method=application_method,
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
            logger.info("[draft_writer] %s — 치환 %d건", title, result.get("count", 0))
            entry["status"] = "success"
            raw_path.unlink(missing_ok=True)

    except Exception as e:
        logger.warning("[draft_writer] HWP 처리 실패 (%s): %s", title, e)
        entry["error"] = str(e)
        if raw_path.exists():
            raw_path.unlink(missing_ok=True)

    return entry


# ── PDF 처리 ─────────────────────────────────────────────────────────────────

_BLANK_PATTERNS = [
    r"_{3,}",  # 밑줄 3개 이상
    r"\(\s+\)",  # 괄호 빈칸
    r"□",  # 체크박스
    r"○",  # 원형 체크박스
]


def _has_blanks(text: str) -> bool:
    return any(re.search(p, text) for p in _BLANK_PATTERNS)


def _extract_field_labels(text: str) -> list[str]:
    """PDF 텍스트에서 빈칸 앞 라벨 후보를 추출합니다 (최대 20개)."""
    labels = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.{1,15}?)[\s]*[:：]?\s*_{2,}", line)
        if m:
            labels.append(m.group(1).strip())
        m2 = re.match(r"^[□○]\s+(.{1,20})", line)
        if m2:
            labels.append(m2.group(1).strip())
    return list(dict.fromkeys(labels))[:20]


async def _generate_pdf_guide(
    serv_nm: str,
    form_title: str,
    user_info: str,
    fields: list[str],
    pdf_text: str,
) -> str:
    """LLM으로 PDF 양식 작성 가이드 텍스트를 생성합니다."""
    fields_text = (
        ", ".join(f'"{f}"' for f in fields) if fields else "(항목 자동 추출 불가)"
    )
    prompt = (
        f"당신은 복지 서비스 신청서 작성을 도와주는 안내 도우미입니다.\n\n"
        f"서비스명: {serv_nm}\n"
        f"양식명: {form_title}\n"
        f"사용자 정보:\n{user_info}\n\n"
        "아래 PDF 양식의 주요 작성 항목을 참고하여 "
        "사용자가 각 항목을 어떻게 작성해야 하는지 안내하세요.\n"
        f"주요 항목: {fields_text}\n\n"
        f"PDF 텍스트 일부:\n{pdf_text[:1000]}\n\n"
        "작성 규칙:\n"
        "- 각 항목별로 사용자 정보에 맞춰 작성 예시를 제시하세요.\n"
        "- 모르는 정보는 '[직접 입력]'으로 표시하세요.\n"
        "- 간결하고 명확하게 작성하세요."
    )
    llm = get_llm()
    try:
        response = await llm.ainvoke(prompt)
        return response.content
    except Exception as e:
        logger.warning("[draft_writer] PDF 가이드 생성 실패: %s", e)
        return (
            f"'{form_title}' PDF 양식의 작성 가이드를 생성하지 못했습니다."
            " 직접 작성해 주세요."
        )


async def _process_pdf(
    form: dict,
    index: int,
    serv_nm: str,
    user_info: str,
) -> dict | None:
    """PDF: pdfplumber 파싱 → 빈칸 추출 → LLM 가이드 생성.

    빈칸이 없는 안내서류이면 None 반환 (skip).
    """
    title = form.get("title", f"form_{index}")
    url = form.get("url", "")

    entry: dict = {
        "original_title": title,
        "original_url": url,
        "file_type": "pdf",
        "status": "failed",
        "error": None,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            pdf_bytes = resp.content

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        if not _has_blanks(text):
            logger.info("[draft_writer] PDF 빈칸 없음(안내서류) — skip: %s", title)
            return None

        fields = _extract_field_labels(text)
        guide_text = await _generate_pdf_guide(
            serv_nm=serv_nm,
            form_title=title,
            user_info=user_info,
            fields=fields,
            pdf_text=text,
        )

        entry["status"] = "guide_only"
        entry["guide_text"] = guide_text

    except Exception as e:
        logger.warning("[draft_writer] PDF 처리 실패 (%s): %s", title, e)
        entry["error"] = str(e)

    return entry


# ── 노드 진입점 ───────────────────────────────────────────────────────────────


async def draft_writer_node(state: AgentState, config: RunnableConfig) -> dict:
    """application_forms를 파일 타입별로 처리합니다.

    - HWP/HWPX: 자동 채우기 → status "success" / "skipped" / "failed"
    - PDF: 빈칸 추출 → LLM 가이드 → status "guide_only" (빈칸 없으면 skip)
    - 기타: skip
    """
    thread_id: str = config["configurable"].get("thread_id", "unknown")
    selected: WelfareCandidate = state["selected_service"]
    profile: UserProfile = state["user_profile"]

    forms = selected.application_forms or []
    if not forms:
        logger.info("[draft_writer] application_forms 없음 — skip")
        return {"filled_forms": []}

    user_info = _build_user_info(profile)
    output_dir = get_output_dir(thread_id)

    filled: list[dict] = []

    for i, form in enumerate(forms):
        file_type = form.get("file_type", "").lower()

        if file_type in _SUPPORTED_HWP:
            entry = await _process_hwp(
                form=form,
                index=i,
                serv_nm=selected.serv_nm,
                application_method=selected.application_method or "",
                user_info=user_info,
                output_dir=output_dir,
                thread_id=thread_id,
            )
            filled.append(entry)

        elif file_type == "pdf":
            entry = await _process_pdf(
                form=form,
                index=i,
                serv_nm=selected.serv_nm,
                user_info=user_info,
            )
            if entry is not None:
                filled.append(entry)

        else:
            logger.debug("[draft_writer] 지원하지 않는 파일 타입 — skip: %s", file_type)

    return {"filled_forms": filled}
