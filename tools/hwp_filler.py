"""HWP 양식 다운로드 및 Node.js 스크립트 기반 자동 채우기 도구."""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

logger = logging.getLogger("bokjidream.hwp_filler")

_DOWNLOAD_TIMEOUT = float(os.getenv("HWP_DOWNLOAD_TIMEOUT", "30.0"))
_NODE_TIMEOUT = float(os.getenv("HWP_NODE_TIMEOUT", "60.0"))
_FILLED_FORMS_DIR = Path(os.getenv("FILLED_FORMS_DIR", "./filled_forms"))
_NODE_BINARY = os.getenv("NODE_BINARY", "node")
_FILL_HWP_SCRIPT = Path(__file__).parent.parent / "scripts" / "fill_hwp.js"


async def download_hwp(url: str, dest: Path) -> None:
    """URL에서 HWP/HWPX 파일을 다운로드하여 dest 경로에 저장합니다.

    file:// 프로토콜은 로컬 파일 복사로 처리합니다 (테스트 fixture 지원).
    """
    if url.startswith("file://"):
        shutil.copy2(url[7:], dest)
        logger.debug("HWP 로컬 복사 완료: %s → %s", url, dest)
        return
    async with httpx.AsyncClient(
        timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.content

    # HWP(OLE): D0 CF 11 E0 / HWPX(ZIP): 50 4B 03 04
    _VALID_MAGIC = (b"\xd0\xcf\x11\xe0", b"PK\x03\x04")
    if len(content) < 1000 or not any(content.startswith(m) for m in _VALID_MAGIC):
        raise ValueError(f"유효하지 않은 HWP 파일 ({len(content)} bytes, url={url})")
    dest.write_bytes(content)
    logger.debug("HWP 다운로드 완료: %s → %s", url, dest)


def _run_node_sync(args: list[str], timeout: float) -> bytes:
    """Node.js fill_hwp.js를 동기적으로 실행하고 stdout을 반환합니다.

    Windows SelectorEventLoop에서 asyncio.create_subprocess_exec가 NotImplementedError를
    던지는 문제를 우회하기 위해 subprocess.run (동기)을 사용합니다.
    """
    result = subprocess.run(
        [_NODE_BINARY, str(_FILL_HWP_SCRIPT), *args],
        capture_output=True,
        timeout=timeout,
    )
    stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        raise RuntimeError(f"fill_hwp.js 종료 코드 {result.returncode}: {stderr_text}")
    if stderr_text:
        for line in stderr_text.splitlines():
            logger.debug("[hwp_filler] node stderr: %s", line)
    return result.stdout


async def _run_node(args: list[str], timeout: float) -> bytes:
    """Node.js fill_hwp.js를 실행하고 stdout을 반환합니다.

    asyncio.to_thread로 동기 subprocess를 비동기 컨텍스트에서 실행합니다.
    """
    return await asyncio.to_thread(_run_node_sync, args, timeout)


async def _scan_hwp_raw(input_path: Path) -> dict:
    """--scan 결과 raw dict 반환. 실패 시 빈 dict."""
    try:
        stdout = await _run_node(["--scan", str(input_path)], _NODE_TIMEOUT)
        data = json.loads(stdout.decode("utf-8"))
        if not data.get("ok", True):
            logger.warning("[hwp_filler] 라벨 스캔 실패: %s", data.get("error", ""))
            return {}
        return data
    except Exception as e:
        logger.warning("[hwp_filler] 라벨 스캔 실패: %s", e)
        return {}


async def scan_hwp_all(input_path: Path) -> dict:
    """HWP/HWPX를 한 번만 스캔하여 labels(전체)와 text_labels(텍스트 전용)를 함께 반환.

    반환 형식: {"labels": [...], "text_labels": [...]}
    실패 시 빈 dict를 반환합니다.
    """
    return await _scan_hwp_raw(input_path)


async def scan_hwp_labels(input_path: Path) -> list[str]:
    """HWP/HWPX 표 셀에서 전체 라벨 후보 목록을 반환합니다 (체크박스 포함).

    실패 시 빈 리스트를 반환합니다.
    """
    data = await _scan_hwp_raw(input_path)
    return data.get("labels", [])


async def scan_hwp_text_labels(input_path: Path) -> list[dict]:
    """HWP/HWPX 표 셀에서 텍스트 입력 필드만 반환합니다 (체크박스 행 제외).

    반환 형식: [{"id": "원본라벨", "label": "섹션 - 원본라벨"}, ...]
    실패 시 빈 리스트를 반환합니다.
    """
    data = await _scan_hwp_raw(input_path)
    raw = data.get("text_labels", [])
    # JS가 {id, label} 객체 배열을 반환하지만, 구버전 호환을 위해 문자열도 처리
    result = []
    for item in raw:
        if isinstance(item, dict):
            result.append(
                {
                    "id": item.get("id", ""),
                    "label": item.get("label", item.get("id", "")),
                }
            )
        elif isinstance(item, str):
            result.append({"id": item, "label": item})
    return result


async def fill_hwp(
    input_path: Path,
    output_path: Path,
    field_mapping: dict[str, str],
) -> dict:
    """Node.js fill_hwp.js를 subprocess로 호출해 HWP 필드를 채웁니다.

    Returns:
        {"ok": bool, "count": int, "results": list}
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False
    ) as tmp:
        json.dump(field_mapping, tmp, ensure_ascii=False)
        tmp_path = tmp.name

    try:
        stdout = await _run_node(
            [str(input_path), str(output_path), tmp_path], _NODE_TIMEOUT
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    raw = stdout.decode("utf-8", errors="replace")
    logger.debug("[hwp_filler] fill stdout: %.200s", raw)
    result = json.loads(raw)
    if not result.get("ok", True):
        raise ValueError(result.get("error", "HWP 처리 실패"))
    return result


def get_output_dir(thread_id: str) -> Path:
    """thread_id별 출력 디렉터리 경로를 반환합니다 (디렉터리를 생성하지 않음)."""
    return _FILLED_FORMS_DIR / thread_id


def get_filled_forms_dir() -> Path:
    """환경변수에 설정된 FILLED_FORMS_DIR을 반환합니다."""
    return _FILLED_FORMS_DIR
