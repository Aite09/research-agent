"""
tests/conftest.py

Fixtures shared by all test modules: env isolation and installers that swap
Groq/Tavily for the fakes in tests/helpers.py.
"""

from typing import Callable, Iterator, List

import pytest

import agents.critic_agent as critic_agent
import agents.llm as llm
import agents.planner_agent as planner_agent
import agents.search_agent as search_agent
import agents.writer_agent as writer_agent
from helpers import FakeLLM, FakeTavily


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests off the network regardless of the developer's .env."""
    monkeypatch.delenv("OBSERVABILITY_URL", raising=False)
    monkeypatch.delenv("SEARCH_CONCURRENCY", raising=False)


@pytest.fixture
def install_llm(monkeypatch: pytest.MonkeyPatch) -> Callable[[FakeLLM], FakeLLM]:
    """Patch every agent's chat() with the given FakeLLM."""

    def _install(fake: FakeLLM) -> FakeLLM:
        """Apply the patch and return the fake for assertions."""
        for module in (planner_agent, writer_agent, critic_agent):
            monkeypatch.setattr(module, "chat", fake)
        return fake

    return _install


@pytest.fixture
def install_tavily(monkeypatch: pytest.MonkeyPatch) -> Callable[[FakeTavily], FakeTavily]:
    """Patch the search agent's Tavily client with the given FakeTavily."""

    def _install(fake: FakeTavily) -> FakeTavily:
        """Apply the patch and return the fake for assertions."""
        monkeypatch.setattr(search_agent, "_build_client", lambda: fake)
        return fake

    return _install


@pytest.fixture
def records() -> Iterator[List[llm.LLMCallRecord]]:
    """Capture every LLMCallRecord emitted during a test."""
    captured: List[llm.LLMCallRecord] = []
    llm.add_listener(captured.append)
    yield captured
    llm.remove_listener(captured.append)
