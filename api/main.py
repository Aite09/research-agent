"""
api/main.py

FastAPI backend for the Multi-Agent Research & Report Generator.

Provides two interfaces:
  - POST /api/research     → synchronous REST endpoint (returns full result)
  - WS   /ws/research      → WebSocket endpoint (streams per-agent events)

WebSocket event format (JSON):
  {"type": "agent_start",  "agent": "planner",  "message": "..."}
  {"type": "agent_done",   "agent": "planner",  "data": {...}}
  {"type": "complete",     "report": "...", "quality_score": 8.0, ...}
  {"type": "error",        "message": "..."}

Run with:
  uvicorn api.main:app --reload --port 8001
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from graph.state import AgentState
from graph.workflow import build_graph

load_dotenv()

# ── App setup ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Research Agent API",
    description="Multi-agent AI research pipeline powered by Groq + LangGraph",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for running synchronous LangGraph pipeline
_executor = ThreadPoolExecutor(max_workers=4)


# ── Pydantic models ───────────────────────────────────────────────────────────
class ResearchRequest(BaseModel):
    """Request body for REST endpoint."""
    query: str


class ResearchResponse(BaseModel):
    """Response body for REST endpoint."""
    query: str
    report: str
    quality_score: float
    revision_count: int
    search_queries: list[str]
    source_count: int
    word_count: int
    status: str
    error: str


# ── Helpers ───────────────────────────────────────────────────────────────────
def _make_initial_state(query: str) -> AgentState:
    """Build zero-value initial AgentState for a given query."""
    return AgentState(
        query=query,
        search_queries=[],
        search_results=[],
        report="",
        quality_score=0.0,
        critique="",
        revision_count=0,
        messages=[],
        status="planning",
        error="",
    )


def _state_to_response(state: AgentState) -> ResearchResponse:
    """Convert final AgentState to REST response."""
    report = state.get("report", "")
    results = state.get("search_results", [])
    return ResearchResponse(
        query=state.get("query", ""),
        report=report,
        quality_score=state.get("quality_score", 0.0),
        revision_count=state.get("revision_count", 0),
        search_queries=state.get("search_queries", []),
        source_count=len(set(r.get("url", "") for r in results if r.get("url"))),
        word_count=len(report.split()),
        status=state.get("status", "unknown"),
        error=state.get("error", ""),
    )


# ── Agent event labels ────────────────────────────────────────────────────────
_AGENT_LABELS: dict[str, dict[str, str]] = {
    "planner": {
        "start": "Planning research strategy...",
        "done": "Sub-queries generated",
    },
    "search": {
        "start": "Searching the web...",
        "done": "Web results collected",
    },
    "writer": {
        "start": "Writing research report...",
        "done": "Report drafted",
    },
    "critic": {
        "start": "Evaluating report quality...",
        "done": "Quality review complete",
    },
}


def _chunk_to_event(chunk: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a LangGraph stream chunk to a WebSocket event dict.

    LangGraph stream chunks look like:
        {"planner": {"search_queries": [...], "status": "searching"}}

    Args:
        chunk: Raw LangGraph stream chunk.

    Returns:
        WebSocket event dict with type, agent, and relevant data.
    """
    node_name = next(iter(chunk))
    node_state: dict[str, Any] = chunk[node_name]
    labels = _AGENT_LABELS.get(node_name, {"start": "", "done": "Done"})

    event: dict[str, Any] = {
        "type": "agent_done",
        "agent": node_name,
        "message": labels["done"],
    }

    # Attach relevant data per agent
    if node_name == "planner":
        event["data"] = {"search_queries": node_state.get("search_queries", [])}
    elif node_name == "search":
        results = node_state.get("search_results", [])
        event["data"] = {
            "result_count": len(results),
            "sources": [
                {"title": r.get("title", ""), "url": r.get("url", "")}
                for r in results
            ],
        }
    elif node_name == "writer":
        report = node_state.get("report", "")
        event["data"] = {"word_count": len(report.split())}
    elif node_name == "critic":
        event["data"] = {
            "quality_score": node_state.get("quality_score", 0.0),
            "revision_count": node_state.get("revision_count", 0),
        }

    if node_state.get("error"):
        event["type"] = "agent_error"
        event["error"] = node_state["error"]

    return event


