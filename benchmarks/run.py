"""
benchmarks/run.py

Measures the research pipeline against live Groq + Tavily so every number
quoted about this project comes from a reproducible run.

Two modes:

  pipeline  (default)
      Runs the full graph on N questions from benchmarks/queries.txt and records,
      per run: end-to-end latency, time per agent, LLM calls, tokens, list-price
      cost, critic score and revisions. Summary reports p50/p95 latency.

  search-ab
      A/B test of the Search stage only: sequential (SEARCH_CONCURRENCY=1) vs
      concurrent. Each question is planned, then searched ONCE in one mode
      (alternating), so every timing is a cold Tavily request. An earlier
      design timed both modes on the same sub-queries; Tavily served the
      second side from cache (0.2–0.5 s vs 3–12 s cold), which made the
      comparison meaningless. Use --start to pick questions not searched recently.

Results go to benchmarks/results/<timestamp>_<mode>.jsonl (one line per run)
plus <timestamp>_<mode>_summary.json — commit them as evidence.

Usage:
    python -m benchmarks.run --runs 5
    python -m benchmarks.run --mode search-ab --runs 10 --start 10
    OBSERVABILITY_URL=http://localhost:8000 python -m benchmarks.run --runs 10

Quota notes (free tiers):
    Groq free-tier models have per-minute token limits. The Groq SDK retries
    429s itself after a backoff, so a rate-limited call looks like a slow call,
    not an error. Each run therefore records rate_limit_retries and
    retry_wait_s (parsed from the SDK's retry log), and the summary reports
    latency both with and without that wait.
    Tavily "advanced" search costs 2 credits per sub-query.
"""

import argparse
import json
import logging
import math
import os
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv

import agents.llm as llm
from agents.planner_agent import planner_node
from agents.search_agent import DEFAULT_SEARCH_CONCURRENCY, search_node
from graph.state import AgentState
from graph.workflow import build_graph

# ── Constants ────────────────────────────────────────────────────────────────
BENCH_DIR = Path(__file__).resolve().parent
DEFAULT_QUERIES = BENCH_DIR / "queries.txt"
RESULTS_DIR = BENCH_DIR / "results"
NODES = ("planner", "search", "writer", "critic")
GROQ_RETRY_LOGGER = "groq._base_client"   # logs "Retrying request to %s in %f seconds"


# ── Helpers ──────────────────────────────────────────────────────────────────
class RetryCounter(logging.Handler):
    """Counts Groq SDK retries (429 rate limits, 5xx) and the backoff time they add."""

    def __init__(self) -> None:
        """Start with zero retries."""
        super().__init__(level=logging.INFO)
        self.retries = 0
        self.wait_s = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        """Parse the SDK's retry log line; ignore everything else."""
        args = record.args if isinstance(record.args, tuple) else ()
        if isinstance(record.msg, str) and record.msg.startswith("Retrying request") and len(args) >= 2:
            self.retries += 1
            self.wait_s += float(args[1])


def load_queries(path: Path, runs: int, start: int = 0) -> List[str]:
    """
    Read questions from a file, cycling if more runs than questions are requested.

    Args:
        path:  Text file, one question per line, '#' comments allowed.
        runs:  Number of questions to return.
        start: Index of the first question to use.

    Returns:
        List of `runs` questions.
    """
    lines = [ln.strip() for ln in path.read_text().splitlines()]
    questions = [ln for ln in lines if ln and not ln.startswith("#")]
    if not questions:
        raise ValueError(f"No questions found in {path}")
    return [questions[(start + i) % len(questions)] for i in range(runs)]


