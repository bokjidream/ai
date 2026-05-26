"""HWP 양식 다운로드 및 Node.js 스크립트 기반 자동 채우기 도구."""

import asyncio
import json
import logging
import os
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
    """URL에서 HWP/HWPX 파일을 다운로드하여 dest 경로에 저장합니다."""
    async with httpx.AsyncClient(
        timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    logger.debug("HWP 다운로드 완료: %s → %s", url, dest)


async def _run_node(args: list[str], timeout: float) -> bytes:
    """Node.js fill_hwp.js를 실행하고 stdout을 반환합니다."""
    proc = await asyncio.create_subprocess_exec(
        _NODE_BINARY,
        str(_FILL_HWP_SCRIPT),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as e:
        proc.kill()
        raise RuntimeError(
            f"fill_hwp.js가 {timeout}초 내에 완료되지 않았습니다."
        ) from e

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"fill_hwp.js 종료 코드 {proc.returncode}: {err_msg}")

    return stdout


async def scan_hwp_labels(input_path: Path) -> list[str]:
    """HWP/HWPX 표 셀에서 라벨 후보 텍스트 목록을 반환합니다.

    실패 시 빈 리스트를 반환합니다 (LLM이 추론 모드로 동작).
    """
    try:
        stdout = await _run_node(["--scan", str(input_path)], _NODE_TIMEOUT)
        data = json.loads(stdout.decode("utf-8"))
        return data.get("labels", [])
    except Exception as e:
        logger.warning("[hwp_filler] 라벨 스캔 실패: %s", e)
        return []


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

    return json.loads(stdout.decode("utf-8"))


def get_output_dir(thread_id: str) -> Path:
    """thread_id별 출력 디렉터리 경로를 반환합니다 (디렉터리를 생성하지 않음)."""
    return _FILLED_FORMS_DIR / thread_id


def get_filled_forms_dir() -> Path:
    """환경변수에 설정된 FILLED_FORMS_DIR을 반환합니다."""
    return _FILLED_FORMS_DIR
