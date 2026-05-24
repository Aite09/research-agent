# Research Agent

> Autonomous multi-agent research pipeline powered by LangGraph, Groq, and Tavily — delivers structured, self-corrected markdown reports with a cinematic React frontend.

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
                             (score < 7 → revise, max 2 loops)
```

| Agent | Responsibility |
|-------|---------------|
| **Planner** | Decomposes the query into 3–5 focused sub-queries |
| **Search** | Runs parallel Tavily web searches per sub-query |
| **Writer** | Synthesises results into a structured markdown report |
| **Critic** | Scores quality 1–10, requests revisions if score < 7 |

---

## Features

- **Autonomous pipeline** — submit query, receive polished report
- **Self-correction loop** — Critic drives revisions until quality threshold is met
- **Real-time streaming** — WebSocket pushes live agent status updates to the UI
- **Cinematic frontend** — GSAP word-stagger hero, ScrollTrigger report reveal, infinite marquee
- **Source attribution** — every claim backed by cited URLs from Tavily
- **Quality scoring** — 1–10 score with visual quality bar in the report

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM | [Groq](https://console.groq.com) — `llama-3.3-70b-versatile` |
| Web Search | [Tavily](https://app.tavily.com) |
| Backend | FastAPI + WebSocket |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| Animations | GSAP + ScrollTrigger + @gsap/react |

---

## Project Structure

```
research-agent/
├── agents/
│   ├── planner_agent.py     # Query decomposition
│   ├── search_agent.py      # Tavily web search
│   ├── writer_agent.py      # Report synthesis
│   └── critic_agent.py      # Quality scoring + feedback
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
├── tests/
│   └── test_agents.py       # Unit + integration tests
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
uvicorn api.main:app --reload --port 8000
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

## Findings
### {Sub-topic 1}
...

## Sources
- [Title](url)

## Metadata
- Quality Score: 8/10
- Revisions: 1
- Queries Searched: 4
```

---

## Environment Variables

| Variable | Description | Where to get |
|----------|-------------|--------------|
| `GROQ_API_KEY` | LLM inference | [console.groq.com](https://console.groq.com) |
| `TAVILY_API_KEY` | Web search | [app.tavily.com](https://app.tavily.com) |

> **Never commit `.env`** — it is excluded via `.gitignore`.

---

## Development Phases

| Phase | Scope | Status |
|-------|-------|--------|
| Week 1 | Core agents + LangGraph graph | ✅ Complete |
| Week 2 | Writer agent + report synthesis | ✅ Complete |
| Week 3 | Critic agent + revision loop | ✅ Complete |
| Week 4 | FastAPI backend + React frontend | ✅ Complete |

---

## License

MIT — see [LICENSE](LICENSE) for details.
