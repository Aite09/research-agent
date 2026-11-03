"""
agents/planner_agent.py

Planner Agent — decomposes a broad user research query into 3–5 focused
sub-queries that the Search agent will use to gather targeted web results.

Why this step?
  A single broad query like "AI impact on Toronto jobs" returns generic results.
  Breaking it into focused sub-queries (job displacement stats, new roles created,
  sector-specific impacts, etc.) gives the Writer much richer, structured material.
"""

import json
from typing import List

from agents.llm import MODEL, chat
from graph.state import AgentState

# ── Constants ────────────────────────────────────────────────────────────────


def _parse_queries(raw: str) -> List[str]:
    """
    Parse the LLM response into a clean list of sub-query strings.

    Tries JSON first; falls back to line-by-line parsing so a malformed
    JSON response doesn't crash the pipeline.

    Args:
        raw: Raw text response from the LLM.

    Returns:
        List of sub-query strings (3–5 items).
    """
    # Attempt 1: LLM returned a JSON array
    try:
        # Strip markdown code fences if present
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        queries = json.loads(cleaned)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            return [q.strip() for q in queries if q.strip()]
    except (json.JSONDecodeError, ValueError):
        pass

    # Attempt 2: One query per line, strip numbering/bullets
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading "1. " / "- " / "* "
        for prefix in ("- ", "* "):
            if line.startswith(prefix):
                line = line[len(prefix):]
        if line[0].isdigit() and ". " in line[:4]:
            line = line.split(". ", 1)[1]
        lines.append(line)

    return lines if lines else [raw.strip()]


def planner_node(state: AgentState) -> dict:
    """
    LangGraph node: Planner Agent.

    Reads:
        state["query"] — the original user research question.

    Writes:
        search_queries — list of 3–5 focused sub-queries.
        status         — updated to "searching".
        messages       — appended with planner turn.
        error          — set if LLM call fails.

    Args:
        state: Current AgentState.

    Returns:
        Dict of updated state fields only.
    """
    query = state["query"]
    print(f"[PLANNER] Starting — query: {query}")

    try:
        system_prompt = (
            "You are a research planning assistant. Your job is to decompose a broad "
            "research question into 3–5 precise, focused sub-queries. Each sub-query "
            "should target a specific angle of the topic so that web searches return "
            "concrete, useful information.\n\n"
            "Rules:\n"
            "- Return ONLY a JSON array of strings. No explanation, no markdown, no extra text.\n"
            "- Each sub-query must be a complete, searchable question or phrase.\n"
            "- Sub-queries must be distinct — no overlap.\n"
            "- Aim for 4 sub-queries unless 3 or 5 is clearly more appropriate.\n\n"
            'Example output: ["sub-query 1", "sub-query 2", "sub-query 3", "sub-query 4"]'
        )

        user_prompt = f"Research question: {query}"

        raw_output = chat(
            agent="planner",
            model=MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=500,
        )
        search_queries = _parse_queries(raw_output)

        print(f"[PLANNER] Done — generated {len(search_queries)} sub-queries:")
        for i, q in enumerate(search_queries, 1):
            print(f"  {i}. {q}")

        return {
            "search_queries": search_queries,
            "status": "searching",
            "messages": state.get("messages", []) + [
                {"role": "planner", "content": f"Generated sub-queries: {search_queries}"}
            ],
            "error": "",
        }

    except Exception as exc:
        error_msg = f"Planner agent failed: {exc}"
        print(f"[PLANNER] ERROR — {error_msg}")
        return {
            "search_queries": [],
            "status": "error",
            "error": error_msg,
            "messages": state.get("messages", []) + [
                {"role": "planner", "content": f"ERROR: {error_msg}"}
            ],
        }
