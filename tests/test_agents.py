"""
tests/test_agents.py

Unit and graph-level tests for the research pipeline.

Groq and Tavily are replaced with scripted fakes, so the default run makes no
network calls and needs no API keys. One integration test hits the real APIs
and only runs with RUN_INTEGRATION=1.

Run:
    pytest                      # unit + mocked graph tests
    RUN_INTEGRATION=1 pytest    # also the real-API end-to-end run
"""

import os
import threading
from types import SimpleNamespace
from typing import Any, Callable, List, Optional

import pytest
from fastapi.testclient import TestClient

import agents.critic_agent as critic_agent
import agents.llm as llm
import agents.planner_agent as planner_agent
import agents.search_agent as search_agent
import agents.writer_agent as writer_agent
from graph.workflow import build_graph
from helpers import FakeLLM, FakeTavily, SyncExecutor, fake_groq_client, make_result, make_state


# ── Planner ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('["a", "b", "c"]', ["a", "b", "c"]),
        ('```json\n["a", "b"]\n```', ["a", "b"]),
        ("1. first query\n2. second query", ["first query", "second query"]),
        ("- alpha\n* beta", ["alpha", "beta"]),
    ],
)
def test_parse_queries_formats(raw: str, expected: List[str]) -> None:
    """Planner output parses from JSON, fenced JSON, numbered and bulleted lists."""
    assert planner_agent._parse_queries(raw) == expected


def test_planner_node_success(install_llm: Callable[[FakeLLM], FakeLLM]) -> None:
    """Planner writes sub-queries and hands off to search."""
    install_llm(FakeLLM(critic_scores=[]))
    out = planner_agent.planner_node(make_state())
    assert out["search_queries"] == ["rag definition", "rag vs fine-tuning"]
    assert out["status"] == "searching"
    assert out["error"] == ""


def test_planner_node_failure_is_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    """An LLM failure sets error state instead of raising into the graph."""

    def boom(**_: Any) -> str:
        """Simulate a Groq outage."""
        raise RuntimeError("groq down")

    monkeypatch.setattr(planner_agent, "chat", boom)
    out = planner_agent.planner_node(make_state())
    assert out["status"] == "error"
    assert "groq down" in out["error"]
    assert out["search_queries"] == []


# ── Search ───────────────────────────────────────────────────────────────────
def test_sanitize_content_truncates_long_text() -> None:
    """Content over the cap is cut and marked; short content is untouched."""
    assert search_agent._sanitize_content("short") == "short"
    cut = search_agent._sanitize_content("y" * 5000)
    assert len(cut) == search_agent.MAX_CONTENT_CHARS + 3
    assert cut.endswith("...")


@pytest.mark.parametrize(("value", "expected"), [(None, 5), ("2", 2), ("0", 1), ("abc", 5)])
def test_search_concurrency_env(monkeypatch: pytest.MonkeyPatch, value: Optional[str], expected: int) -> None:
    """SEARCH_CONCURRENCY is read per call, clamped to >= 1, and falls back on bad input."""
    if value is not None:
        monkeypatch.setenv("SEARCH_CONCURRENCY", value)
    assert search_agent._search_concurrency() == expected


def test_search_runs_queries_concurrently(
    install_tavily: Callable[[FakeTavily], FakeTavily], monkeypatch: pytest.MonkeyPatch
) -> None:
    """All sub-queries are in flight at once — a 3-party barrier only releases if they overlap."""
    queries = ["q1", "q2", "q3"]
    fake = install_tavily(FakeTavily(barrier=threading.Barrier(len(queries))))
    monkeypatch.setenv("SEARCH_CONCURRENCY", "3")

    out = search_agent.search_node(make_state(search_queries=queries))

    assert fake.max_in_flight == 3
    assert len(out["search_results"]) == 3 * search_agent.MAX_RESULTS_PER_QUERY
    assert out["status"] == "writing"


