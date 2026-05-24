"""
main.py

Entry point for the Multi-Agent Research & Report Generator.

Loads environment variables, builds the LangGraph pipeline, runs a
research query, and prints the final report cleanly in the terminal.

Usage:
    python main.py
    python main.py "your custom research question here"
"""

import sys
from dotenv import load_dotenv

from graph.state import AgentState
from graph.workflow import build_graph

# ── Default test query ────────────────────────────────────────────────────────
DEFAULT_QUERY = "What is the impact of AI on the Toronto job market in 2025?"


def run_pipeline(query: str) -> AgentState:
    """
    Build and execute the research pipeline for a given query.

    Args:
        query: The user's research question.

    Returns:
        Final AgentState after the pipeline completes.
    """
    print("\n" + "=" * 60)
    print("  MULTI-AGENT RESEARCH PIPELINE")
    print("=" * 60)
    print(f"  Query: {query}")
    print("=" * 60 + "\n")

    graph = build_graph()

    initial_state: AgentState = {
        "query": query,
        "search_queries": [],
        "search_results": [],
        "report": "",
        "quality_score": 0.0,
        "critique": "",
        "revision_count": 0,
        "messages": [],
        "status": "planning",
        "error": "",
    }

    final_state: AgentState = graph.invoke(initial_state)
    return final_state


def print_report(state: AgentState) -> None:
    """
    Print the final research report cleanly to the terminal,
    followed by a stats summary.

    Args:
        state: Final AgentState returned by the pipeline.
    """
    report = state.get("report", "")
    error = state.get("error", "")
    status = state.get("status", "unknown")

    print("\n" + "=" * 60)
    print("  PIPELINE STATUS")
    print("=" * 60)
    print(f"  Status : {status}")
    print(f"  Error  : {error or 'none'}")
    print("=" * 60 + "\n")

    if report:
        # Print the full markdown report
        print("=" * 60)
        print("  RESEARCH REPORT")
        print("=" * 60 + "\n")
        print(report)

        # Stats summary
        word_count = len(report.split())
        results = state.get("search_results", [])
        source_count = len(set(r.get("url", "") for r in results if r.get("url")))
        queries = state.get("search_queries", [])

        score = state.get("quality_score", 0.0)
        revisions = state.get("revision_count", 0)
        score_bar = "⭐" * int(score) + "☆" * (10 - int(score))

        print("\n" + "─" * 60)
        print(f"  📊 Word count    : {word_count}")
        print(f"  🔗 Sources used  : {source_count}")
        print(f"  🔍 Queries run   : {len(queries)}")
        print(f"  🔄 Revisions     : {revisions}")
        print(f"  ⭐ Quality score : {score}/10  {score_bar}")
        print("─" * 60 + "\n")

    else:
        print("No report generated.")
        if error:
            print(f"Reason: {error}")


def main() -> None:
    """
    Main entry point. Loads .env, resolves query, runs pipeline, prints report.
    """
    load_dotenv()

    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY

    final_state = run_pipeline(query)
    print_report(final_state)

    if final_state.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
