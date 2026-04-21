# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Management

Uses **`uv`**. All Python commands must be prefixed with `uv run`.

```bash
uv sync --all-groups          # install all deps (first time)
uv add <pkg>                  # add runtime dep
uv add --group dev <pkg>      # add dev dep
uv run python main.py         # run agent
uv run ruff check --fix .     # lint + auto-fix
uv run ruff format .          # format
uv run pytest tests/ -v       # all tests
uv run pre-commit install     # register hooks (once per clone)
```

## Architecture

8-node LangGraph pipeline. See `docs/development_plan.md` for full design.

```
START → initial_interview ⟲ → rag_search → service_select(HitL) → rag_detail → detail_interview ⟲ → document_guidance → draft_writer → report_writer → END
```

```
graph/ state.py builder.py   agents/ *.py   tools/ llm.py rag_client.py prompt_loader.py
prompts/ *.txt   tests/       main.py        server.py
```

## Data Models (`graph/state.py`)

**Enums (StrEnum):** `IncomeLevel` (`기초수급`/`차상위`/`저소득`/`일반`) · `EmploymentStatus` (`취업`/`실업`/`비경제활동`) · `MaritalStatus` (`미혼`/`기혼`/`이혼`/`사별`) · `DisabilitySeverity` (`경증`/`중증`)

**`UserProfile`** (Pydantic BaseModel)
- Step-1: `age`, `region`, `household_size`, `marital_status`, `has_children`, `disability`, `employment_status`, `income_level`
- `disability_severity` — conditional, only when `disability=True`; no model-level validator (enforced by interview logic)
- `is_elderly` — `@computed_field` from `age >= 65`; never set directly
- Step-2: `disability_type`, `disability_grade`, `children_ages`, `housing_type`, `household_type`, `is_veteran`, `is_single_parent`
- `extra_fields: dict[str, str | int | bool] = {}` — safe mutable default in Pydantic v2

**`WelfareCandidate`** (Pydantic BaseModel) — field names match RAG API exactly
- Required: `serv_id`, `serv_nm`, `serv_dgst`
- Defaults: `department=""`, `eligibility_reason=""` (LLM-generated), `score=0.0`, `priority=0`
- Phase 2: `required_documents=[]`, `application_fields=[]`, `application_url=None`, `detail_fetched=False`

**`AgentState`** (TypedDict) — all fields must be provided explicitly in `graph.invoke()`
```python
messages: Annotated[list[BaseMessage], add_messages]
user_profile: UserProfile
initial_missing_fields: list[str]
welfare_candidates: list[WelfareCandidate]
selected_service: WelfareCandidate | None
detail_missing_fields: list[str]   # "extra:" prefix for extra_fields keys
document_guidance: str
application_guide: str
final_report: str
```

## RAG API Contract

```
POST /welfare/search
Body:  { "age": 65, "income_level": "기초수급", "gender": "여성", ... }  # flat JSON, no wrapper
Response: [{ "serv_id", "serv_nm", "serv_dgst", "department", "score" }, ...]

GET /welfare/{serv_id}
Response: { "serv_id", "serv_nm", "required_documents", "application_fields", "application_url", ... }
```
- Empty `[]` from search → pipeline ends, no LLM fallback
- `eligibility_reason` is NOT in RAG response — LLM generates it from `serv_dgst`
- `required_documents` / `application_fields` currently return `[]` (RAG not yet implemented)

## Checkpointer

`GRAPH_CHECKPOINTER=memory` (dev) / `sqlite` (prod). `service_select` uses `interrupt()` for HitL — checkpointer required.

## Key Constraints

- All agent nodes are `async def`; return partial `AgentState` dict
- RAG HTTP calls only through `tools/rag_client.py` — never call `httpx` directly
- `get_llm()` is the only LLM import point — never import LLM directly
- `draft_writer` produces text guidance only — no HWP generation
- `report_writer` reformats only — no new information added

## Environment Variables

```dotenv
GOOGLE_API_KEY=
GOOGLE_MODEL=gemini-2.5-flash
GRAPH_CHECKPOINTER=memory
SQLITE_DB_PATH=./checkpoints.db
RAG_SERVICE_URL=http://localhost:8000
RAG_SEARCH_TOP_K=5
```

## Testing

`asyncio_mode = "auto"`. Mock fixtures in `tests/conftest.py`:
- `mock_llm`: `llm.invoke.return_value.content = "모킹된 응답"`
- `mock_rag_client`: `serv_id`/`serv_nm`/`serv_dgst` are required — include all three in mock data
