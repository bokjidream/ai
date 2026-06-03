"""양식 처리 노드 — HWP/HWPX 자동 채우기 및 PDF 작성 가이드 생성.

노드 역할 분리:
  draft_field_extractor_node : HWP 스캔 + LLM 필드 선택 → state 커밋 (interrupt 없음)
  draft_fields_pause_node    : interrupt만 수행 → 사용자 입력 대기
  draft_writer_node          : state의 user_draft_fields 읽어 HWP/PDF 채우기
"""

import asyncio
import io
import json
import logging
import os
import re
import shutil
from pathlib import Path

import httpx
import pdfplumber
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from graph.state import AgentState, UserProfile, WelfareCandidate
from tools.hwp_filler import (
    download_hwp,
    fill_hwp,
    get_output_dir,
    scan_hwp_all,
    scan_hwp_labels,
)
from tools.json_utils import parse_llm_json
from tools.llm import get_llm
from tools.profile_utils import format_user_profile
from tools.prompt_loader import load_prompt

logger = logging.getLogger("bokjidream.draft_writer")

_SUPPORTED_HWP = {"hwp", "hwpx"}

# 신청서 파일 판별
_FORM_KEYWORDS = ("신청서", "신청양식", "서식", "application")
_GUIDE_KEYWORDS = ("안내", "매뉴얼", "지침", "가이드", "사업안내")

# 폴백 시 제외할 행정/헤더 라벨 패턴
_NON_FILLABLE_RE = re.compile(
    r"^\(\d+쪽"  # (3쪽 중 1쪽)
    r"|^처리기간"
    r"|^별도안내"
    r"|^수수료"
    r"|^처리\s*절차"
    r"|^작성방법"
    r"|^유\s*의\s*사\s*항"
    r"|^안내사항"
    r"|^유의사항"
    r"|^\["  # [   ] 체크박스 텍스트
    r"|^※"  # 주석
    r"|^\d+\."  # 숫자 섹션 번호
    r"|주민등록번호"  # 개인정보 보호 — 절대 묻지 않음
    r"|주민번호"
)

_EXTRA_FORM_MARKER_RE = re.compile(
    r"^서식\s*[2-9]|^서식\s*[1-9][0-9]|^별지|^부록|^첨부"
)


def _truncate_to_main_form(labels: list[dict]) -> list[dict]:
    """서식2 이후(위임장·이의신청서 등 부속서식) 라벨을 제거하고 서식1만 반환."""
    result = []
    for item in labels:
        if _EXTRA_FORM_MARKER_RE.search(item["id"]):
            break
        result.append(item)
    return result


# 1순위 — 신청자 본인 정보 키워드 (코드에서 직접 선택 + 폴백 공용)
_TIER1_KEYWORDS = [
    "성명",
    "이름",
    "전화번호",
    "휴대전화",
    "휴대폰",
    "핸드폰",
    "연락처",
    "주소",
    "전자우편",
    "이메일",
    "계좌번호",
    "금융기관명",
    "금융기관",
    "은행명",
    "예금주",
]

_LLM_MAX_RETRY = int(os.getenv("LLM_MAX_RETRY", "2"))

_SECTION_APPLICANT = ("대상자", "신청자", "신청인", "본인", "지급계좌")
_SECTION_EMERGENCY = ("긴급연락처", "보호자", "가족", "연락인")


def _section_rank(label: str) -> int:
    """섹션 우선순위: 신청자(0) → 서비스 고유(1) → 긴급연락처/보호자(2)."""
    if any(k in label for k in _SECTION_APPLICANT):
        return 0
    if any(k in label for k in _SECTION_EMERGENCY):
        return 2
    return 1


_HWP_DOWNLOAD_RETRIES = int(os.getenv("HWP_DOWNLOAD_RETRIES", "4"))
_DRAFT_FIELD_LIMIT = int(os.getenv("DRAFT_FIELD_LIMIT", "8"))


def _is_application_form(title: str) -> bool:
    t = title.lower()
    if any(k in t for k in _FORM_KEYWORDS):
        return True
    if any(k in t for k in _GUIDE_KEYWORDS):
        return False
    return True


