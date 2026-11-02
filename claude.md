# Claude Reference: Multi-Agent Research & Report Generator

> This file is the authoritative project reference. Read before every task.
> Last updated: 2026-05-23

---

## Project Purpose

User submits research query → 4 specialized LLM agents (Groq, Llama 3.3 70B) collaborate autonomously → structured, self-corrected markdown report with sources and quality score.

---

## Architecture Overview

```
START → planner → search → writer → critic → END
                                       ↑         |
                                       └─────────┘
                             (score < 7 → revise, max 2 loops)
```

### Agent Responsibilities

| Agent | File | Responsibility |
|-------|------|----------------|
| Planner | `agents/planner_agent.py` | Decompose query → 3–5 focused sub-queries |
| Search | `agents/search_agent.py` | Tavily API search per sub-query, collect results |
| Writer | `agents/writer_agent.py` | Synthesize results → structured markdown report |
| Critic | `agents/critic_agent.py` | Score 1–10, return critique if score < 7 |

### Routing Logic
- `critic → END` if `quality_score >= 7` OR `revision_count >= 2`
- `critic → writer` if `quality_score < 7` AND `revision_count < 2`

---

## Tech Stack

| Layer | Technology | Version/Notes |
|-------|-----------|---------------|
| Language | Python | 3.11+ |
| Agent Orchestration | LangGraph | Latest stable |
| LLM | Groq API (OpenAI-compatible) | `llama-3.3-70b-versatile` |
| Web Search | Tavily API | via `tavily-python` |
| Backend (Week 4) | FastAPI | REST + WebSocket |
| Frontend (Week 4) | React + Tailwind CSS | Vite-based |
| Env Management | python-dotenv | `.env` file |

---

## Folder Structure

```
research-agent/
├── agents/
│   ├── __init__.py              # Package init
│   ├── llm.py                   # Shared Groq wrapper: latency, tokens, cost, observability
│   ├── planner_agent.py         # Query decomposition
│   ├── search_agent.py          # Tavily web search
│   ├── writer_agent.py          # Report synthesis
│   └── critic_agent.py          # Quality scoring + feedback
├── graph/
│   ├── __init__.py              # Package init
│   ├── state.py                 # AgentState TypedDict schema
│   └── workflow.py              # LangGraph StateGraph definition
├── frontend/                    # Week 4 React app (empty for now)
├── benchmarks/                  # Live-API benchmark harness + committed results
├── tests/
│   ├── test_agents.py           # Unit + graph + API tests (Groq/Tavily faked)
│   ├── test_benchmark.py        # Benchmark harness tests
│   ├── helpers.py               # Fakes
│   └── conftest.py              # Shared fixtures
├── .env                         # API keys (never commit)
├── .gitignore
├── claude.md                    # This file
├── main.py                      # Entry point (CLI runner)
└── requirements.txt
```

---

## AgentState Schema

Defined in `graph/state.py` as `TypedDict`.

```python
class AgentState(TypedDict):
    query: str                        # Original user question
    search_queries: List[str]         # Sub-queries from Planner
    search_results: List[SearchResult] # Raw Tavily results
    report: str                       # Markdown report from Writer
    quality_score: float              # Score 1–10 from Critic
    critique: str                     # Critic feedback for Writer
    revision_count: int               # Loop counter (max 2)
    messages: List[dict]              # Full conversation log (auto-appended)
    status: str                       # Pipeline status string
    error: str                        # Populated on failure, else empty string
```

### SearchResult Schema
```python
class SearchResult(TypedDict):
    query: str       # Sub-query that produced this result
    url: str         # Source URL
    title: str       # Page title
    content: str     # Truncated to 1500 chars max
```

---

## Environment Variables

All keys loaded via `python-dotenv` from `.env`. Never hardcode.

```env
GROQ_API_KEY=gsk_...          # from console.groq.com (free)
TAVILY_API_KEY=tvly-...       # from app.tavily.com
```

---

## Production Standards (enforce always)

### Code Quality
- **Complete code only** — no placeholders, no `# TODO`, no `pass` stubs
- **Type hints** on every function signature (args + return type)
- **Docstrings** on every file (module-level) and every function
- **No `any` type** unless genuinely unavoidable with comment explaining why

### Error Handling
- Every agent wraps LLM/API calls in `try/except`
- On failure: populate `state["error"]`, set `state["status"] = "error"`, return state
- Agents **never** raise unhandled exceptions into the graph
- Graceful degradation: if search fails, writer gets empty results + error note