def _complete_event(state: dict[str, Any]) -> dict[str, Any]:
    """
    Build the final WebSocket "complete" event from a finished pipeline state.

    Args:
        state: Final AgentState (as a plain dict) from the streamed run.

    Returns:
        Event dict with the report and summary stats.
    """
    report = state.get("report", "")
    results = state.get("search_results", [])
    return {
        "type": "complete",
        "report": report,
        "quality_score": state.get("quality_score", 0.0),
        "revision_count": state.get("revision_count", 0),
        "search_queries": state.get("search_queries", []),
        "word_count": len(report.split()),
        "source_count": len(set(r.get("url", "") for r in results if r.get("url"))),
        "status": state.get("status", "done"),
    }


# ── REST endpoint ─────────────────────────────────────────────────────────────
@app.post("/api/research", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    """
    Run the full research pipeline synchronously and return the complete result.

    Args:
        request: ResearchRequest with query string.

    Returns:
        ResearchResponse with report, quality score, and metadata.
    """
    loop = asyncio.get_event_loop()
    graph = build_graph()
    initial_state = _make_initial_state(request.query)

    final_state: AgentState = await loop.run_in_executor(
        _executor,
        lambda: graph.invoke(initial_state),
    )

    return _state_to_response(final_state)


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws/research")
async def research_websocket(websocket: WebSocket) -> None:
    """
    Stream research pipeline events over WebSocket.

    Protocol:
      1. Client sends: {"query": "your research question"}
      2. Server streams agent_start / agent_done events per agent
      3. Server sends final "complete" event with full report
      4. Connection closes

    Args:
        websocket: FastAPI WebSocket connection.
    """
    await websocket.accept()

    try:
        # Receive initial query from client
        data = await websocket.receive_json()
        query: str = data.get("query", "").strip()

        if not query:
            await websocket.send_json({"type": "error", "message": "Query cannot be empty."})
            await websocket.close()
            return

        await websocket.send_json({
            "type": "pipeline_start",
            "message": f"Starting research pipeline for: {query}",
        })

        loop = asyncio.get_event_loop()
        graph = build_graph()
        initial_state = _make_initial_state(query)

        # Queue for passing events from sync thread to async WebSocket
        event_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        def _run_pipeline() -> None:
            """Run LangGraph pipeline in thread, push events to queue."""
            try:
                # Each chunk is one node's partial update. Folding them into a
                # copy of the initial state yields this run's final state, so
                # the "complete" event needs no second graph.invoke() (which
                # used to re-run every LLM + Tavily call and return a different report).
                final_state: dict[str, Any] = dict(initial_state)
                failed = False

                for chunk in graph.stream(initial_state):
                    node_name = next(iter(chunk))

                    # Send agent_start for current node
                    labels = _AGENT_LABELS.get(node_name, {"start": "Working..."})
                    loop.call_soon_threadsafe(
                        event_queue.put_nowait,
                        {
                            "type": "agent_start",
                            "agent": node_name,
                            "message": labels["start"],
                        },
                    )

                    # Small delay so UI can show the "start" state briefly
                    import time
                    time.sleep(0.1)

                    # Send agent_done with result data
                    event = _chunk_to_event(chunk)
                    loop.call_soon_threadsafe(event_queue.put_nowait, event)

                    # Check for pipeline error
                    node_state = chunk[node_name]
                    final_state.update(node_state)
                    if node_state.get("status") == "error":
                        loop.call_soon_threadsafe(
                            event_queue.put_nowait,
                            {
                                "type": "error",
                                "message": node_state.get("error", "Unknown error"),
                            },
                        )
                        failed = True
                        break

                if not failed:
                    loop.call_soon_threadsafe(
                        event_queue.put_nowait, _complete_event(final_state)
                    )

                # Signal completion
                loop.call_soon_threadsafe(event_queue.put_nowait, None)

            except Exception as exc:
                loop.call_soon_threadsafe(
                    event_queue.put_nowait,
                    {"type": "error", "message": f"Pipeline failed: {exc}"},
                )
                loop.call_soon_threadsafe(event_queue.put_nowait, None)

        # Start pipeline in background thread
        _executor.submit(_run_pipeline)

        # Stream events to WebSocket as they arrive
        while True:
            event = await event_queue.get()

            if event is None:
                break  # Pipeline finished

            await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok", "service": "research-agent-api"}