def test_search_concurrency_one_is_sequential(
    install_tavily: Callable[[FakeTavily], FakeTavily], monkeypatch: pytest.MonkeyPatch
) -> None:
    """SEARCH_CONCURRENCY=1 restores the old one-at-a-time behaviour (benchmark baseline)."""
    fake = install_tavily(FakeTavily())
    monkeypatch.setenv("SEARCH_CONCURRENCY", "1")
    search_agent.search_node(make_state(search_queries=["q1", "q2", "q3"]))
    assert fake.max_in_flight == 1


def test_search_preserves_query_order_and_truncates(install_tavily: Callable[[FakeTavily], FakeTavily]) -> None:
    """Results come back grouped in sub-query order with content capped at 1500 chars."""
    install_tavily(FakeTavily())
    out = search_agent.search_node(make_state(search_queries=["b", "a", "c"]))
    order = [r["query"] for r in out["search_results"]]
    assert order == ["b"] * 3 + ["a"] * 3 + ["c"] * 3
    assert all(len(r["content"]) <= search_agent.MAX_CONTENT_CHARS + 3 for r in out["search_results"])


def test_search_one_failed_query_keeps_others(install_tavily: Callable[[FakeTavily], FakeTavily]) -> None:
    """A single Tavily failure drops that query's results only."""
    install_tavily(FakeTavily(fail_queries=("bad",)))
    out = search_agent.search_node(make_state(search_queries=["good", "bad"]))
    assert {r["query"] for r in out["search_results"]} == {"good"}
    assert out["status"] == "writing"
    assert out["error"] == ""


def test_search_all_failed_still_continues(install_tavily: Callable[[FakeTavily], FakeTavily]) -> None:
    """If every search fails the writer still runs, with an error note."""
    install_tavily(FakeTavily(fail_queries=("x", "y")))
    out = search_agent.search_node(make_state(search_queries=["x", "y"]))
    assert out["search_results"] == []
    assert out["status"] == "writing"
    assert "empty" in out["error"]


def test_search_without_queries_errors() -> None:
    """No planner output → explicit error, no Tavily call."""
    out = search_agent.search_node(make_state(search_queries=[]))
    assert out["status"] == "error"


# ── Writer ───────────────────────────────────────────────────────────────────
def test_sources_list_dedupes_urls() -> None:
    """Duplicate URLs appear once; empty input has a placeholder line."""
    results = [make_result("q", "https://a"), make_result("q", "https://a"), make_result("q", "https://b")]
    sources = writer_agent._build_sources_list(results)
    assert sources.count("https://a") == 1
    assert "https://b" in sources
    assert writer_agent._build_sources_list([]) == "- No sources available"


def test_format_search_results_groups_by_query() -> None:
    """Each sub-query becomes one 'Research Angle' section."""
    results = [make_result("q1", "https://a"), make_result("q2", "https://b"), make_result("q1", "https://c")]
    context = writer_agent._format_search_results(results)
    assert context.count("### Research Angle: q1") == 1
    assert context.count("### Research Angle: q2") == 1


def test_writer_node_appends_sources(install_llm: Callable[[FakeLLM], FakeLLM]) -> None:
    """Writer output gets a generated Sources section and hands off to critic."""
    install_llm(FakeLLM(critic_scores=[]))
    out = writer_agent.writer_node(make_state(search_results=[make_result("q", "https://a", "A")]))
    assert "## Sources" in out["report"]
    assert "[A](https://a)" in out["report"]
    assert out["status"] == "critiquing"


# ── Critic ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Score: 8", 8.0),
        ("score: 7.5\nStrengths", 7.5),
        ("I'd rate this 6/10", 6.0),
        ("Review\n  9  \nDone", 9.0),
        ("Score: 15", 10.0),
        ("Score: 0", 1.0),
        ("no number here", 5.0),
    ],
)
def test_parse_score(raw: str, expected: float) -> None:
    """Scores parse from several formats, clamp to 1–10, and default to 5 (revise)."""
    assert critic_agent._parse_score(raw) == expected


