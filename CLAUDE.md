# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Management

Uses **`uv`**. All Python commands must be prefixed with `uv run`.

```bash
uv sync --all-groups          # install all deps (first time)
uv add <pkg>                  # add runtime dep
uv add --group dev <pkg>      # add dev dep
uv add --group test <pkg>     # add test dep

uv run python main.py         # run agent
uv run ruff check .           # lint
uv run ruff check --fix .     # lint + auto-fix
uv run ruff format .          # format
uv run pytest tests/ -v       # all tests
uv run pytest tests/test_file.py::test_fn -v  # single test
uv run pre-commit install     # register hooks (once per clone)
```

## Architecture

An 8-node **LangGraph** pipeline. Nodes execute in order; two nodes have re-entry loops and one has a Human-in-the-Loop pause.

```
START
  │
  ▼
initial_interview ◄──────────────────┐  (re-entry loop: missing fields)
  │ min fields collected             │
  ▼                                  │
rag_search ──(no results)──► END     │
  │ candidates found                 │
  ▼                                  │
service_select  ← user picks (HitL)  │
  │                                  │
  ▼                                  │
rag_detail                           │
  │                                  │
  ▼                                  │
detail_interview ◄───────────────────┘  (re-entry loop: missing fields)
  │ all fields collected
  ▼
document_guidance
  ▼
draft_writer
  ▼
report_writer
  ▼
END
```

### Target directory layout

```
agents/
  initial_interview.py   # Step 1 interview — collects minimum profile fields
  rag_search.py          # RAG candidate search — JSON profile → N welfare services
  service_select.py      # HitL pause — user selects a service
  rag_detail.py          # RAG detail fetch — fills selected_service fields
  detail_interview.py    # Step 2 interview — service-specific additional fields
  document_guidance.py   # Lists required documents
  draft_writer.py        # Per-field application guide (no HWP generation)
  report_writer.py       # Reformats guide into user-friendly report
graph/
  state.py               # AgentState, UserProfile, WelfareCandidate
  builder.py             # StateGraph wiring, conditional edges, checkpointer
tools/
  llm.py                 # get_llm() factory (Gemini now, Ollama later)
  rag_client.py          # httpx async client for RAG service (Phase 3)
  prompt_loader.py       # loads prompts/{name}.txt files
prompts/
  initial_interview.txt
  detail_interview.txt
  document_guidance.txt
  draft_writer.txt
  report_writer.txt
tests/
  conftest.py            # mock_llm and mock_rag_client fixtures
  test_smoke.py
  test_state.py / test_graph.py / test_e2e.py / ...
main.py                  # CLI entry point (Phase 5: interactive loop)
server.py                # FastAPI mode for Next.js (Phase 5)
```

## Data Models (`graph/state.py`)

Three Pydantic models define the shared state:

**`UserProfile`** — grows incrementally across both interviews.
- Step-1 minimum fields: `age`, `household_size`, `marital_status`, `has_children`, `disability`, `disability_severity`, `employment_status`, `region`, `income_level`
  - `income_level` uses `IncomeLevel` Enum (`기초생활수급자` / `차상위계층` / `저소득` / `일반`) — LLM determines this from conversation, not direct user input
  - `employment_status` uses `EmploymentStatus` Enum (`취업` / `실업` / `비경제활동`)
  - `marital_status` uses `MaritalStatus` Enum (`미혼` / `기혼` / `이혼` / `사별`)
  - `disability_severity` uses `DisabilitySeverity` Enum (`경증` / `중증`) — only collected when `disability=True`
  - `is_elderly` is a `@computed_field` derived from `age >= 65` — never set it directly
- Step-2 service-specific fields: `disability_type`, `disability_grade`, `children_ages`, `housing_type`, `household_type`, `is_veteran`, `is_single_parent`, etc.
- `extra_fields: dict[str, str | int | bool]` — catch-all for fields not in the model; keys are later promoted to regular fields if they appear often
- See `docs/state_design.md` for full field list and income_level collection flow

**`WelfareCandidate`** — one entry per RAG result.
- Phase 1 (after `rag_search`): `service_id`, `service_name`, `department`, `eligibility_reason`, `summary`, `score`, `priority`
  - `department` and `eligibility_reason` are required fields (no default) — must be present in RAG `/search` response
- Phase 2 (after `rag_detail`): `required_documents`, `application_fields`, `application_url`, `detail_fetched=True`
- `priority` is computed inside `rag_search_node` from `score` descending order — not provided by RAG

**`AgentState`** (`TypedDict`):
```python
messages: Annotated[list[BaseMessage], add_messages]  # use add_messages Reducer
user_profile: UserProfile
initial_missing_fields: list[str]
welfare_candidates: list[WelfareCandidate]
selected_service: WelfareCandidate | None
detail_missing_fields: list[str]    # "extra:" prefix for extra_fields keys
document_guidance: str
application_guide: str
final_report: str
```

## Key Behavioral Constraints

**No LLM fallback on empty RAG results.** If `rag_search` returns `[]`, the pipeline terminates with a user-facing message. LLMs must not fabricate welfare services.

