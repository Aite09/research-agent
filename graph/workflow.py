"""
graph/workflow.py

Builds the LangGraph StateGraph that wires agents together into
an autonomous pipeline.

Week 3 graph:
    START → planner → search → writer → critic → END
                                           ↑         |
                                           └─────────┘
                                 (score < 7 → revise, max 2 loops)

Why conditional edges?
  After the Critic scores the report, the pipeline branches:
  - Score >= 7 or max revisions hit → END (accept report)
  - Score < 7 and revisions left    → writer (revise report)
  LangGraph's add_conditional_edges handles this routing automatically
  based on the return value of route_after_critic().
"""

from langgraph.graph import StateGraph, END

from graph.state import AgentState
from agents.planner_agent import planner_node
from agents.search_agent import search_node
from agents.writer_agent import writer_node
from agents.critic_agent import critic_node, route_after_critic


def _continue_unless_error(next_node: str):
    """
    Build a router that stops the run when the previous node set status "error".

    Without this, a Planner failure still ran Search and the Writer (an LLM
    call with no research material) before the Critic finally gave up.

    Args:
        next_node: Node to run when the previous one succeeded.

    Returns:
        Routing function returning next_node or "end".
    """

    def _route(state: AgentState) -> str:
        """Return "end" on error, else the next node name."""
        return "end" if state.get("status") == "error" else next_node

    return _route


def build_graph() -> StateGraph:
    """
    Construct and compile the LangGraph StateGraph.

    Graph structure (Week 3):
        START → planner → search → writer → critic → END
                                               ↑         |
                                               └─────────┘

    Returns:
        Compiled LangGraph StateGraph ready for invocation.
    """
    graph = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    graph.add_node("planner", planner_node)
    graph.add_node("search", search_node)
    graph.add_node("writer", writer_node)
    graph.add_node("critic", critic_node)

    # ── Define edges ──────────────────────────────────────────────────────────
    graph.set_entry_point("planner")
    # Planner/Search failures end the run; Search with zero results still
    # continues (status "writing") so the Writer can report the gap.
    graph.add_conditional_edges("planner", _continue_unless_error("search"), {"search": "search", "end": END})
    graph.add_conditional_edges("search", _continue_unless_error("writer"), {"writer": "writer", "end": END})
    graph.add_edge("writer", "critic")

    # Conditional routing after critic:
    # route_after_critic() returns "end" or "writer"
    # LangGraph maps those strings to actual graph destinations below
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "end": END,
            "writer": "writer",
        },
    )

    return graph.compile()
