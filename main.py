import asyncio
import uuid

from dotenv import load_dotenv
from langgraph.types import Command

from graph.builder import build_graph
from graph.state import UserProfile

load_dotenv()


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
        "detail_current_field": None,
        "detail_last_question": "",
        "detail_last_answer": "",
        "extra_field_schemas": [],
    }


async def _run_until_interrupt(graph, input_: dict | Command, config: dict) -> tuple:
    async for chunk in graph.astream(input_, config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            interrupt_value = chunk["__interrupt__"][0].value
            state = await graph.aget_state(config)
            if "question" in interrupt_value:
                return ("interview", interrupt_value, state)
            if "candidates" in interrupt_value:
                return ("service_select", interrupt_value, state)

    state = await graph.aget_state(config)
    if not state.values.get("welfare_candidates"):
        return ("no_results", {}, state)
    return ("done", {}, state)


async def run():
    """그래프 실행 진입점."""
    graph = await build_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("\n복지드림 AI 복지서비스 안내를 시작합니다.\n")

    input_: dict | Command = _initial_state()

    while True:
        response_type, interrupt_value, state = await _run_until_interrupt(
            graph, input_, config
        )

        if response_type == "interview":
            print(f"\n[복지드림] {interrupt_value['question']}")
            user_input = input("> ").strip()
            input_ = Command(resume=user_input)

        elif response_type == "service_select":
            print(f"\n[복지드림] {interrupt_value['candidates']}")
            if interrupt_value.get("error"):
                print(f"⚠ {interrupt_value['error']}")
            user_input = input("> ").strip()
            input_ = Command(resume=user_input)

        elif response_type == "no_results":
            print("\n[복지드림] 해당하는 복지서비스를 찾지 못했습니다.")
            break

        elif response_type == "done":
            print("\n[복지드림] 안내가 완료되었습니다.\n")
            print("=== 최종 보고서 ===")
            print(state.values.get("final_report", ""))
            break


if __name__ == "__main__":
    asyncio.run(run())
