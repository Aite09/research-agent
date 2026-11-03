"""
tests/test_benchmark.py

Checks the benchmark harness itself (percentiles, aggregation, retry
accounting, A/B wiring) with fake Groq + Tavily, so reported numbers are
trustworthy before any real quota is spent.
"""

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

import agents.llm as llm
import agents.planner_agent as planner_agent
from benchmarks import run as bench
from helpers import FakeLLM, FakeTavily, fake_groq_client


@pytest.mark.parametrize(
    ("values", "pct", "expected"),
    [
        ([1.0, 2.0, 3.0, 4.0], 50, 2.5),
        ([1.0, 2.0, 3.0, 4.0, 5.0], 50, 3.0),
        ([10.0], 95, 10.0),
        (list(map(float, range(1, 101))), 95, 95.05),
        ([], 50, None),
    ],
)
def test_percentile_matches_numpy_linear(values: list[float], pct: float, expected: float | None) -> None:
    """Linear interpolation, same as numpy.percentile's default."""
    result = bench.percentile(values, pct)
    assert result == (pytest.approx(expected) if expected is not None else None)


def test_load_queries_skips_comments_cycles_and_offsets(tmp_path: Path) -> None:
    """Comment/blank lines are ignored, questions repeat, and --start offsets the window."""
    path = tmp_path / "q.txt"
    path.write_text("# header\nfirst?\n\nsecond?\nthird?\n")
    assert bench.load_queries(path, 4) == ["first?", "second?", "third?", "first?"]
    assert bench.load_queries(path, 2, start=2) == ["third?", "first?"]


def test_retry_counter_parses_groq_retry_log() -> None:
    """Only the SDK's 'Retrying request' lines count, and their wait seconds are summed."""
    logger = logging.getLogger(bench.GROQ_RETRY_LOGGER)
    counter = bench.RetryCounter()
    logger.addHandler(counter)
    logger.setLevel(logging.INFO)
    try:
        logger.info("Retrying request to %s in %f seconds", "/openai/v1/chat/completions", 2.5)
        logger.info("Retrying request to %s in %f seconds", "/openai/v1/chat/completions", 4.0)
        logger.info("Sending HTTP Request: %s %s", "POST", "/x")
    finally:
        logger.removeHandler(counter)
    assert counter.retries == 2
    assert counter.wait_s == pytest.approx(6.5)


def test_run_pipeline_once_aggregates_llm_records(
    monkeypatch: pytest.MonkeyPatch, install_tavily: Callable[[FakeTavily], FakeTavily]
) -> None:
    """A passing run makes 3 LLM calls whose tokens and cost are summed into the row."""
    # Same canned text for every agent: planner falls back to one sub-query,
    # writer emits it as the report, critic parses Score: 8 and accepts.
    monkeypatch.setattr(llm, "_build_client", lambda: fake_groq_client(content="Score: 8"))
    install_tavily(FakeTavily())

    row = bench.run_pipeline_once("What is RAG?")

    assert row["status"] == "done"
    assert row["llm_calls"] == 3
    assert row["llm_errors"] == 0
    assert row["prompt_tokens"] == 3000
    assert row["completion_tokens"] == 1500
    assert row["cost_usd"] == pytest.approx(3 * llm.estimate_cost_usd(llm.MODEL, 1000, 500))
    assert (row["writer_passes"], row["critic_passes"]) == (1, 1)
    assert row["total_s"] >= sum(row["node_s"].values()) - 0.01
    assert (row["rate_limit_retries"], row["retry_wait_s"]) == (0, 0.0)