def _is_fillable_label(label_id: str) -> bool:
    """폴백 선택 시 행정/헤더 라벨 여부 판별."""
    return not _NON_FILLABLE_RE.search(label_id)


def _fallback_fields(all_labels: list[dict]) -> list[dict]:
    """LLM 선택 완전 실패 시 _TIER1_KEYWORDS 우선순위로 폴백 필드를 반환."""
    fillable = [item for item in all_labels if _is_fillable_label(item["id"])]
    if fillable:
        fillable.sort(
            key=lambda item: next(
                (i for i, kw in enumerate(_TIER1_KEYWORDS) if kw in item["id"]),
                len(_TIER1_KEYWORDS),
            )
        )
        return [
            {"id": item["id"], "label": item["label"], "type": "text"}
            for item in fillable[:_DRAFT_FIELD_LIMIT]
        ]
    return [
        {"id": kw, "label": kw, "type": "text"}
        for kw in _TIER1_KEYWORDS[:_DRAFT_FIELD_LIMIT]
    ]


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name)[:50]


def _get_test_fixture_forms() -> list[dict]:
    """SKIP_INTERVIEW 테스트 모드용 로컬 fixture 반환."""
    fixture_path = (
        Path(__file__).parent.parent
        / "tests"
        / "fixtures"
        / "응급안전안심서비스_신청서.hwpx"
    )
    if fixture_path.exists():
        return [
            {
                "title": "테스트 신청서 (응급안전안심서비스)",
                "url": f"file://{fixture_path.resolve()}",
                "file_type": "hwpx",
            }
        ]
    return []


# ── LLM 필드 선택 ─────────────────────────────────────────────────────────────