### Observability
- Every agent prints debug line at entry: `[AGENT_NAME] Starting — query: {query}`
- Every agent prints debug line at exit: `[AGENT_NAME] Done — {key_result_summary}`
- Revision loops logged: `[CRITIC] Score: {score}/10 — Revision {revision_count}/2`

### Security
- No API keys in code or logs
- Tavily results sanitized before passing to LLM (strip scripts, truncate to 1500 chars)
- No `eval()` or `exec()` usage

### LLM Usage
- Model: `llama-3.3-70b-versatile` (never hardcode model string — use constant `MODEL = "llama-3.3-70b-versatile"`)
- Client: `groq.Groq(api_key=os.getenv("GROQ_API_KEY"))`, built only inside `agents/llm.py` — agents call `chat()`
- Prompts: structured with clear role/task/output-format sections
- Temperature: 0.3 for Planner/Critic (deterministic), 0.7 for Writer (creative)
- Max tokens: Planner 500, Search N/A, Writer 4000, Critic 500

---

## LangGraph Patterns (key concepts for this project)

### StateGraph
```python
# graph/workflow.py pattern
from langgraph.graph import StateGraph, END
graph = StateGraph(AgentState)
graph.add_node("planner", planner_node)
graph.add_conditional_edges("critic", route_after_critic, {...})
```

### Node Functions
Each agent is a **node function**: takes `AgentState`, returns `dict` of updated fields only.
```python
def planner_node(state: AgentState) -> dict:
    # return only fields this node updates
    return {"search_queries": [...], "status": "searching"}
```

### Conditional Routing
```python
def route_after_critic(state: AgentState) -> str:
    if state["quality_score"] >= 7 or state["revision_count"] >= 2:
        return "end"
    return "writer"
```

---

## Report Output Format

Writer agent produces markdown with this structure:
```markdown
# Research Report: {topic}

## Executive Summary
...

## Findings

### {Sub-topic 1}
...

### {Sub-topic 2}
...

## Sources
- [Title](url)

## Metadata
- Quality Score: {score}/10
- Revisions: {count}
- Queries Searched: {n}
```

---

## Week 4 Frontend (future — do not build yet)

### Design Skills Available
Located in `~/.claude/skills/`:
- `ui-ux-pro-max` — full UI/UX design system
- `design-taste-frontend` — aesthetic decisions
- `high-end-visual-design` — premium visual polish
- `minimalist-ui` — clean editorial style
- `full-output-enforcement` — complete code generation
- `gpt-taste` — GPT-style chat UI patterns

### Planned Stack
- React + Vite + TypeScript
- Tailwind CSS
- FastAPI WebSocket for streaming
- Real-time agent status updates in UI

---

## Development Phases

| Phase | Scope | Status |
|-------|-------|--------|
| Week 1 | Core agents + LangGraph graph | ✅ Complete |
| Week 2 | Writer agent + report synthesis | ✅ Complete |
| Week 3 | Critic agent + revision loop | ✅ Complete |
| Week 4 | FastAPI backend + React frontend | ✅ Complete |
| Week 5 | Telemetry, concurrent search, tests + CI, benchmarks | ✅ Complete |

---

## Common Pitfalls (avoid these)

1. **Mutating state directly** — LangGraph expects node returns, not mutations
2. **Missing keys in return dict** — only return keys you actually updated
3. **Hardcoded API keys** — always `.env`
4. **Unhandled Tavily errors** — API rate limits and network errors are common
5. **Infinite revision loops** — `revision_count` guard is mandatory
6. **Oversized search results** — truncate to 1500 chars before passing to LLM

---

## Testing Strategy

File: `tests/test_agents.py`

- Unit test each agent node function with mock state
- Mock Groq client + Tavily client (no real API calls in unit tests)
- Integration test: full graph run with real APIs (tagged, run manually)
- Assert: state schema integrity after each node

---

## Claude Behavior Instructions

When working on this project:
1. Read this file before every task
2. Apply `senior-fullstack` + `senior-backend` principles
3. Never produce incomplete code — use `full-output-enforcement` skill if needed
4. Explain LangGraph decisions (beginner context)
5. Default model constant: `MODEL = "llama-3.3-70b-versatile"`
6. Prefer editing existing files over creating new ones
7. Flag any deviation from production standards in comments
1