import uuid

from dotenv import load_dotenv

from graph.builder import graph
from graph.state import UserProfile

load_dotenv()


def run():
    """그래프 실행 진입점."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "messages": [],
        "user_profile": UserProfile(),
        "initial_missing_fields": [
            "age",
            "gender",
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
    }

    result = graph.invoke(initial_state, config)
    return result


if __name__ == "__main__":
    run()
