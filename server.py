"""복지드림 AI 에이전트 FastAPI 서버."""

from __future__ import annotations

import logging
import logging.config
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
from pydantic import BaseModel

from graph.builder import build_graph
from graph.state import UserProfile, WelfareCandidate

load_dotenv()

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 그래프를 초기화하고, 종료 시 리소스를 정리합니다."""
    global graph
    graph = await build_graph()
    yield
    # SQLite 모드일 경우 _checkpointer_stack이 GC될 때 커넥션 자동 종료


app = FastAPI(title="BokjiDream AI Server", lifespan=lifespan)

_CORS_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["POST"],
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


def _initial_state() -> dict:
    return {
        "messages": [],
        "user_profile": UserProfile(),
        "initial_missing_fields": [
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
        "document_guidance": "",
        "application_guide": "",
        "final_report": "",
        "interview_current_field": None,
        "interview_last_question": "",
        "interview_last_answer": "",
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


def _done_response(thread_id: str, state) -> ChatResponse:
    selected: WelfareCandidate | None = state.values.get("selected_service")
    candidates: list[WelfareCandidate] = state.values.get("welfare_candidates", [])
    return ChatResponse(
        thread_id=thread_id,
        type="done",
        data={
            "final_report": state.values.get("final_report", ""),
            "document_guidance": state.values.get("document_guidance", ""),
            "application_guide": state.values.get("application_guide", ""),
            "selected_service": selected.model_dump() if selected else None,
            "welfare_candidates": [c.model_dump() for c in candidates],
        },
    )


async def _run_until_interrupt(
    thread_id: str,
    input_: dict | Command,
    config: dict,
) -> ChatResponse:
    logger.debug("[thread=%s] 그래프 스트림 시작", thread_id)
    async for chunk in graph.astream(input_, config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            interrupt_value = chunk["__interrupt__"][0].value
            state = await graph.aget_state(config)
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
        else:
            _log_state_chunk(chunk)

    state = await graph.aget_state(config)
    if not state.values.get("welfare_candidates"):
        logger.info("[thread=%s] 스트림 종료 → no_results", thread_id)
        return ChatResponse(thread_id=thread_id, type="no_results", data={})
    logger.info("[thread=%s] 스트림 종료 → done", thread_id)
    return _done_response(thread_id, state)


@app.post("/chat/start", response_model=ChatResponse)
async def chat_start() -> ChatResponse:
    """새 세션을 시작하고 첫 번째 인터뷰 질문을 반환합니다."""
    thread_id = str(uuid.uuid4())
    logger.info("[thread=%s] POST /chat/start", thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    try:
        response = await _run_until_interrupt(thread_id, _initial_state(), config)
        logger.info("[thread=%s] → type=%s", thread_id, response.type)
        return response
    except Exception as e:
        logger.exception("[thread=%s] /chat/start 오류", thread_id)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/chat/message", response_model=ChatResponse)
async def chat_message(body: MessageRequest) -> ChatResponse:
    """사용자 메시지를 받아 그래프를 재개하고 다음 상태를 반환합니다."""
    thread_id = body.thread_id
    logger.info("[thread=%s] POST /chat/message | msg=%.40r", thread_id, body.message)
    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.aget_state(config)
    if not state.values:
        logger.warning("[thread=%s] thread 없음", thread_id)
        raise HTTPException(status_code=404, detail="thread_id를 찾을 수 없습니다.")
    try:
        response = await _run_until_interrupt(
            thread_id, Command(resume=body.message), config
        )
        logger.info("[thread=%s] → type=%s", thread_id, response.type)
        return response
    except Exception as e:
        logger.exception("[thread=%s] /chat/message 오류", thread_id)
        raise HTTPException(status_code=500, detail=str(e)) from e
