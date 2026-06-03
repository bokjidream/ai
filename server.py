"""복지드림 AI 에이전트 FastAPI 서버."""

from __future__ import annotations

import asyncio
import logging
import logging.config
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langgraph.types import Command
from pydantic import BaseModel

from graph.builder import build_graph
from graph.state import (
    DisabilitySeverity,
    EmploymentStatus,
    IncomeLevel,
    MaritalStatus,
    UserProfile,
    WelfareCandidate,
)
from tools.hwp_filler import get_filled_forms_dir

load_dotenv(override=True)

logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s [%(levelname)s] %(name)s | %(message)s",
                "datefmt": "%H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stderr",
            }
        },
        "loggers": {
            "bokjidream": {
                "handlers": ["console"],
                "level": os.getenv("LOG_LEVEL", "DEBUG"),
                "propagate": False,
            }
        },
    }
)

logger = logging.getLogger("bokjidream.server")

# 서버 시작 시 lifespan에서 초기화됨
graph = None
_pg_pool = None

THREAD_TTL_HOURS = 12
_CLEANUP_INTERVAL_SECS = 3600  # 1시간마다 실행


async def _setup_thread_registry(pool) -> None:
    async with pool.connection() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_last_active (
                thread_id TEXT PRIMARY KEY,
                last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


async def _touch_thread(thread_id: str) -> None:
    if _pg_pool is None:
        return
    async with _pg_pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO thread_last_active (thread_id, last_active_at)
            VALUES (%s, NOW())
            ON CONFLICT (thread_id) DO UPDATE SET last_active_at = NOW()
            """,
            (thread_id,),
        )


async def _cleanup_old_threads() -> None:
    async with _pg_pool.connection() as conn:
        cur = await conn.execute(
            "SELECT thread_id FROM thread_last_active"
            " WHERE last_active_at < NOW() - INTERVAL '%s hours'",
            (THREAD_TTL_HOURS,),
        )
        old_ids = [row[0] for row in await cur.fetchall()]
        if not old_ids:
            return
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            try:
                await conn.execute(
                    f"DELETE FROM {table} WHERE thread_id = ANY(%s)",  # noqa: S608
                    (old_ids,),
                )
            except Exception:
                logger.warning("[cleanup] %s 삭제 실패", table)
        await conn.execute(
            "DELETE FROM thread_last_active WHERE thread_id = ANY(%s)",
            (old_ids,),
        )
        logger.info("[cleanup] %d개 만료 thread 삭제 완료", len(old_ids))


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL_SECS)
        try:
            await _cleanup_old_threads()
        except Exception:
            logger.exception("[cleanup] 삭제 중 오류")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 그래프를 초기화하고, 종료 시 리소스를 정리합니다."""
    global graph, _pg_pool
    graph = await build_graph()

    cleanup_task = None
    if os.getenv("GRAPH_CHECKPOINTER") == "postgres":
        from psycopg_pool import AsyncConnectionPool

        conn_string = os.getenv("POSTGRES_CONN_STRING", "")
        _pg_pool = AsyncConnectionPool(conn_string, open=False)
        await _pg_pool.open()
        await _setup_thread_registry(_pg_pool)
        cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info(
            "[cleanup] TTL=%dh interval=%ds", THREAD_TTL_HOURS, _CLEANUP_INTERVAL_SECS
        )  # noqa: E501

    yield

    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    if _pg_pool:
        await _pg_pool.close()
    # SQLite 모드일 경우 _checkpointer_stack이 GC될 때 커넥션 자동 종료


app = FastAPI(title="BokjiDream AI Server", lifespan=lifespan)

_CORS_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")
_SERVER_ERROR_MSG = "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatResponse(BaseModel):
    """AI 서버 응답 공통 래퍼."""

    thread_id: str
    type: str
    data: dict


class MessageRequest(BaseModel):
    """POST /chat/message 요청 바디."""

    thread_id: str
    message: str


_TEST_PROFILE = UserProfile(
    age=65,
    region="서울",
    household_size=1,
    marital_status=MaritalStatus.SINGLE,
    has_children=False,
    disability=True,
    disability_severity=DisabilitySeverity.MILD,
    employment_status=EmploymentStatus.INACTIVE,
    income_level=IncomeLevel.BASIC,
)


def _initial_state() -> dict:
    skip = os.getenv("SKIP_INTERVIEW", "false").lower() == "true"
    return {
        "messages": [],
        "user_profile": _TEST_PROFILE if skip else UserProfile(),
        "initial_missing_fields": []
        if skip
        else [
            "age",
            "region",
            "household_size",
            "marital_status",
            "has_children",
            "disability",
            "employment_status",
            "income_level",
        ],
        "welfare_candidates": [],
        "selected_service": None,
        "detail_missing_fields": [],
        "final_report": "",
        "interview_current_field": None,
        "interview_last_question": "",
        "interview_last_answer": "",
        "pending_question": None,
        "detail_current_field": None,
        "detail_last_question": "",
        "detail_last_answer": "",
        "extra_field_schemas": [],
        "filled_forms": [],
        "reference_docs": [],
        "draft_extracted_fields": [],
        "draft_form_title": "",
        "draft_scan_path": "",
        "user_draft_fields": {},
    }


def _format_field(field: str, value) -> str:
    if value is None:
        return "None"
    if field == "messages":
        return f"[{len(value) if isinstance(value, list) else '?'} message(s)]"
    if field == "user_profile":
        try:
            filled = {k: v for k, v in value.model_dump().items() if v is not None}
        except AttributeError:
            return repr(value)
        return (
            "{" + ", ".join(f"{k}={v!r}" for k, v in filled.items()) + "}"
            if filled
            else "(empty)"
        )
    if field == "welfare_candidates":
        names = [
            getattr(c, "serv_nm", "?")
            for c in (value if isinstance(value, list) else [])
        ]
        return f"[{len(names)}개: {', '.join(names)}]"
    if field == "selected_service":
        return getattr(value, "serv_nm", repr(value))
    if isinstance(value, str):
        return repr(value[:50] + "..." if len(value) > 50 else value)
    return repr(value)


def _log_state_chunk(chunk: dict) -> None:
    for node_name, updates in chunk.items():
        if node_name == "__interrupt__" or not isinstance(updates, dict):
            return
        lines = [f"  {f}: {_format_field(f, v)}" for f, v in updates.items()]
        logger.debug(
            "[node=%s] %d개 필드 업데이트:\n%s", node_name, len(lines), "\n".join(lines)
        )


def _interview_response(thread_id: str, interrupt_value: dict, state) -> ChatResponse:
    missing = (
        state.values.get("initial_missing_fields")
        or state.values.get("detail_missing_fields")
        or []
    )
    return ChatResponse(
        thread_id=thread_id,
        type="interview",
        data={"question": interrupt_value["question"], "missing_fields": missing},
    )


def _service_select_response(
    thread_id: str, interrupt_value: dict, state
) -> ChatResponse:
    candidates: list[WelfareCandidate] = state.values.get("welfare_candidates", [])
    return ChatResponse(
        thread_id=thread_id,
        type="service_select",
        data={
            "candidates": interrupt_value["candidates"],
            "welfare_candidates": [c.model_dump() for c in candidates],
            "error": interrupt_value.get("error"),
        },
    )


def _service_detail_response(thread_id: str, state) -> ChatResponse:
    selected: WelfareCandidate | None = state.values.get("selected_service")
    candidates: list[WelfareCandidate] = state.values.get("welfare_candidates", [])
    return ChatResponse(
        thread_id=thread_id,
        type="service_detail",
        data={
            "selected_service": selected.model_dump() if selected else None,
            "welfare_candidates": [c.model_dump() for c in candidates],
        },
    )


def _draft_fields_response(thread_id: str, interrupt_value: dict) -> ChatResponse:
    return ChatResponse(
        thread_id=thread_id,
        type="draft_fields",
        data={
            "fields": interrupt_value.get("fields", []),
            "form_title": interrupt_value.get("form_title", "신청서"),
        },
    )


def _done_response(thread_id: str, state) -> ChatResponse:
    selected: WelfareCandidate | None = state.values.get("selected_service")
    candidates: list[WelfareCandidate] = state.values.get("welfare_candidates", [])
    filled_forms: list[dict] = state.values.get("filled_forms", [])
    reference_docs: list[dict] = state.values.get("reference_docs", [])
    # saved_path(서버 내부 절대경로)는 클라이언트에 노출하지 않음
    public_filled_forms = [
        {k: v for k, v in f.items() if k != "saved_path"} for f in filled_forms
    ]
    return ChatResponse(
        thread_id=thread_id,
        type="done",
        data={
            "final_report": state.values.get("final_report", ""),
            "selected_service": selected.model_dump() if selected else None,
            "welfare_candidates": [c.model_dump() for c in candidates],
            "filled_forms": public_filled_forms,
            "reference_docs": reference_docs,
        },
    )


async def _run_until_interrupt(
    thread_id: str,
    input_: dict | Command,
    config: dict,
) -> ChatResponse:
    logger.debug("[thread=%s] 그래프 스트림 시작", thread_id)
    t_stream_start = time.perf_counter()
    async for chunk in graph.astream(input_, config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            t_interrupt = time.perf_counter()
            logger.info(
                "[thread=%s] [TIMING] stream→interrupt: %.3fs",
                thread_id,
                t_interrupt - t_stream_start,
            )
            interrupt_value = chunk["__interrupt__"][0].value
            t0 = time.perf_counter()
            state = await graph.aget_state(config)
            logger.info(
                "[thread=%s] [TIMING] aget_state (post-interrupt): %.3fs",
                thread_id,
                time.perf_counter() - t0,
            )
            if "question" in interrupt_value:
                logger.info(
                    "[thread=%s] INTERRUPT → interview | field=%s | question=%.60s",
                    thread_id,
                    interrupt_value.get("field", "?"),
                    interrupt_value["question"],
                )
                return _interview_response(thread_id, interrupt_value, state)
            if "candidates" in interrupt_value:
                candidates = state.values.get("welfare_candidates", [])
                logger.info(
                    "[thread=%s] INTERRUPT → service_select | %d개: %s",
                    thread_id,
                    len(candidates),
                    ", ".join(getattr(c, "serv_nm", "?") for c in candidates),
                )
                return _service_select_response(thread_id, interrupt_value, state)
            if interrupt_value.get("type") == "service_detail":
                logger.info("[thread=%s] INTERRUPT → service_detail", thread_id)
                return _service_detail_response(thread_id, state)
            if interrupt_value.get("type") == "draft_fields":
                fields = interrupt_value.get("fields", [])
                logger.info(
                    "[thread=%s] INTERRUPT → draft_fields | %d개: %s",
                    thread_id,
                    len(fields),
                    [f.get("label") for f in fields],
                )
                return _draft_fields_response(thread_id, interrupt_value)
        else:
            _log_state_chunk(chunk)

    state = await graph.aget_state(config)
    if not state.values.get("welfare_candidates"):
        logger.info("[thread=%s] 스트림 종료 → no_results", thread_id)
        return ChatResponse(thread_id=thread_id, type="no_results", data={})
    logger.info("[thread=%s] 스트림 종료 → done", thread_id)
    return _done_response(thread_id, state)


@app.get("/forms/download/{thread_id}/{filename}")
async def download_form(thread_id: str, filename: str) -> FileResponse:
    """채워진 HWP 파일을 다운로드합니다."""
    filled_forms_dir = get_filled_forms_dir()
    safe_thread_id = Path(thread_id).name
    safe_filename = Path(filename).name
    file_path = filled_forms_dir / safe_thread_id / safe_filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    try:
        file_path.resolve().relative_to(filled_forms_dir.resolve())
    except ValueError as e:
        raise HTTPException(status_code=403, detail="접근이 거부되었습니다.") from e

    return FileResponse(
        path=str(file_path),
        filename=safe_filename,
        media_type="application/octet-stream",
    )


@app.post("/chat/start", response_model=ChatResponse)
async def chat_start() -> ChatResponse:
    """새 세션을 시작하고 첫 번째 인터뷰 질문을 반환합니다."""
    thread_id = str(uuid.uuid4())
    logger.info("[thread=%s] POST /chat/start", thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    await _touch_thread(thread_id)
    try:
        response = await _run_until_interrupt(thread_id, _initial_state(), config)
        logger.info("[thread=%s] → type=%s", thread_id, response.type)
        return response
    except Exception as e:
        logger.exception("[thread=%s] /chat/start 오류", thread_id)
        raise HTTPException(status_code=500, detail=_SERVER_ERROR_MSG) from e


@app.post("/chat/message", response_model=ChatResponse)
async def chat_message(body: MessageRequest) -> ChatResponse:
    """사용자 메시지를 받아 그래프를 재개하고 다음 상태를 반환합니다."""
    thread_id = body.thread_id
    logger.info("[thread=%s] POST /chat/message | msg=%.40r", thread_id, body.message)
    config = {"configurable": {"thread_id": thread_id}}
    t0 = time.perf_counter()
    state = await graph.aget_state(config)
    logger.info(
        "[thread=%s] [TIMING] aget_state (pre-stream): %.3fs",
        thread_id,
        time.perf_counter() - t0,
    )
    if not state.values:
        logger.warning("[thread=%s] thread 없음", thread_id)
        raise HTTPException(status_code=404, detail="thread_id를 찾을 수 없습니다.")

    # draft_fields interrupt 상태에서 __start_draft__ 중복 → 재개 없이 재반환
    if body.message == "__start_draft__" and state.next:
        interrupts = state.tasks[0].interrupts if state.tasks else []
        if interrupts:
            iv = interrupts[0].value
            if isinstance(iv, dict) and iv.get("type") == "draft_fields":
                logger.info(
                    "[thread=%s] draft_fields 중복 __start_draft__ → 재반환", thread_id
                )
                return _draft_fields_response(thread_id, iv)

    await _touch_thread(thread_id)
    try:
        response = await _run_until_interrupt(
            thread_id, Command(resume=body.message), config
        )
        logger.info("[thread=%s] → type=%s", thread_id, response.type)
        return response
    except Exception as e:
        logger.exception("[thread=%s] /chat/message 오류", thread_id)
        raise HTTPException(status_code=500, detail=_SERVER_ERROR_MSG) from e