def test_critic_empty_report_errors_without_counting_revision() -> None:
    """Empty report is an error and does not consume a revision."""
    out = critic_agent.critic_node(make_state(report="", revision_count=1))
    assert out["status"] == "error"
    assert out["revision_count"] == 1


@pytest.mark.parametrize(
    ("score", "revision_count", "status", "new_count"),
    [
        (8, 0, "done", 0),     # accepted first time → zero revisions
        (5, 0, "writing", 1),  # first revision requested
        (5, 1, "writing", 2),  # second revision requested
        (5, 2, "done", 2),     # cap reached → accept as-is
    ],
)
def test_critic_decision(
    install_llm: Callable[[FakeLLM], FakeLLM], score: float, revision_count: int, status: str, new_count: int
) -> None:
    """revision_count only increments when a revision is actually requested."""
    install_llm(FakeLLM(critic_scores=[score]))
    out = critic_agent.critic_node(make_state(report="# Draft", revision_count=revision_count))
    assert out["status"] == status
    assert out["revision_count"] == new_count


@pytest.mark.parametrize(("status", "route"), [("writing", "writer"), ("done", "end"), ("error", "end")])
def test_route_after_critic_follows_status(status: str, route: str) -> None:
    """Routing obeys the critic's decision, and errors end the run."""
    assert critic_agent.route_after_critic(make_state(status=status, quality_score=3.0)) == route


# ── LLM wrapper ──────────────────────────────────────────────────────────────
def test_estimate_cost_usd() -> None:
    """List-price cost: 1000 in + 500 out on gpt-oss-120b = $0.000525; unknown model = $0."""
    assert llm.estimate_cost_usd("openai/gpt-oss-120b", 1000, 500) == pytest.approx(0.000525)
    assert llm.estimate_cost_usd("some-other-model", 1000, 500) == 0.0


def test_chat_records_tokens_cost_latency(
    monkeypatch: pytest.MonkeyPatch, records: List[llm.LLMCallRecord]
) -> None:
    """A successful call returns text and emits one complete record."""
    monkeypatch.setattr(llm, "_build_client", lambda: fake_groq_client(content="answer"))
    text = llm.chat("planner", llm.MODEL, "sys", "user q", 0.3, 100)

    assert text == "answer"
    assert len(records) == 1
    rec = records[0]
    assert rec["status"] == "success"
    assert (rec["prompt_tokens"], rec["completion_tokens"]) == (1000, 500)
    assert rec["cost_usd"] == pytest.approx(llm.estimate_cost_usd(llm.MODEL, 1000, 500))
    assert rec["latency_ms"] >= 0
    assert rec["agent"] == "planner"


def test_chat_failure_is_recorded_then_raised(
    monkeypatch: pytest.MonkeyPatch, records: List[llm.LLMCallRecord]
) -> None:
    """Failed calls are logged as errors and still raise so the agent can handle them."""
    monkeypatch.setattr(llm, "_build_client", lambda: fake_groq_client(exc=RuntimeError("429")))
    with pytest.raises(RuntimeError, match="429"):
        llm.chat("writer", llm.MODEL, "sys", "user", 0.7, 100)
    assert records[0]["status"] == "error"
    assert records[0]["response"] is None


def test_chat_ships_log_matching_platform_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """With OBSERVABILITY_URL set, one POST /logs goes out with the user prompt only."""
    posted: List[dict] = []

    def fake_post(url: str, json: dict, timeout: float) -> SimpleNamespace:
        """Capture the request instead of sending it."""
        posted.append({"url": url, "body": json})
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setenv("OBSERVABILITY_URL", "http://obs.local:8000/")
    monkeypatch.setattr(llm, "_shipper", SyncExecutor())
    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setattr(llm, "_build_client", lambda: fake_groq_client())

    llm.chat("critic", llm.MODEL, "SYSTEM PROMPT", "the user prompt", 0.3, 100)

    assert len(posted) == 1
    assert posted[0]["url"] == "http://obs.local:8000/logs"
    body = posted[0]["body"]
    assert body["application_id"] == "research-agent"
    assert body["provider"] == "groq"
    assert body["prompt"] == "the user prompt"
    assert body["total_tokens"] == 1500
    assert body["status"] == "success"
    assert body["tags"] == {"agent": "critic"}


