"""
agents/writer_agent.py

Writer Agent — synthesizes raw search results from the Search agent into
a structured, readable markdown research report.

Why a dedicated Writer agent?
  Raw search results are fragmented snippets from multiple sources. The
  Writer's job is to act like a senior analyst: read all sources, identify
  patterns, resolve conflicts, and produce a coherent narrative report.

Uses Groq API (llama-3.3-70b-versatile) for fast, high-quality synthesis.
"""

from typing import List

from agents.llm import chat

from graph.state import AgentState, SearchResult

# ── Constants ────────────────────────────────────────────────────────────────
MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 4000
TEMPERATURE = 0.7   # Higher than Planner — Writer benefits from fluency


def _format_search_results(results: List[SearchResult]) -> str:
    """
    Format search results into a structured context block for the LLM prompt.

    Groups results by their originating sub-query so the Writer can see
    which angle each source addresses.

    Args:
        results: List of SearchResult dicts from Search agent.

    Returns:
        Formatted string ready for LLM context injection.
    """
    if not results:
        return "No search results available."

    # Group by query
    grouped: dict[str, List[SearchResult]] = {}
    for r in results:
        query = r.get("query", "Unknown")
        grouped.setdefault(query, []).append(r)

    sections: List[str] = []
    for query, items in grouped.items():
        sections.append(f"### Research Angle: {query}")
        for i, item in enumerate(items, 1):
            sections.append(
                f"**Source {i}: {item.get('title', 'No title')}**\n"
                f"URL: {item.get('url', '')}\n"
                f"Content: {item.get('content', '')}\n"
            )

    return "\n".join(sections)


def _build_sources_list(results: List[SearchResult]) -> str:
    """
    Build a deduplicated markdown sources list from search results.

    Args:
        results: List of SearchResult dicts.

    Returns:
        Markdown-formatted sources string.
    """
    seen_urls: set[str] = set()
    sources: List[str] = []

    for r in results:
        url = r.get("url", "")
        title = r.get("title", "Source")
        if url and url not in seen_urls:
            seen_urls.add(url)
            sources.append(f"- [{title}]({url})")

    return "\n".join(sources) if sources else "- No sources available"


def writer_node(state: AgentState) -> dict:
    """
    LangGraph node: Writer Agent.

    Reads:
        state["query"]          — original user research question.
        state["search_results"] — raw results from Search agent.
        state["critique"]       — Critic feedback (empty on first pass).
        state["revision_count"] — how many revisions have occurred.

    Writes:
        report   — full structured markdown report.
        status   — updated to "critiquing".
        messages — appended with writer turn.
        error    — set if LLM call fails.

    Args:
        state: Current AgentState.

    Returns:
        Dict of updated state fields only.
    """
    query = state["query"]
    search_results = state.get("search_results", [])
    critique = state.get("critique", "")
    revision_count = state.get("revision_count", 0)

    print(f"[WRITER] Starting — query: {query}")
    print(f"[WRITER] Sources available: {len(search_results)} | Revision: {revision_count}")

    try:
        context = _format_search_results(search_results)
        sources_md = _build_sources_list(search_results)

        # If this is a revision, include the Critic's feedback in the prompt
        revision_instruction = ""
        if critique and revision_count > 0:
            revision_instruction = (
                f"\n\n## Revision Instructions\n"
                f"This is revision #{revision_count}. A quality review found these issues:\n"
                f"{critique}\n"
                f"Address ALL points above in this revised report.\n"
            )

        system_prompt = (
            "You are a senior research analyst. Your job is to synthesize web research "
            "into a clear, structured, and insightful report for an intelligent reader.\n\n"
            "Report requirements:\n"
            "1. Write in clear, professional prose — no bullet-point dumps\n"
            "2. Cite specific facts and figures from the sources\n"
            "3. Identify patterns and insights across multiple sources\n"
            "4. Be balanced — include both opportunities and challenges\n"
            "5. Structure EXACTLY as shown in the format below\n\n"
            "Output format (use exactly these markdown headers):\n"
            "# Research Report: {TOPIC}\n\n"
            "## Executive Summary\n"
            "(2-3 sentences capturing the core answer)\n\n"
            "## Key Findings\n"
            "(Subsections per major theme found in research)\n\n"
            "## Analysis\n"
            "(Deeper insights, patterns, implications)\n\n"
            "## Conclusion\n"
            "(What this means, what to watch for)\n\n"
            "## Sources\n"
            "(Leave this section EMPTY — do not write anything here. Sources are added after your output.)\n\n"
            "Write the full report now. Be thorough but concise. Minimum 400 words."
        )

        user_prompt = (
            f"Research Question: {query}\n\n"
            f"## Research Materials\n\n"
            f"{context}"
            f"{revision_instruction}"
        )

        report_body = chat(
            agent="writer",
            model=MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

        # Append sources section to the report
        full_report = (
            f"{report_body.strip()}\n\n"
            f"## Sources\n\n"
            f"{sources_md}\n\n"
            f"---\n"
            f"*Report generated from {len(search_results)} sources across "
            f"{len(set(r.get('query','') for r in search_results))} research angles.*"
        )

        word_count = len(full_report.split())
        source_count = len(set(r.get("url", "") for r in search_results if r.get("url")))

        print(f"[WRITER] Done — {word_count} words, {source_count} unique sources")

        return {
            "report": full_report,
            "status": "critiquing",
            "messages": state.get("messages", []) + [
                {
                    "role": "writer",
                    "content": f"Report generated: {word_count} words, {source_count} sources.",
                }
            ],
            "error": "",
        }

    except Exception as exc:
        error_msg = f"Writer agent failed: {exc}"
        print(f"[WRITER] ERROR — {error_msg}")
        return {
            "report": "",
            "status": "error",
            "error": error_msg,
            "messages": state.get("messages", []) + [
                {"role": "writer", "content": f"ERROR: {error_msg}"}
            ],
        }
