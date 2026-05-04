from langgraph.constants import END

from graph.builder import (
    build_graph,
    route_after_detail_interview,
    route_after_initial_interview,
    route_after_rag_search,
)
from graph.state import UserProfile, WelfareCandidate


def _make_candidate(**kwargs) -> WelfareCandidate:
    defaults = dict(
        serv_id="WLF00000035",
        serv_nm="기초연금",
        serv_dgst="노인 연금",
    )
    return WelfareCandidate(**{**defaults, **kwargs})


def _base_state(**overrides) -> dict:
    state = {
        "messages": [],
        "user_profile": UserProfile(),
        "initial_missing_fields": [],
        "welfare_candidates": [],
        "selected_service": None,
        "detail_missing_fields": [],
        "document_guidance": "",
        "application_guide": "",
        "final_report": "",
    }
    state.update(overrides)
    return state


class TestGraphCompile:
    async def test_graph_compiles(self):
        g = await build_graph()
        assert g is not None

    async def test_all_nodes_registered(self):
        g = await build_graph()
        nodes = list(g.get_graph().nodes.keys())
        expected = [
            "initial_interview",
            "rag_search",
            "service_select",
            "rag_detail",
            "detail_interview",
            "document_guidance",
            "draft_writer",
            "report_writer",
        ]
        for node in expected:
            assert node in nodes


class TestConditionalEdges:
    def test_initial_interview_rereoutes_when_missing(self):
        state = _base_state(initial_missing_fields=["age", "region"])
        assert route_after_initial_interview(state) == "initial_interview"

    def test_initial_interview_proceeds_when_complete(self):
        state = _base_state(initial_missing_fields=[])
        assert route_after_initial_interview(state) == "rag_search"

    def test_rag_search_ends_when_no_candidates(self):
        state = _base_state(welfare_candidates=[])
        assert route_after_rag_search(state) == END

    def test_rag_search_proceeds_when_candidates_found(self):
        state = _base_state(welfare_candidates=[_make_candidate()])
        assert route_after_rag_search(state) == "service_select"

    def test_detail_interview_reentries_when_missing(self):
        state = _base_state(detail_missing_fields=["household_type"])
        assert route_after_detail_interview(state) == "detail_interview"

    def test_detail_interview_proceeds_when_complete(self):
        state = _base_state(detail_missing_fields=[])
        assert route_after_detail_interview(state) == "document_guidance"