def initial_state(query: str) -> AgentState:
    """Zero-value AgentState for one run."""
    return AgentState(
        query=query,
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


def percentile(values: List[float], pct: float) -> Optional[float]:
    """
    Linear-interpolated percentile (same method as numpy's default).

    Args:
        values: Samples.
        pct:    Percentile in [0, 100].

    Returns:
        The percentile, or None for an empty sample.
    """
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def rounded(value: Optional[float], digits: int = 3) -> Optional[float]:
    """Round, passing None through."""
    return None if value is None else round(value, digits)


def git_revision() -> str:
    """Short commit SHA of the code being benchmarked, '+dirty' if uncommitted changes exist."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        return f"{sha}+dirty" if dirty else sha
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# ── Pipeline mode ────────────────────────────────────────────────────────────
def run_pipeline_once(query: str) -> dict[str, Any]:
    """
    Run the full graph once and measure it.

    Per-node time is the gap between consecutive LangGraph stream updates;
    a node that runs more than once (writer/critic on revisions) is summed.

    Args:
        query: Research question.

    Returns:
        One result row.
    """
    calls: List[llm.LLMCallRecord] = []
    llm.add_listener(calls.append)
    retry_logger = logging.getLogger(GROQ_RETRY_LOGGER)
    previous_level = retry_logger.level
    retries = RetryCounter()
    retry_logger.setLevel(logging.INFO)
    retry_logger.addHandler(retries)

    graph = build_graph()
    state: dict[str, Any] = dict(initial_state(query))
    node_s = {name: 0.0 for name in NODES}
    passes = {name: 0 for name in NODES}

    start = last = time.perf_counter()
    try:
        for chunk in graph.stream(initial_state(query), stream_mode="updates"):
            now = time.perf_counter()
            node = next(iter(chunk))
            node_s[node] = node_s.get(node, 0.0) + (now - last)
            passes[node] = passes.get(node, 0) + 1
            state.update(chunk[node])
            last = now
    except Exception as exc:  # Graph-level failure (agents normally contain their own)
        state["status"], state["error"] = "error", f"graph raised: {exc}"
    finally:
        llm.remove_listener(calls.append)
        retry_logger.removeHandler(retries)
        retry_logger.setLevel(previous_level)
    total_s = time.perf_counter() - start

    report = state.get("report", "")
    results = state.get("search_results", [])
    return {
        "query": query,
        "status": state.get("status"),
        "error": state.get("error", ""),
        "total_s": round(total_s, 3),
        "node_s": {k: round(v, 3) for k, v in node_s.items()},
        "writer_passes": passes["writer"],
        "critic_passes": passes["critic"],
        "revision_count": state.get("revision_count", 0),
        "quality_score": state.get("quality_score", 0.0),
        "sub_queries": len(state.get("search_queries", [])),
        "source_count": len({r.get("url") for r in results if r.get("url")}),
        "word_count": len(report.split()),
        "llm_calls": len(calls),
        "llm_errors": sum(1 for c in calls if c["status"] == "error"),
        "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
        "completion_tokens": sum(c["completion_tokens"] for c in calls),
        "cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
        "llm_latency_s": round(sum(c["latency_ms"] for c in calls) / 1000, 3),
        "rate_limit_retries": retries.retries,
        "retry_wait_s": round(retries.wait_s, 3),
    }


def summarize_pipeline(rows: List[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate pipeline rows. Latency/quality stats use successful runs only;
    the error rate is reported separately so failures aren't hidden.

    Args:
        rows: Output of run_pipeline_once for every run.

    Returns:
        Summary dict.
    """
    ok = [r for r in rows if r["status"] == "done"]
    totals = [r["total_s"] for r in ok]
    # Same runs with SDK backoff subtracted: what the pipeline costs when not throttled.
    unthrottled = [r["total_s"] - r["retry_wait_s"] for r in ok]
    summary: dict[str, Any] = {
        "runs": len(rows),
        "successful_runs": len(ok),
        "error_rate": rounded(1 - len(ok) / len(rows)) if rows else None,
        "latency_s": {
            "p50": rounded(percentile(totals, 50)),
            "p95": rounded(percentile(totals, 95)),
            "mean": rounded(statistics.fmean(totals)) if totals else None,
            "min": rounded(min(totals)) if totals else None,
            "max": rounded(max(totals)) if totals else None,
        },
        "latency_excluding_retry_wait_s": {
            "p50": rounded(percentile(unthrottled, 50)),
            "p95": rounded(percentile(unthrottled, 95)),
        },
        "rate_limits": {
            "runs_with_retries": sum(1 for r in ok if r["rate_limit_retries"]),
            "retries_total": sum(r["rate_limit_retries"] for r in ok),
            "retry_wait_s_mean": rounded(statistics.fmean(r["retry_wait_s"] for r in ok)) if ok else None,
        },
        "stage_p50_s": {
            name: rounded(percentile([r["node_s"][name] for r in ok], 50)) for name in NODES
        },
    }
    if ok:
        summary.update({
            "cost_usd_per_run": {
                "mean": rounded(statistics.fmean(r["cost_usd"] for r in ok), 6),
                "p50": rounded(percentile([r["cost_usd"] for r in ok], 50), 6),
                "total_all_runs": rounded(sum(r["cost_usd"] for r in rows), 6),
            },
            "tokens_per_run_mean": {
                "prompt": round(statistics.fmean(r["prompt_tokens"] for r in ok)),
                "completion": round(statistics.fmean(r["completion_tokens"] for r in ok)),
            },
            "llm_calls_per_run_mean": rounded(statistics.fmean(r["llm_calls"] for r in ok), 2),
            "quality_score_mean": rounded(statistics.fmean(r["quality_score"] for r in ok), 2),
            "accepted_first_draft_rate": rounded(sum(1 for r in ok if r["revision_count"] == 0) / len(ok)),
            "revisions_mean": rounded(statistics.fmean(r["revision_count"] for r in ok), 2),
            "sources_per_report_mean": rounded(statistics.fmean(r["source_count"] for r in ok), 1),
        })
    return summary


# ── Search A/B mode ──────────────────────────────────────────────────────────
def timed_search(sub_queries: List[str], concurrency: int) -> tuple[float, int]:
    """
    Run only the Search node with a given concurrency.

    Args:
        sub_queries: Planner output to search.
        concurrency: Value for SEARCH_CONCURRENCY.

    Returns:
        (seconds, result_count)
    """
    os.environ["SEARCH_CONCURRENCY"] = str(concurrency)
    state = initial_state("search-ab")
    state["search_queries"] = sub_queries
    start = time.perf_counter()
    out = search_node(state)
    return time.perf_counter() - start, len(out.get("search_results", []))


def run_search_ab_once(query: str, index: int, concurrency: int) -> dict[str, Any]:
    """
    Plan, then time ONE cold search in the mode assigned to this run.

    Modes alternate (even index → sequential, odd → concurrent) so both sides
    get a similar mix of questions, and no sub-query is searched twice.

    Args:
        query:       Research question.
        index:       Run index, picks the mode.
        concurrency: SEARCH_CONCURRENCY for the concurrent side.

    Returns:
        One result row.
    """
    planned = planner_node(initial_state(query))
    sub_queries = planned.get("search_queries", [])
    if planned.get("status") == "error" or not sub_queries:
        return {"query": query, "status": "error", "error": planned.get("error", "no sub-queries")}

    workers = 1 if index % 2 == 0 else concurrency
    seconds, result_count = timed_search(sub_queries, workers)
    return {
        "query": query,
        "status": "done",
        "error": "",
        "mode": "sequential" if workers == 1 else "concurrent",
        "concurrency": workers,
        "sub_queries": len(sub_queries),
        "search_s": round(seconds, 3),
        "results": result_count,
    }


def summarize_search_ab(rows: List[dict[str, Any]]) -> dict[str, Any]:
    """
    Compare cold search latency between the two modes.

    Args:
        rows: Output of run_search_ab_once.

    Returns:
        Summary with per-mode p50/p95, sample sizes and p50 reduction (%).
    """
    ok = [r for r in rows if r["status"] == "done"]
    seq = [r["search_s"] for r in ok if r["mode"] == "sequential"]
    conc = [r["search_s"] for r in ok if r["mode"] == "concurrent"]
    seq_p50, conc_p50 = percentile(seq, 50), percentile(conc, 50)
    reduction = speedup = None
    if seq_p50 and conc_p50:
        reduction = round(100 * (1 - conc_p50 / seq_p50), 1)
        speedup = round(seq_p50 / conc_p50, 2)
    return {
        "runs": len(rows),
        "successful_runs": len(ok),
        "sequential_s": {"n": len(seq), "p50": rounded(seq_p50), "p95": rounded(percentile(seq, 95))},
        "concurrent_s": {"n": len(conc), "p50": rounded(conc_p50), "p95": rounded(percentile(conc, 95))},
        "p50_reduction_pct": reduction,
        "p50_speedup": speedup,
        "sub_queries_mean": rounded(statistics.fmean(r["sub_queries"] for r in ok), 2) if ok else None,
    }


# ── Entry point ──────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """CLI arguments."""
    parser = argparse.ArgumentParser(description="Benchmark the research pipeline against live APIs.")
    parser.add_argument("--mode", choices=("pipeline", "search-ab"), default="pipeline")
    parser.add_argument("--runs", type=int, default=5, help="Number of questions to run (default 5)")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES, help="Question file")
    parser.add_argument("--start", type=int, default=0, help="Index of the first question to use")
    parser.add_argument(
        "--search-concurrency", type=int, default=DEFAULT_SEARCH_CONCURRENCY,
        help="SEARCH_CONCURRENCY for pipeline runs / the concurrent side of search-ab",
    )
    parser.add_argument("--delay", type=float, default=20.0, help="Seconds to wait between runs (rate limits)")
    return parser.parse_args()


