"""
tests/test_benchmark.py

Checks the benchmark harness itself (percentiles, aggregation, A/B wiring)
with fake Groq + Tavily, so reported numbers are trustworthy before any
real quota is spent.
"""

from pathlib import Path
from typing import Callable

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


def test_load_queries_skips_comments_and_cycles(tmp_path: Path) -> None:
    """Comment/blank lines are ignored and questions repeat when runs > questions."""
    path = tmp_path / "q.txt"
    path.write_text("# header\nfirst?\n\nsecond?\n")
    assert bench.load_queries(path, 3) == ["first?", "second?", "first?"]


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


def test_summarize_pipeline_excludes_failures_from_latency() -> None:
    """Failed runs count toward error_rate but not toward latency percentiles."""
    def row(status: str, total: float) -> dict:
        """Minimal pipeline row."""
        return {
            "status": status, "total_s": total, "node_s": {n: total / 4 for n in bench.NODES},
            "cost_usd": 0.01, "prompt_tokens": 100, "completion_tokens": 50, "llm_calls": 3,
            "quality_score": 8.0, "revision_count": 0, "source_count": 9,
        }

    summary = bench.summarize_pipeline([row("done", 10.0), row("done", 20.0), row("error", 999.0)])
    assert summary["successful_runs"] == 2
    assert summary["error_rate"] == pytest.approx(0.333)
    assert summary["latency_s"]["p50"] == 15.0
    assert summary["latency_s"]["max"] == 20.0
    assert summary["accepted_first_draft_rate"] == 1.0


def test_search_ab_compares_identical_sub_queries(
    monkeypatch: pytest.MonkeyPatch, install_tavily: Callable[[FakeTavily], FakeTavily]
) -> None:
    """Both sides search the same planner output and return the same result count."""
    monkeypatch.setattr(planner_agent, "chat", FakeLLM(critic_scores=[]))
    install_tavily(FakeTavily())

    row = bench.run_search_ab_once("What is RAG?", index=1, concurrency=4)

    assert row["status"] == "done"
    assert row["first"] == "concurrent"
    assert row["sequential_results"] == row["concurrent_results"] > 0
    assert row["speedup"] is not None


def test_summarize_search_ab_reduction() -> None:
    """p50 reduction is computed from the two medians."""
    rows = [
        {"status": "done", "sequential_s": 8.0, "concurrent_s": 2.0, "speedup": 4.0, "sub_queries": 4},
        {"status": "done", "sequential_s": 6.0, "concurrent_s": 2.0, "speedup": 3.0, "sub_queries": 4},
    ]
    summary = bench.summarize_search_ab(rows)
    assert summary["sequential_s"]["p50"] == 7.0
    assert summary["concurrent_s"]["p50"] == 2.0
    assert summary["p50_reduction_pct"] == pytest.approx(71.4)