def test_chat_survives_observability_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead observability endpoint never breaks the pipeline."""

    def refuse(*_: Any, **__: Any) -> None:
        """Simulate connection refused."""
        raise ConnectionError("refused")

    monkeypatch.setenv("OBSERVABILITY_URL", "http://localhost:9")
    monkeypatch.setattr(llm, "_shipper", SyncExecutor())
    monkeypatch.setattr(llm.httpx, "post", refuse)
    monkeypatch.setattr(llm, "_build_client", lambda: fake_groq_client(content="still works"))

    assert llm.chat("planner", llm.MODEL, "s", "u", 0.3, 10) == "still works"


def test_chat_without_observability_url_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shipping is opt-in: no URL, no request."""
    monkeypatch.setattr(llm, "_shipper", SyncExecutor())
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: pytest.fail("unexpected POST"))
    monkeypatch.setattr(llm, "_build_client", lambda: fake_groq_client())
    llm.chat("planner", llm.MODEL, "s", "u", 0.3, 10)


@pytest.mark.parametrize(
    ("model", "expect_reasoning"),
    [("openai/gpt-oss-120b", True), ("openai/gpt-oss-20b", True), ("qwen/qwen3.8-27b", False)],
)
def test_chat_sets_low_reasoning_only_for_gpt_oss(
    monkeypatch: pytest.MonkeyPatch, model: str, expect_reasoning: bool
) -> None:
    """gpt-oss calls get reasoning_effort=low and no reasoning text; other models get neither."""
    sent: List[dict] = []

    def create(**kwargs: Any) -> SimpleNamespace:
        """Capture request kwargs and return a minimal completion."""
        sent.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "_build_client", lambda: client)
    llm.chat("planner", model, "s", "u", 0.3, 10)

    if expect_reasoning:
        assert sent[0]["reasoning_effort"] == "low"
        assert sent[0]["include_reasoning"] is False
    else:
        assert "reasoning_effort" not in sent[0]
        assert "include_reasoning" not in sent[0]


# ── Full graph (mocked) ──────────────────────────────────────────────────────
def test_graph_accepts_first_draft(
    install_llm: Callable[[FakeLLM], FakeLLM], install_tavily: Callable[[FakeTavily], FakeTavily]
) -> None:
    """Good first draft → one writer pass, zero revisions, status done."""
    fake = install_llm(FakeLLM(critic_scores=[8]))
    install_tavily(FakeTavily())
    final = build_graph().invoke(make_state())

    assert final["status"] == "done"
    assert final["revision_count"] == 0
    assert (fake.count("writer"), fake.count("critic")) == (1, 1)


def test_graph_revises_once_then_accepts(
    install_llm: Callable[[FakeLLM], FakeLLM], install_tavily: Callable[[FakeTavily], FakeTavily]
) -> None:
    """Low then high score → one revision whose prompt carries the critique."""
    fake = install_llm(FakeLLM(critic_scores=[5, 8]))
    install_tavily(FakeTavily())
    final = build_graph().invoke(make_state())

    assert final["status"] == "done"
    assert final["revision_count"] == 1
    assert final["quality_score"] == 8.0
    writer_prompts = [c["user_prompt"] for c in fake.calls if c["agent"] == "writer"]
    assert "Revision Instructions" not in writer_prompts[0]
    assert "Revision Instructions" in writer_prompts[1]


def test_graph_caps_at_two_revisions(
    install_llm: Callable[[FakeLLM], FakeLLM], install_tavily: Callable[[FakeTavily], FakeTavily]
) -> None:
    """Always-low score → exactly 2 revisions (3 drafts), then accept. Regression for the old off-by-one."""
    fake = install_llm(FakeLLM(critic_scores=[4, 4, 4]))
    install_tavily(FakeTavily())
    final = build_graph().invoke(make_state())

    assert final["status"] == "done"
    assert final["revision_count"] == critic_agent.MAX_REVISIONS == 2
    assert (fake.count("writer"), fake.count("critic")) == (3, 3)