def main() -> None:
    """Run the benchmark, write JSONL + summary, print the summary."""
    load_dotenv()
    args = parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    if args.search_concurrency < 1:
        raise SystemExit("--search-concurrency must be >= 1")
    if args.mode == "search-ab" and args.search_concurrency == 1:
        raise SystemExit("search-ab compares against concurrency 1; pass --search-concurrency > 1")

    queries = load_queries(args.queries, args.runs, args.start)
    os.environ["SEARCH_CONCURRENCY"] = str(args.search_concurrency)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rows_path = RESULTS_DIR / f"{stamp}_{args.mode}.jsonl"
    summary_path = RESULTS_DIR / f"{stamp}_{args.mode}_summary.json"

    rows: List[dict[str, Any]] = []
    with rows_path.open("w") as fh:
        for i, query in enumerate(queries):
            if i and args.delay > 0:
                time.sleep(args.delay)
            print(f"\n[BENCH] {i + 1}/{len(queries)} — {query}")
            if args.mode == "pipeline":
                row = run_pipeline_once(query)
                print(f"[BENCH]   {row['status']} in {row['total_s']}s | "
                      f"score {row['quality_score']} | revisions {row['revision_count']} | "
                      f"${row['cost_usd']} | llm_errors {row['llm_errors']} | "
                      f"retries {row['rate_limit_retries']} ({row['retry_wait_s']}s)")
            else:
                row = run_search_ab_once(query, i, args.search_concurrency)
                if row["status"] == "done":
                    print(f"[BENCH]   {row['mode']} (x{row['concurrency']}): "
                          f"{row['search_s']}s for {row['sub_queries']} sub-queries")
                else:
                    print(f"[BENCH]   error: {row['error']}")
            rows.append(row)
            fh.write(json.dumps(row) + "\n")
            fh.flush()

    summarize = summarize_pipeline if args.mode == "pipeline" else summarize_search_ab
    summary = {
        "mode": args.mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision(),
        "model": llm.MODEL,
        "search_concurrency": args.search_concurrency,
        "delay_s": args.delay,
        "queries_file": str(args.queries),
        "queries_start": args.start,
        "pricing_per_million_usd": llm.PRICING_PER_MILLION.get(llm.MODEL),
        "results": summarize(rows),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print("\n" + "=" * 60)
    print(json.dumps(summary["results"], indent=2))
    print("=" * 60)
    print(f"Rows:    {rows_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