def test_run_pipeline_once_counts_sdk_retries(
    monkeypatch: pytest.MonkeyPatch, install_tavily: Callable[[FakeTavily], FakeTavily]
) -> None:
    """Retries the SDK logs during a run land in the row — throttling isn't hidden as latency."""
    retry_log = logging.getLogger(bench.GROQ_RETRY_LOGGER)

    def create(**_: Any) -> SimpleNamespace:
        """Log one SDK-style retry, then succeed."""
        retry_log.info("Retrying request to %s in %f seconds", "/openai/v1/chat/completions", 1.5)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Score: 8"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "_build_client", lambda: client)
    install_tavily(FakeTavily())

    row = bench.run_pipeline_once("What is RAG?")

    assert row["rate_limit_retries"] == 3
    assert row["retry_wait_s"] == pytest.approx(4.5)
    assert not retry_log.handlers  # handler removed after the run


def _pipeline_row(status: str, total: float, retry_wait: float = 0.0) -> dict:
    """Minimal pipeline row for summary tests."""
    return {
        "status": status, "total_s": total, "node_s": {n: total / 4 for n in bench.NODES},
        "cost_usd": 0.01, "prompt_tokens": 100, "completion_tokens": 50, "llm_calls": 3,
        "quality_score": 8.0, "revision_count": 0, "source_count": 9,
        "rate_limit_retries": 1 if retry_wait else 0, "retry_wait_s": retry_wait,
    }


def test_summarize_pipeline_excludes_failures_from_latency() -> None:
    """Failed runs count toward error_rate but not toward latency percentiles."""
    summary = bench.summarize_pipeline([
        _pipeline_row("done", 10.0), _pipeline_row("done", 20.0), _pipeline_row("error", 999.0),
    ])
    assert summary["successful_runs"] == 2
    assert summary["error_rate"] == pytest.approx(0.333)
    assert summary["latency_s"]["p50"] == 15.0
    assert summary["latency_s"]["max"] == 20.0
    assert summary["accepted_first_draft_rate"] == 1.0


def test_summarize_pipeline_reports_latency_without_retry_wait() -> None:
    """Retry backoff is reported and subtracted in the unthrottled latency figure."""
    summary = bench.summarize_pipeline([_pipeline_row("done", 30.0, retry_wait=20.0), _pipeline_row("done", 12.0)])
    assert summary["latency_s"]["p50"] == 21.0
    assert summary["latency_excluding_retry_wait_s"]["p50"] == 11.0
    assert summary["rate_limits"]["runs_with_retries"] == 1
    assert summary["rate_limits"]["retry_wait_s_mean"] == 10.0


def test_search_ab_times_one_cold_mode_per_run(
    monkeypatch: pytest.MonkeyPatch, install_tavily: Callable[[FakeTavily], FakeTavily]
) -> None:
    """Even runs search sequentially, odd runs concurrently, each exactly once."""
    monkeypatch.setattr(planner_agent, "chat", FakeLLM(critic_scores=[]))
    tavily = install_tavily(FakeTavily())

    seq = bench.run_search_ab_once("What is RAG?", index=0, concurrency=4)
    assert (seq["mode"], seq["concurrency"]) == ("sequential", 1)
    assert tavily.max_in_flight == 1

    conc = bench.run_search_ab_once("What is RAG?", index=1, concurrency=4)
    assert (conc["mode"], conc["concurrency"]) == ("concurrent", 4)
    assert tavily.max_in_flight == 2  # FakeLLM planner yields 2 sub-queries
    assert seq["results"] == conc["results"] > 0


def test_summarize_search_ab_reduction() -> None:
    """p50 reduction and speedup come from the per-mode cold medians."""
    def row(mode: str, seconds: float) -> dict:
        """Minimal A/B row."""
        return {"status": "done", "mode": mode, "search_s": seconds, "sub_queries": 4}

    summary = bench.summarize_search_ab([
        row("sequential", 8.0), row("concurrent", 2.0), row("sequential", 6.0), row("concurrent", 2.0),
    ])
    assert summary["sequential_s"] == {"n": 2, "p50": 7.0, "p95": pytest.approx(7.9)}
    assert summary["concurrent_s"]["p50"] == 2.0
    assert summary["p50_reduction_pct"] == pytest.approx(71.4)
    assert summary["p50_speedup"] == 3.5
