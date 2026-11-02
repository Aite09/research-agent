"""
tests/helpers.py

Shared fakes for Groq, Tavily and the observability shipper, plus state builders.
Imported by test modules; fixtures that install these live in conftest.py.
"""

import threading
import time
from types import SimpleNamespace
from typing import Any, Callable, List, Optional

from graph.state import AgentState, SearchResult


# ── Builders ──────────────────────────────────────────────────────────────────
def make_state(**overrides: Any) -> AgentState:
    """Return a zero-value AgentState with selected fields overridden."""
    state = AgentState(
        query="What is retrieval-augmented generation?",
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
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def make_result(query: str, url: str, title: str = "Title") -> SearchResult:
    """Return one SearchResult for tests."""
    return SearchResult(query=query, url=url, title=title, content="body")


class FakeLLM:
    """Scripted stand-in for agents.llm.chat, answering by agent name."""

    def __init__(self, critic_scores: List[float], critic_error: bool = False) -> None:
        """
        Args:
            critic_scores: Scores the critic returns, in call order.
            critic_error:  If True, every critic call raises.
        """
        self.calls: List[dict] = []
        self._scores = list(critic_scores)
        self._critic_error = critic_error

    def __call__(
        self,
        agent: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Record the call and return a canned response for the agent."""
        self.calls.append({"agent": agent, "user_prompt": user_prompt})
        if agent == "planner":
            return '["rag definition", "rag vs fine-tuning"]'
        if agent == "writer":
            return "# Research Report: RAG\n\n## Executive Summary\nRAG grounds answers."
        if agent == "critic":
            if self._critic_error:
                raise RuntimeError("groq 503")
            return f"Score: {self._scores.pop(0)}\n\nStrengths:\n- clear"
        raise AssertionError(f"unexpected agent {agent}")

    def count(self, agent: str) -> int:
        """Number of calls made by one agent."""
        return sum(1 for c in self.calls if c["agent"] == agent)


class FakeTavily:
    """Thread-safe Tavily stand-in that tracks how many searches overlap."""

    def __init__(
        self,
        fail_queries: tuple[str, ...] = (),
        barrier: Optional[threading.Barrier] = None,
    ) -> None:
        """
        Args:
            fail_queries: Queries that raise instead of returning results.
            barrier:      If set, every search waits on it — proves N calls overlap.
        """
        self.fail_queries = fail_queries
        self.barrier = barrier
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def search(self, query: str, max_results: int, search_depth: str) -> dict:
        """Return max_results fake hits for the query."""
        with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            if self.barrier is not None:
                self.barrier.wait(timeout=5)
            else:
                time.sleep(0.02)
            if query in self.fail_queries:
                raise RuntimeError("tavily 429")
            return {
                "results": [
                    {"url": f"https://example.com/{query}/{i}", "title": f"{query} {i}", "content": "x" * 2000}
                    for i in range(max_results)
                ]
            }
        finally:
            with self._lock:
                self._in_flight -= 1


class SyncExecutor:
    """Executor stub that runs submitted work immediately on the caller thread."""

    def submit(self, fn: Callable[..., None], *args: Any) -> None:
        """Run fn(*args) now."""
        fn(*args)


def fake_groq_client(
    content: str = "hello",
    prompt_tokens: int = 1000,
    completion_tokens: int = 500,
    exc: Optional[Exception] = None,
) -> SimpleNamespace:
    """Build an object shaped like groq.Groq with a scripted completions.create."""

    def create(**_: Any) -> SimpleNamespace:
        """Return a canned completion or raise exc."""
        if exc is not None:
            raise exc
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        )

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