**`rag_detail` uses LLM (structured output) to compute `detail_missing_fields`.** After fetching RAG detail, the node passes the service `eligibility` object to the LLM and asks it to infer which `UserProfile` fields are still missing. Returns `list[str]`.

**`detail_interview` is a pass-through when `detail_missing_fields` is empty.** If `rag_detail` determines no additional fields are needed, `detail_interview` returns immediately without any LLM call. `route_after_detail_interview` then routes directly to `document_guidance`.

**`detail_missing_fields` field naming convention:**
- Regular `UserProfile` field → plain name, e.g. `"household_size"`
- Field not in model → `"extra:"` prefix, e.g. `"extra:deposit_amount"` → stored in `user_profile.extra_fields`

**`draft_writer` does not generate HWP files.** It produces per-field text guidance showing how to fill in each field. Unknown items are marked `[직접 확인 필요: 이유]`.

**`report_writer` does not add new information.** It only reformats `application_guide` + `document_guidance` into readable Markdown.

## Checkpointer (`graph/builder.py`)

`service_select` uses LangGraph `interrupt()` for Human-in-the-Loop. A checkpointer is required for this to work.

| `GRAPH_CHECKPOINTER` value | Storage | When to use |
|---|---|---|
| `memory` | RAM (lost on restart) | Development / tests |
| `sqlite` | `./checkpoints.db` file | Phase 5 production |
| `postgres` | External DB | High-traffic future |

Resume pattern:
```python
# CLI / test: resume after interrupt
graph.invoke(Command(resume=user_input), config)
# FastAPI: POST /resume with selected value
```

## RAG API Contract

Two HTTP calls to the `rag/` service. **Do not change the JSON shape without coordinating with `rag/`.**

```
POST /search
Body:  { "profile": { "age": 65, "income_level": "기초생활수급자", ... }, "top_k": 5 }
Response: [{ "id", "name", "department", "summary", "eligibility_reason", "score" }, ...]
# Empty list [] = no results; pipeline ends, no LLM fallback

POST /services/detail
Body:  { "service_id": "welfare_001" }
Response: { "id", "name", "required_documents", "application_fields", "application_url", ... }
# application_fields is required by draft_writer
```

RAG converts the JSON profile to natural language internally; the AI side only sends structured JSON.

## Prompt Management

System prompts live in `prompts/*.txt` and are loaded at import time via `tools/prompt_loader.py`. Variable substitution uses Python f-strings or `str.format()` — no template engine.

```python
from tools.prompt_loader import load_prompt
SYSTEM_PROMPT = load_prompt("initial_interview")  # reads prompts/initial_interview.txt
```

## LLM Factory (`tools/llm.py`)

`get_llm()` is the single swap point. Currently Gemini; Ollama block is commented out.
All agent nodes must call `get_llm()` — never import an LLM directly.

## Environment Variables

```dotenv
# Phase 1–3 (Gemini)
GOOGLE_API_KEY=
GOOGLE_MODEL=gemini-2.5-flash

# Checkpointer
GRAPH_CHECKPOINTER=memory          # memory | sqlite | postgres
SQLITE_DB_PATH=./checkpoints.db    # if sqlite

# Phase 3 — RAG integration
RAG_SERVICE_URL=http://localhost:8000
RAG_SEARCH_TOP_K=5
RAG_TIMEOUT_SECONDS=10
RAG_MAX_RETRIES=1

# Phase 4 — Ollama migration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# Phase 5 — FastAPI server
SERVER_HOST=0.0.0.0
SERVER_PORT=8001
```

## Testing

`asyncio_mode = "auto"` — no decorator needed on async test functions.

**Mocking strategy** (`tests/conftest.py`):
```python
@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.invoke.return_value.content = "모킹된 응답"
    return llm

@pytest.fixture
def mock_rag_client():
    client = AsyncMock()
    # WARNING: include ALL required WelfareCandidate fields (department, eligibility_reason have no default)
    client.search.return_value = [{
        "id": "welfare_001", "name": "기초연금", "department": "보건복지부",
        "eligibility_reason": "나이 65세 이상, 기초생활수급자", "summary": "...", "score": 0.95,
    }]
    client.get_detail.return_value = {
        "id": "welfare_001", "required_documents": [...],
        "application_fields": [...], "application_url": "...",
    }
    return client
```

RAG nodes (`rag_search`, `rag_detail`) must inject the client so it can be mocked in tests. Direct HTTP calls inside agents are forbidden — use `tools/rag_client.py`.

## Code Conventions

- Python ≥ 3.11, line length 88, Google docstring style
- `| None` over `Optional[...]`
- All agent nodes are `async def` — RAG client uses `httpx.AsyncClient`; do not mix sync and async nodes
- All agent nodes take `AgentState` as input and return a partial `AgentState` dict
- RAG HTTP calls go through `tools/rag_client.py` — never call `httpx` directly in agents
- `AgentState` initial values must be explicitly provided in `graph.invoke()` — TypedDict has no defaults