def _normalize_label(s: str) -> str:
    """라벨 비교용 정규화: 구두점·특수문자 제거 후 공백 정리, 소문자 변환.

    "신청인 - 성명" → "신청인 성명"
    "신청인-성명"   → "신청인 성명"
    """
    s = re.sub(r"[\-_·•·\(\)\[\]]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()


def _fuzzy_lookup(s: str, label_by_display: dict[str, dict]) -> dict | None:
    """정확 일치 → 정규화 일치 순으로 라벨 매핑을 찾는다."""
    if s in label_by_display:
        return label_by_display[s]
    norm_s = _normalize_label(s)
    for key, item in label_by_display.items():
        if _normalize_label(key) == norm_s:
            return item
    return None


def _pick_tier1(labels: list[dict]) -> tuple[list[dict], list[dict]]:
    """_TIER1_KEYWORDS 기반으로 1순위 필드를 코드에서 직접 선택.

    전화번호 계열(전화번호·휴대전화·연락처)은 하나만 포함한다.
    반환: (tier1 목록, 나머지 목록)
    """
    _PHONE_KEYWORDS = {"전화번호", "휴대전화", "휴대폰", "핸드폰", "연락처"}
    tier1: list[dict] = []
    rest: list[dict] = []
    seen_ids: set[str] = set()
    phone_included = False

    for item in labels:
        label_id = item["id"]
        matched_kw = next((kw for kw in _TIER1_KEYWORDS if kw in label_id), None)
        if matched_kw:
            if matched_kw in _PHONE_KEYWORDS:
                if phone_included:
                    rest.append(item)
                    continue
                phone_included = True
            if label_id not in seen_ids:
                seen_ids.add(label_id)
                tier1.append(item)
        else:
            rest.append(item)

    if len(tier1) > _DRAFT_FIELD_LIMIT:
        rest = tier1[_DRAFT_FIELD_LIMIT:] + rest
        tier1 = tier1[:_DRAFT_FIELD_LIMIT]
    return tier1, rest


async def _select_fields_with_llm(
    serv_nm: str,
    form_title: str,
    all_labels: list[dict],
    user_info: str,
) -> list[dict]:
    """1순위는 코드에서 직접 선택, 남은 슬롯만 LLM이 2순위로 채운다.

    all_labels: [{"id": "원본라벨", "label": "섹션 - 원본라벨"}, ...]
    반환값도 동일 구조. 실패 시 tier1만 반환.
    """
    fillable = [item for item in all_labels if _is_fillable_label(item["id"])]
    tier1, rest = _pick_tier1(fillable)

    remaining_slots = _DRAFT_FIELD_LIMIT - len(tier1)

    tier2: list[dict] = []
    if remaining_slots > 0 and rest:
        label_by_display = {item["label"]: item for item in fillable}
        labels_text = "\n".join(f"- {item['label']}" for item in rest)
        already_selected = "\n".join(f"- {item['label']}" for item in tier1) or "(없음)"
        prompt_template = load_prompt("draft_field_selector")
        prompt = prompt_template.format(
            serv_nm=serv_nm,
            form_title=form_title,
            form_labels=labels_text,
            user_info=user_info,
            remaining_slots=remaining_slots,
            already_selected=already_selected,
        )
        llm = get_llm()
        last_err: Exception | None = None
        for attempt in range(1, _LLM_MAX_RETRY + 1):
            try:
                response = await llm.ainvoke(prompt)
                content = response.content.strip()
                if not content:
                    raise ValueError("LLM이 빈 응답 반환")
                selected = parse_llm_json(content, root="[")
                if not isinstance(selected, list):
                    raise ValueError(f"배열이 아닌 응답: {type(selected)}")
                tier1_ids = {item["id"] for item in tier1}
                seen: set[str] = set()
                for s in selected:
                    if not isinstance(s, str):
                        continue
                    item = _fuzzy_lookup(s, label_by_display)
                    if item and item["id"] not in tier1_ids and item["id"] not in seen:
                        seen.add(item["id"])
                        tier2.append(item)
                        if len(tier2) >= remaining_slots:
                            break
                break
            except Exception as e:
                last_err = e
                logger.warning(
                    "[draft_writer] LLM 2순위 선택 실패 (시도 %d/%d): %s",
                    attempt,
                    _LLM_MAX_RETRY,
                    e,
                )
        else:
            if last_err is not None:
                logger.warning("[draft_writer] LLM 2순위 선택 최종 실패: %s", last_err)

    result = tier1 + tier2
    logger.info(
        "[draft_writer] LLM 필드 선택 %d개: %s",
        len(result),
        [v["label"] for v in result],
    )
    return result


# ── HWP/HWPX 채우기 ───────────────────────────────────────────────────────────


async def _generate_hwp_field_mapping(
    serv_nm: str,
    application_method: str,
    form_title: str,
    user_info: str,
    form_labels: list[str],
) -> dict[str, str]:
    """LLM으로 HWP 필드 매핑 JSON 생성. 실패 시 빈 dict.

    행정/헤더 라벨을 제거하고 최대 60개만 LLM에 전달해 JSON 오류 방지.
    실패 시 _LLM_MAX_RETRY회 재시도.
    """
    # 행정/헤더 라벨 제거 후 최대 60개
    filtered = [lbl for lbl in form_labels if _is_fillable_label(lbl)][:60]
    labels_text = (
        ", ".join(f'"{lbl}"' for lbl in filtered)
        if filtered
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
    last_err: Exception | None = None
    for attempt in range(1, _LLM_MAX_RETRY + 1):
        try:
            response = await llm.ainvoke(prompt)
            content = response.content.strip()
            result = parse_llm_json(content)
            if not isinstance(result, dict):
                raise ValueError(f"dict가 아닌 응답: {type(result)}")
            return result
        except Exception as e:
            last_err = e
            logger.warning(
                "[draft_writer] LLM HWP 필드 매핑 실패 (시도 %d/%d): %s",
                attempt,
                _LLM_MAX_RETRY,
                e,
            )
    logger.warning("[draft_writer] LLM HWP 필드 매핑 최종 실패: %s", last_err)
    return {}


async def _process_hwp(
    form: dict,
    index: int,
    serv_nm: str,
    application_method: str,
    user_info: str,
    output_dir: Path,
    thread_id: str,
    user_draft_fields: dict[str, str] | None = None,
    predownloaded_path: Path | None = None,
    pre_scanned_labels: list[str] | None = None,
) -> dict:
    """HWP/HWPX: 다운로드(또는 scan_temp 재사용) → LLM 필드 매핑 → fill_hwp.js 실행."""
    title = form.get("title", f"form_{index}")
    url = form.get("url", "")
    file_type = form.get("file_type", "hwp")
    title_base = title
    for _ext in (".hwp", ".hwpx", ".pdf"):
        if title_base.lower().endswith(_ext):
            title_base = title_base[: -len(_ext)]
            break
    safe_name = f"{index:02d}_{_sanitize_filename(title_base)}.{file_type}"
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

        if predownloaded_path and predownloaded_path.exists():
            # extractor가 남긴 scan_temp 재사용 — 다운로드 생략
            shutil.move(str(predownloaded_path), raw_path)
            logger.debug(
                "[draft_writer] scan_temp 재사용 — 다운로드 생략: %s", raw_path.name
            )
        else:
            for _dl_attempt in range(1, _HWP_DOWNLOAD_RETRIES + 1):
                try:
                    await download_hwp(url, raw_path)
                    break
                except Exception as _dl_err:
                    if _dl_attempt == _HWP_DOWNLOAD_RETRIES:
                        raise
                    logger.warning(
                        "[draft_writer] raw 다운로드 실패 (시도 %d/%d) — 재시도: %s",
                        _dl_attempt,
                        _HWP_DOWNLOAD_RETRIES,
                        _dl_err,
                    )
                    await asyncio.sleep(2 * _dl_attempt)

        if pre_scanned_labels is not None:
            form_labels = pre_scanned_labels
            logger.debug("[draft_writer] 스캔 캐시 재사용 — %d개", len(form_labels))
        else:
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
        if not isinstance(field_mapping, dict):
            logger.warning(
                "[draft_writer] LLM 매핑이 dict가 아님 (%s) — 빈 dict 사용",
                type(field_mapping),
            )
            field_mapping = {}

        if user_draft_fields:
            field_mapping.update(user_draft_fields)
            logger.debug(
                "[draft_writer] user_draft_fields %d개 병합: %s",
                len(user_draft_fields),
                list(user_draft_fields.keys()),
            )

        if not field_mapping:
            raw_path.rename(filled_path)
            entry["status"] = "skipped"
            entry["error"] = "LLM 필드 매핑 결과 없음"
        else:
            logger.debug(
                "[draft_writer] fill_hwp 호출 — mapping keys: %s",
                list(field_mapping.keys()),
            )
            result = await fill_hwp(raw_path, filled_path, field_mapping)
            logger.info("[draft_writer] %s — 치환 %d건", title, result.get("count", 0))
            entry["status"] = "success"
            raw_path.unlink(missing_ok=True)

    except Exception as e:
        logger.warning("[draft_writer] HWP 처리 실패 (%s): %s", title, e)
        if raw_path.exists():
            try:
                shutil.copy2(raw_path, filled_path)
                raw_path.unlink(missing_ok=True)
                entry["status"] = "skipped"
                entry["error"] = f"자동 채우기 실패 (원본 제공): {e}"
                entry["user_inputs"] = user_draft_fields or {}
            except Exception:
                raw_path.unlink(missing_ok=True)
                entry["error"] = str(e)
        else:
            entry["error"] = str(e)

    return entry


# ── PDF 처리 ─────────────────────────────────────────────────────────────────

_BLANK_PATTERNS = [
    r"_{3,}",
    r"\(\s+\)",
    r"□",
    r"○",
]


def _has_blanks(text: str) -> bool:
    return any(re.search(p, text) for p in _BLANK_PATTERNS)


def _extract_field_labels(text: str) -> list[str]:
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
    """PDF: pdfplumber 파싱 → 빈칸 추출 → LLM 가이드. 빈칸 없으면 None."""
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


async def draft_field_extractor_node(state: AgentState, config: RunnableConfig) -> dict:
    """HWP 스캔 + LLM 필드 선택 → state 커밋 (interrupt 없음).

    이 노드는 한 번만 실행되고 결과를 state에 저장한다.
    사용자 입력 대기(interrupt)는 draft_fields_pause_node가 담당하므로
    LangGraph resume 시 이 노드는 재실행되지 않는다.
    """
    thread_id: str = config["configurable"].get("thread_id", "unknown")
    selected: WelfareCandidate = state["selected_service"]
    profile: UserProfile = state["user_profile"]

    forms = selected.application_forms or []

    hwp_forms = [f for f in forms if f.get("file_type", "").lower() in _SUPPORTED_HWP]
    hwp_form = next(
        (f for f in hwp_forms if _is_application_form(f.get("title", ""))), None
    )

    if not hwp_form:
        return {
            "draft_extracted_fields": [],
            "draft_form_title": "",
            "draft_scan_path": "",
        }

    form_title = hwp_form.get("title", "신청서")
    output_dir = get_output_dir(thread_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    scan_ext = hwp_form.get("file_type", "hwp").lower()
    scan_path = output_dir / f"scan_temp.{scan_ext}"

    priority_fields: list[dict] = []
    all_labels: list[dict] = []
    scan_labels: list[str] = []

    try:
        for _dl_attempt in range(1, _HWP_DOWNLOAD_RETRIES + 1):
            try:
                await download_hwp(hwp_form["url"], scan_path)
                break
            except Exception as _dl_err:
                if _dl_attempt == _HWP_DOWNLOAD_RETRIES:
                    raise
                logger.warning(
                    "[draft_field_extractor] 다운로드 실패 (시도 %d/%d) — 재시도: %s",
                    _dl_attempt,
                    _HWP_DOWNLOAD_RETRIES,
                    _dl_err,
                )
                await asyncio.sleep(2 * _dl_attempt)

        # 한 번의 스캔으로 text_labels(필드 선택용) + labels(매핑용) 동시 획득
        scan_data = await scan_hwp_all(scan_path)
        scan_labels = scan_data.get("labels", [])  # writer가 재사용

        raw_text_labels: list = scan_data.get("text_labels", [])
        all_labels_raw = [
            {
                "id": (item.get("id", "") if isinstance(item, dict) else item),
                "label": (
                    item.get("label", item.get("id", ""))
                    if isinstance(item, dict)
                    else item
                ),
            }
            for item in raw_text_labels
        ]
        all_labels = _truncate_to_main_form(all_labels_raw)
        logger.info(
            "[draft_field_extractor] 스캔 라벨 %d개: %s",
            len(all_labels),
            [item["label"] for item in all_labels],
        )
        # scan_path를 삭제하지 않고 보존 → draft_writer_node에서 raw로 재사용

        if all_labels:
            user_info = format_user_profile(profile)
            selected_labels = await _select_fields_with_llm(
                serv_nm=selected.serv_nm,
                form_title=form_title,
                all_labels=all_labels,
                user_info=user_info,
            )
            priority_fields = [
                {"id": item["id"], "label": item["label"], "type": "text"}
                for item in selected_labels
            ]
    except Exception as e:
        logger.warning("[draft_field_extractor] 스캔 실패: %s", e, exc_info=True)
        scan_path.unlink(missing_ok=True)
        scan_path = None  # 실패 시 재사용 불가

    if not priority_fields:
        priority_fields = _fallback_fields(all_labels)
        if priority_fields:
            logger.warning(
                "[draft_field_extractor] LLM 선택 실패 — 폴백 %d개: %s",
                len(priority_fields),
                [p["label"] for p in priority_fields],
            )

    logger.info(
        "[draft_field_extractor] 필드 %d개 추출: %s",
        len(priority_fields),
        [p["label"] for p in priority_fields],
    )
    return {
        "draft_extracted_fields": priority_fields,
        "draft_form_title": form_title,
        "draft_scan_path": str(scan_path) if scan_path and scan_path.exists() else "",
        "draft_scan_labels": scan_labels,
    }


async def draft_fields_pause_node(state: AgentState) -> dict:
    """사용자 입력 대기 노드 (interrupt만 수행).

    draft_field_extractor_node가 state에 커밋한 draft_extracted_fields를 읽어
    interrupt로 웹에 전달한다.

    LangGraph resume 시 이 노드가 재실행되어도:
    - state에서 draft_extracted_fields를 그대로 읽으므로 스캔/LLM 재호출 없음
    - interrupt()가 즉시 사용자 입력값을 반환
    """
    fields: list[dict] = state.get("draft_extracted_fields", [])
    if not fields:
        # HWP 서식 없음 — 입력 없이 통과
        return {"user_draft_fields": {}}

    form_title: str = state.get("draft_form_title", "신청서")
    user_values_json: str = interrupt(
        {
            "type": "draft_fields",
            "fields": fields,
            "form_title": form_title,
        }
    )

    try:
        user_draft_fields: dict[str, str] = (
            json.loads(user_values_json) if user_values_json else {}
        )
    except Exception:
        user_draft_fields = {}

    logger.debug(
        "[draft_fields_pause] 사용자 입력 %d개: %s",
        len(user_draft_fields),
        list(user_draft_fields.keys()),
    )
    return {"user_draft_fields": user_draft_fields}


async def draft_writer_node(state: AgentState, config: RunnableConfig) -> dict:
    """application_forms를 파일 타입별로 채우는 노드.

    - HWP/HWPX: state의 user_draft_fields를 LLM 매핑에 병합 후 자동 채우기
    - PDF: 빈칸 추출 → LLM 가이드 (status: guide_only)
    - 기타: skip
    """
    thread_id: str = config["configurable"].get("thread_id", "unknown")
    selected: WelfareCandidate = state["selected_service"]
    profile: UserProfile = state["user_profile"]
    user_draft_fields: dict[str, str] = state.get("user_draft_fields", {})

    forms = selected.application_forms or []

    if not forms:
        logger.info("[draft_writer] application_forms 없음 — skip")
        return {"filled_forms": []}

    user_info = format_user_profile(profile)
    output_dir = get_output_dir(thread_id)

    # extractor가 남긴 scan_temp + 스캔 캐시 — 첫 번째 신청서 HWP에만 적용
    scan_path_str: str = state.get("draft_scan_path", "")
    scan_cache: Path | None = Path(scan_path_str) if scan_path_str else None
    cached_labels: list[str] = state.get("draft_scan_labels", [])

    # scan_cache를 받을 form 결정 (extractor와 동일 로직)
    hwp_forms = [f for f in forms if f.get("file_type", "").lower() in _SUPPORTED_HWP]
    scanned_form = next(
        (f for f in hwp_forms if _is_application_form(f.get("title", ""))), None
    )

    # 파일 타입별 코루틴 수집 — 원본 순서(index)를 키로 유지
    tasks: dict[int, object] = {}
    for i, form in enumerate(forms):
        file_type = form.get("file_type", "").lower()

        if file_type in _SUPPORTED_HWP and _is_application_form(form.get("title", "")):
            is_scanned = form is scanned_form
            tasks[i] = _process_hwp(
                form=form,
                index=i,
                serv_nm=selected.serv_nm,
                application_method=selected.application_method or "",
                user_info=user_info,
                output_dir=output_dir,
                thread_id=thread_id,
                user_draft_fields=user_draft_fields,
                predownloaded_path=scan_cache if is_scanned else None,
                pre_scanned_labels=(
                    cached_labels if is_scanned and cached_labels else None
                ),
            )
        elif file_type == "pdf" and _is_application_form(form.get("title", "")):
            tasks[i] = _process_pdf(
                form=form,
                index=i,
                serv_nm=selected.serv_nm,
                user_info=user_info,
            )
        else:
            logger.debug("[draft_writer] 지원하지 않는 파일 타입 — skip: %s", file_type)

    if not tasks:
        return {"filled_forms": []}

    # HWP/PDF 병렬 실행
    sorted_indices = sorted(tasks)
    results = await asyncio.gather(*[tasks[i] for i in sorted_indices])
    filled = [r for r in results if r is not None]

    return {"filled_forms": filled}
