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
    graph.add_edge("planner", "search")
    graph.add_edge("search", "writer")
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
