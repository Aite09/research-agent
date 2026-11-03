"""
agents/search_agent.py

Search Agent — takes the sub-queries from the Planner and uses Tavily to
fetch real web results for each one. Sub-queries run concurrently on a thread
pool (SEARCH_CONCURRENCY, default 5) since each Tavily call is network-bound.
Results are truncated to 1500 chars each to keep LLM context manageable.

Why Tavily?
  Tavily is purpose-built for AI agents — it returns cleaned, readable page
  content (not raw HTML) and is designed for LLM consumption. Each result
  includes a URL, title, and extracted body text.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from typing import List

from tavily import TavilyClient
from graph.state import AgentState, SearchResult

# ── Constants ────────────────────────────────────────────────────────────────
MAX_RESULTS_PER_QUERY = 3    # Tavily results per sub-query
MAX_CONTENT_CHARS = 1500     # Truncate content to keep LLM context lean
DEFAULT_SEARCH_CONCURRENCY = 5


def _build_client() -> TavilyClient:
    """Initialise Tavily client from environment."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise EnvironmentError("TAVILY_API_KEY not set in environment.")
    return TavilyClient(api_key=api_key)


def _search_concurrency() -> int:
    """
    Read the max number of parallel Tavily requests from SEARCH_CONCURRENCY.

    Read per call (not at import) so benchmarks/run.py can compare sequential
    (1) against concurrent search inside one process.

    Returns:
        Worker count >= 1; falls back to DEFAULT_SEARCH_CONCURRENCY if unset or invalid.
    """
    try:
        return max(1, int(os.getenv("SEARCH_CONCURRENCY", DEFAULT_SEARCH_CONCURRENCY)))
    except ValueError:
        return DEFAULT_SEARCH_CONCURRENCY


def _sanitize_content(content: str) -> str:
    """
    Truncate content to MAX_CONTENT_CHARS.

    Keeps content safe for LLM consumption — avoids oversized context
    windows and strips any runaway page dumps.

    Args:
        content: Raw content string from Tavily.

    Returns:
        Truncated string with ellipsis appended if cut.
    """
    if len(content) <= MAX_CONTENT_CHARS:
        return content
    return content[:MAX_CONTENT_CHARS] + "..."


def _search_single_query(client: TavilyClient, query: str) -> List[SearchResult]:
    """
    Run a single Tavily search and return structured SearchResult objects.

    Args:
        client: Initialised TavilyClient.
        query:  Sub-query string to search.

    Returns:
        List of SearchResult dicts. Empty list if search fails.
    """
    try:
        response = client.search(
            query=query,
            max_results=MAX_RESULTS_PER_QUERY,
            search_depth="advanced",  # Returns fuller content than "basic"
        )
        results: List[SearchResult] = []
        for item in response.get("results", []):
            results.append(
                SearchResult(
                    query=query,
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    content=_sanitize_content(item.get("content", "")),
                )
            )
        return results

    except Exception as exc:
        print(f"[SEARCH] WARNING — query failed: '{query}' | Error: {exc}")
        # Return empty — Writer handles missing results gracefully
        return []


def search_node(state: AgentState) -> dict:
    """
    LangGraph node: Search Agent.

    Reads:
        state["search_queries"] — sub-queries from Planner.

    Writes:
        search_results — list of SearchResult dicts from all queries.
        status         — updated to "writing".
        messages       — appended with search summary.
        error          — set if all searches fail.

    Args:
        state: Current AgentState.

    Returns:
        Dict of updated state fields only.
    """
    search_queries = state.get("search_queries", [])
    print(f"[SEARCH] Starting — {len(search_queries)} queries to search")

    # If Planner failed and produced no queries, propagate gracefully
    if not search_queries:
        error_msg = "Search agent received no queries from Planner."
        print(f"[SEARCH] ERROR — {error_msg}")
        return {
            "search_results": [],
            "status": "error",
            "error": error_msg,
            "messages": state.get("messages", []) + [
                {"role": "search", "content": f"ERROR: {error_msg}"}
            ],
        }

    try:
        client = _build_client()
        all_results: List[SearchResult] = []

        workers = min(_search_concurrency(), len(search_queries))
        print(f"[SEARCH] Running {len(search_queries)} queries, concurrency={workers}")

        # map() returns results in input order, so output stays grouped by
        # sub-query exactly as the sequential loop produced it.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            per_query = list(pool.map(lambda q: _search_single_query(client, q), search_queries))

        for query, results in zip(search_queries, per_query):
            all_results.extend(results)
            print(f"[SEARCH]   '{query}' → {len(results)} results")

        total = len(all_results)
        print(f"[SEARCH] Done — {total} total results collected across {len(search_queries)} queries")

        if total == 0:
            # All searches failed — still continue, Writer will note lack of sources
            return {
                "search_results": [],
                "status": "writing",
                "error": "All Tavily searches returned empty results.",
                "messages": state.get("messages", []) + [
                    {"role": "search", "content": "WARNING: No search results retrieved."}
                ],
            }

        return {
            "search_results": all_results,
            "status": "writing",
            "error": "",
            "messages": state.get("messages", []) + [
                {"role": "search", "content": f"Collected {total} results from {len(search_queries)} queries."}
            ],
        }

    except Exception as exc:
        error_msg = f"Search agent failed: {exc}"
        print(f"[SEARCH] ERROR — {error_msg}")
        return {
            "search_results": [],
            "status": "error",
            "error": error_msg,
            "messages": state.get("messages", []) + [
                {"role": "search", "content": f"ERROR: {error_msg}"}
            ],
        }
