# Research Agent

> Autonomous multi-agent research pipeline powered by LangGraph, Groq, and Tavily — delivers structured, self-corrected markdown reports with a cinematic React frontend.

[![CI](https://github.com/Aite09/research-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Aite09/research-agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61dafb?style=flat-square&logo=react&logoColor=black)
![LangGraph](https://img.shields.io/badge/LangGraph-Latest-f97316?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)

---

## Overview

Research Agent takes a natural language query and autonomously dispatches four specialized AI agents in sequence. Each agent has a single responsibility — decompose, search, write, critique — and the pipeline self-corrects via a revision loop until quality meets a threshold or revision limits are reached.

The result is a fully structured markdown research report with cited sources, a quality score, and real-time pipeline visibility in the browser.

---

## Architecture

```
START → Planner → Search → Writer → Critic → END
                                       ↑          ↓
                                       └── revise ┘
                             (score < 7 → revise, max 2 revisions)
```

| Agent | Responsibility |
|-------|---------------|
| **Planner** | Decomposes the query into 3–5 focused sub-queries |
| **Search** | Runs Tavily searches for all sub-queries concurrently (thread pool, `SEARCH_CONCURRENCY`, default 5) |
| **Writer** | Synthesises results into a structured markdown report |
| **Critic** | Scores quality 1–10 and decides: accept, or request a revision (score < 7, at most 2 revisions) |

Every LLM call goes through one wrapper (`agents/llm.py`) that measures latency, token usage and list-price cost, and can ship each call to the [LLM Observability Platform](https://github.com/Aite09/LLM-Observability-Platform).

---

## Features

- **Autonomous pipeline** — submit query, receive polished report
- **Self-correction loop** — Critic drives revisions until quality threshold is met
- **Real-time streaming** — WebSocket pushes live agent status updates to the UI
- **Cinematic frontend** — GSAP word-stagger hero, ScrollTrigger report reveal, infinite marquee
- **Source attribution** — every claim backed by cited URLs from Tavily
- **Quality scoring** — 1–10 score with visual quality bar in the report
- **Per-call telemetry** — latency, tokens and cost recorded for every LLM call; optional shipping to the observability platform
- **Tested + benchmarked** — mocked unit/graph/API tests in CI, plus a live-API benchmark harness that writes raw results to `benchmarks/results/`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM | [Groq](https://console.groq.com) — `openai/gpt-oss-120b` (set `GROQ_MODEL` to change) |
| Web Search | [Tavily](https://app.tavily.com) |
| Backend | FastAPI + WebSocket |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| Animations | GSAP + ScrollTrigger + @gsap/react |
| Testing / CI | pytest (Groq + Tavily faked), GitHub Actions |

---

## Project Structure

```
research-agent/
├── agents/
│   ├── llm.py               # Shared Groq wrapper: latency, tokens, cost, observability
│   ├── planner_agent.py     # Query decomposition
│   ├── search_agent.py      # Concurrent Tavily web search
│   ├── writer_agent.py      # Report synthesis
│   └── critic_agent.py      # Quality scoring + accept/revise decision
├── graph/
│   ├── state.py             # AgentState TypedDict schema
│   └── workflow.py          # LangGraph StateGraph definition
├── api/
│   └── main.py              # FastAPI REST + WebSocket server
├── frontend/
│   └── src/
│       ├── App.tsx           # Main app + WebSocket integration
│       ├── components/
│       │   ├── AgentTimeline.tsx   # Real-time pipeline status
│       │   ├── ReportDisplay.tsx   # Markdown report + stats
│       │   └── Background.tsx      # Animated orb background
│       └── types.ts          # TypeScript types
├── benchmarks/
│   ├── run.py               # Live-API benchmark (pipeline + search A/B)
│   ├── queries.txt          # 30 benchmark questions across domains
│   └── results/             # Raw JSONL + summary JSON from each run
├── tests/
│   ├── test_agents.py       # Agent, graph, LLM-wrapper and WebSocket tests
│   ├── test_benchmark.py    # Benchmark harness math
│   ├── helpers.py           # Groq/Tavily fakes
│   └── conftest.py          # Shared fixtures
├── main.py                  # CLI entry point
└── requirements.txt
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Groq API key](https://console.groq.com) (free tier available)
- [Tavily API key](https://app.tavily.com) (free tier available)

### 1. Clone & Configure

```bash
git clone https://github.com/Aite09/research-agent.git
cd research-agent
```

Create a `.env` file in the project root:

```env
GROQ_API_KEY=gsk_your_key_here
TAVILY_API_KEY=tvly_your_key_here
```

### 2. Backend Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

### 4. Run

**Terminal 1 — Backend:**
```bash
source venv/bin/activate
uvicorn api.main:app --reload --port 8001
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

### CLI Mode (no frontend)

```bash
source venv/bin/activate
python main.py "What are the latest breakthroughs in quantum computing?"
```

---

## Report Output Format

```markdown
# Research Report: {topic}

## Executive Summary
...

## Key Findings
### {Theme 1}
...

## Analysis
...

## Conclusion
...

## Sources
- [Title](url)

---
*Report generated from 12 sources across 4 research angles.*
```

Quality score, revision count, word count and source count are returned alongside
the report (CLI summary, REST response, WebSocket `complete` event).

---

## Environment Variables

| Variable | Description | Where to get |
|----------|-------------|--------------|
| `GROQ_API_KEY` | LLM inference | [console.groq.com](https://console.groq.com) |
| `TAVILY_API_KEY` | Web search | [app.tavily.com](https://app.tavily.com) |
| `GROQ_MODEL` | Groq model for all agents (default `openai/gpt-oss-120b`) | optional |
| `SEARCH_CONCURRENCY` | Max parallel Tavily requests (default `5`; `1` = sequential) | optional |
| `OBSERVABILITY_URL` | Base URL of the LLM Observability Platform API, e.g. `http://localhost:8000` | optional |
| `OBSERVABILITY_APP_ID` | `application_id` used in observability logs (default `research-agent`) | optional |

> **Never commit `.env`** — it is excluded via `.gitignore`.

---

## Testing

```bash
pytest                      # mocked Groq + Tavily — no keys, no network, runs in CI
RUN_INTEGRATION=1 pytest    # adds one end-to-end run against the real APIs
```

The suite covers each agent's parsing and failure handling, concurrent search
(a thread barrier proves sub-queries really overlap), the critic's revision cap,
the LLM wrapper's cost math and observability payload, and the WebSocket API.

---

## Benchmarks

`benchmarks/run.py` runs the pipeline against the live APIs and writes every run
to `benchmarks/results/` (raw JSONL + summary JSON, tagged with the git commit),
so any number quoted about this project can be traced to a file.

```bash
python -m benchmarks.run --runs 5 --start 20                    # full pipeline: latency, tokens, cost, score
python -m benchmarks.run --mode search-ab --runs 10 --start 10  # search stage: sequential vs concurrent
```

- **Latency** is wall-clock per run; per-agent time comes from LangGraph stream updates.
- **Rate limits:** the Groq SDK retries 429s after a backoff, so throttling looks like
  latency, not an error. Each run records SDK retries and their wait (parsed from the
  SDK's retry log); the summary reports latency with and without that wait.
- **Cost** is tokens × Groq list price ($0.15 / $0.75 per 1M input/output tokens for
  `openai/gpt-oss-120b`, launch price — errs high). Free-tier keys are not billed — this is the equivalent paid cost.
- **Search A/B** searches each question once, in one mode (alternating), so every timing
  is a cold Tavily request. Timing both modes on the same sub-queries doesn't work:
  Tavily serves the repeat from cache (0.2–0.5 s vs 3–12 s cold).
- Use `--start` to pick questions not searched recently, for the same cache reason.

### Measured results (2026-11-03)

**Search stage — sequential vs concurrent** · cold requests, 4 sub-queries each, n = 5 per mode
([summary](benchmarks/results/20261103T002110Z_search-ab_summary.json))

| Mode | p50 | p95 |
|------|-----|-----|
| Sequential (`SEARCH_CONCURRENCY=1`) | 11.68 s | 12.84 s |
| Concurrent (5 workers) | 4.20 s | 4.67 s |

Concurrent search cut search-stage p50 latency by **64% (2.78×)**.

**Full pipeline** · `openai/gpt-oss-120b` on the Groq free tier, n = 5, commit `3cf4f24`
([summary](benchmarks/results/20261103T001513Z_pipeline_summary.json))

| Metric | Value |
|--------|-------|
| Successful runs | 5 / 5 |
| End-to-end p50 (wall clock) | 25.3 s |
| End-to-end p50 excluding rate-limit backoff | 9.7 s (p95 16.1 s) |
| Runs throttled by free-tier limits | 4 / 5 — 18 SDK retries, 36.6 s mean wait per run |
| List-price cost per run | p50 $0.0023 · mean $0.0031 |
| Tokens per run (mean) | 8,760 in · 2,372 out across 3.8 LLM calls |
| First draft accepted by critic | 4 / 5 |
| Sources cited per report (mean) | 11.6 |

Notes: with n = 5, p95 is effectively the worst run — treat these as indicative. The one
unthrottled run finished in 7.2 s end-to-end. In run 3 the critic's score could not be
parsed; the 5.0 fallback caused two extra revisions (146 s, 129 s of it rate-limit wait).
That parser was fixed afterwards (`eaa1047`), so these results include the bug.

---

## Observability Integration

Run the [LLM Observability Platform](https://github.com/Aite09/LLM-Observability-Platform)
(its API listens on `:8000`; this project's API uses `:8001`), then:

```bash
OBSERVABILITY_URL=http://localhost:8000 python -m benchmarks.run --runs 10
```

Each Planner/Writer/Critic call is posted to `POST /logs` with model, tokens, cost,
latency, status and an `agent` tag, so the platform's dashboard, metrics and drift
detection run on real pipeline traffic. Posting happens on a background thread with
a 2 s timeout — if the platform is down, the pipeline is unaffected.

---

## Development Phases

| Phase | Scope | Status |
|-------|-------|--------|
| Week 1 | Core agents + LangGraph graph | ✅ Complete |
| Week 2 | Writer agent + report synthesis | ✅ Complete |
| Week 3 | Critic agent + revision loop | ✅ Complete |
| Week 4 | FastAPI backend + React frontend | ✅ Complete |
| Week 5 | LLM telemetry, concurrent search, tests + CI, benchmarks, observability integration | ✅ Complete |

---

## License

MIT — see [LICENSE](LICENSE) for details.