def test_graph_critic_error_ends_run(
    install_llm: Callable[[FakeLLM], FakeLLM], install_tavily: Callable[[FakeTavily], FakeTavily]
) -> None:
    """A critic failure ends the run instead of looping back to the writer."""
    fake = install_llm(FakeLLM(critic_scores=[], critic_error=True))
    install_tavily(FakeTavily())
    final = build_graph().invoke(make_state())

    assert final["status"] == "error"
    assert fake.count("writer") == 1


def test_graph_planner_error_ends_before_search(
    monkeypatch: pytest.MonkeyPatch,
    install_llm: Callable[[FakeLLM], FakeLLM],
    install_tavily: Callable[[FakeTavily], FakeTavily],
) -> None:
    """A Planner failure ends the run — no Tavily search, no Writer LLM call on empty research."""
    fake = install_llm(FakeLLM(critic_scores=[8]))
    tavily = install_tavily(FakeTavily())

    def planner_down(**_: Any) -> str:
        """Simulate the model being unavailable."""
        raise RuntimeError("404 model_not_found")

    monkeypatch.setattr(planner_agent, "chat", planner_down)
    final = build_graph().invoke(make_state())

    assert final["status"] == "error"
    assert "model_not_found" in final["error"]
    assert fake.count("writer") == 0
    assert tavily.max_in_flight == 0


def test_graph_search_error_ends_before_writer(
    monkeypatch: pytest.MonkeyPatch, install_llm: Callable[[FakeLLM], FakeLLM]
) -> None:
    """A Search setup failure (e.g. missing Tavily key) ends the run before the Writer."""
    fake = install_llm(FakeLLM(critic_scores=[8]))

    def no_key() -> None:
        """Simulate a missing TAVILY_API_KEY."""
        raise EnvironmentError("TAVILY_API_KEY not set in environment.")

    monkeypatch.setattr(search_agent, "_build_client", no_key)
    final = build_graph().invoke(make_state())

    assert final["status"] == "error"
    assert fake.count("writer") == 0


# ── API ──────────────────────────────────────────────────────────────────────
def test_websocket_runs_pipeline_once(
    install_llm: Callable[[FakeLLM], FakeLLM], install_tavily: Callable[[FakeTavily], FakeTavily]
) -> None:
    """WebSocket streams every agent and ends with 'complete' from the same single run."""
    from api.main import app

    fake = install_llm(FakeLLM(critic_scores=[8]))
    install_tavily(FakeTavily())

    events: List[dict] = []
    with TestClient(app).websocket_connect("/ws/research") as ws:
        ws.send_json({"query": "What is RAG?"})
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] in ("complete", "error"):
                break

    done_agents = [e["agent"] for e in events if e["type"] == "agent_done"]
    assert done_agents == ["planner", "search", "writer", "critic"]
    assert events[-1]["type"] == "complete"
    assert events[-1]["status"] == "done"
    assert events[-1]["quality_score"] == 8.0
    # Before the fix, a second graph.invoke() doubled every LLM call.
    assert fake.count("planner") == 1


def test_websocket_rejects_empty_query() -> None:
    """Blank queries get an error event, not a pipeline run."""
    from api.main import app

    with TestClient(app).websocket_connect("/ws/research") as ws:
        ws.send_json({"query": "   "})
        assert ws.receive_json()["type"] == "error"


# ── Integration (real APIs) ──────────────────────────────────────────────────
@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1 to call real Groq + Tavily")
def test_full_pipeline_real_apis() -> None:
    """End-to-end run against live Groq + Tavily (uses API quota)."""
    from dotenv import load_dotenv

    load_dotenv()
    final = build_graph().invoke(make_state())

    assert final["status"] == "done", final["error"]
    assert final["search_results"]
    assert "## Sources" in final["report"]
    assert 1.0 <= final["quality_score"] <= 10.0
