"""
agents/llm.py

Shared Groq chat wrapper used by every LLM-backed agent (Planner, Writer, Critic).

Why one wrapper?
  Each agent used to build its own client and call Groq directly, so there was
  no single place to measure what a call cost or how long it took. Routing every
  call through chat() gives us, per call:
    - wall-clock latency
    - prompt / completion token counts (from Groq's usage block)
    - cost at Groq list price
  and ships that record to two optional sinks:
    1. In-process listeners (add_listener) — used by benchmarks/run.py to
       aggregate per-run latency, tokens and cost.
    2. The LLM Observability Platform (POST /logs) when OBSERVABILITY_URL is set.

Observability shipping is fire-and-forget on a background thread with a short
timeout: if the platform is down, the research pipeline is unaffected.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Literal, Optional, TypedDict

import httpx
from groq import Groq

# ── Constants ────────────────────────────────────────────────────────────────
PROVIDER = "groq"

# Single source of truth for the model every agent uses. Groq retired
# llama-3.3-70b-versatile (404 model_not_found, 2026-11); reading GROQ_MODEL
# makes the next retirement a config change instead of a code change.
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# gpt-oss models reason before answering. "low" keeps latency and tokens down —
# planning, writing and critique don't need long chains of thought — and the
# reasoning text (returned in a separate field) is dropped since nothing reads it.
# Reasoning tokens still count toward max_tokens and completion_tokens.
REASONING_EFFORT = "low"
REASONING_MODEL_PREFIX = "openai/gpt-oss"

# USD per 1M tokens (input, output). gpt-oss-120b uses Groq's launch price
# ($0.15 / $0.75, groq.com/blog/day-zero-support-for-openai-open-models); some
# trackers now list $0.60 output, so this errs high. Free-tier keys are not
# billed — cost_usd is the list-price equivalent so runs can be compared.
PRICING_PER_MILLION: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.75),
}

OBSERVABILITY_TIMEOUT_S = 2.0
DEFAULT_APPLICATION_ID = "research-agent"


class LLMCallRecord(TypedDict):
    """One measured LLM call, passed to listeners and shipped to observability."""

    agent: str                    # "planner" | "writer" | "critic"
    model: str
    prompt: str                   # User message only — see _ship_to_observability
    response: Optional[str]       # None when the call failed
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    status: Literal["success", "error"]
    error: str


Listener = Callable[[LLMCallRecord], None]

_listeners: List[Listener] = []
_unpriced_warned: set[str] = set()
# Two workers is plenty: posts are tiny and only overlap during concurrent API runs.
_shipper = ThreadPoolExecutor(max_workers=2, thread_name_prefix="obs-shipper")


def add_listener(listener: Listener) -> None:
    """
    Register a callback invoked synchronously after every LLM call.

    Args:
        listener: Function receiving the LLMCallRecord for each call.
    """
    _listeners.append(listener)


def remove_listener(listener: Listener) -> None:
    """
    Unregister a callback previously passed to add_listener.

    Args:
        listener: The exact function object that was registered.
    """
    if listener in _listeners:
        _listeners.remove(listener)


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Compute list-price cost for a call.

    Args:
        model:             Model name; unknown models cost 0.0.
        prompt_tokens:     Input token count.
        completion_tokens: Output token count.

    Returns:
        Cost in USD, rounded to 6 decimal places.
    """
    input_price, output_price = PRICING_PER_MILLION.get(model, (0.0, 0.0))
    cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
    return round(cost, 6)


def _build_client() -> Groq:
    """Initialise Groq client from environment."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set in environment.")
    return Groq(api_key=api_key)


def _post_log(url: str, payload: dict) -> None:
    """
    POST one log record to the observability platform. Runs on the shipper thread.

    Never raises — a failed post prints one warning and is dropped.

    Args:
        url:     Full /logs endpoint URL.
        payload: Body matching the platform's LLMLogCreate schema.
    """
    try:
        resp = httpx.post(url, json=payload, timeout=OBSERVABILITY_TIMEOUT_S)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[LLM] WARNING — observability log dropped: {exc}")


def _ship_to_observability(record: LLMCallRecord) -> None:
    """
    Queue a record for the LLM Observability Platform if OBSERVABILITY_URL is set.

    The prompt sent is the user message only. The platform embeds prompts with a
    512-token model for drift detection; the system prompt is identical on every
    call and would dominate the embedding, hiding real shifts in research topics.

    Args:
        record: The measured call.
    """
    base_url = os.getenv("OBSERVABILITY_URL", "").rstrip("/")
    if not base_url:
        return

    payload = {
        "application_id": os.getenv("OBSERVABILITY_APP_ID", DEFAULT_APPLICATION_ID),
        "model": record["model"],
        "provider": PROVIDER,
        "prompt": record["prompt"],
        "response": record["response"],
        "prompt_tokens": record["prompt_tokens"],
        "completion_tokens": record["completion_tokens"],
        "total_tokens": record["prompt_tokens"] + record["completion_tokens"],
        "cost_usd": record["cost_usd"],
        "latency_ms": record["latency_ms"],
        "status": record["status"],
        "tags": {"agent": record["agent"]},
    }
    _shipper.submit(_post_log, f"{base_url}/logs", payload)


def _emit(record: LLMCallRecord) -> None:
    """
    Fan a record out to listeners and observability. Listener errors are contained.

    Args:
        record: The measured call.
    """
    for listener in list(_listeners):
        try:
            listener(record)
        except Exception as exc:
            print(f"[LLM] WARNING — listener failed: {exc}")
    _ship_to_observability(record)


def chat(
    agent: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """
    Run one Groq chat completion and record latency, tokens and cost.

    Args:
        agent:         Calling agent name, used as a tag.
        model:         Groq model name.
        system_prompt: System message.
        user_prompt:   User message.
        temperature:   Sampling temperature.
        max_tokens:    Completion token cap.

    Returns:
        The completion text ("" if the model returned no content).

    Raises:
        Any Groq/network exception, after the failed call has been recorded.
        Agents catch this and set state["error"] as before.
    """
    reasoning_kwargs: dict[str, object] = {}
    if model.startswith(REASONING_MODEL_PREFIX):
        reasoning_kwargs = {"reasoning_effort": REASONING_EFFORT, "include_reasoning": False}
    if model not in PRICING_PER_MILLION and model not in _unpriced_warned:
        _unpriced_warned.add(model)
        print(f"[LLM] WARNING — no list price for '{model}'; cost_usd will be 0.0")

    start = time.perf_counter()
    try:
        client = _build_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            **reasoning_kwargs,
        )
    except Exception as exc:
        _emit(LLMCallRecord(
            agent=agent,
            model=model,
            prompt=user_prompt,
            response=None,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            latency_ms=int((time.perf_counter() - start) * 1000),
            status="error",
            error=str(exc),
        ))
        raise

    latency_ms = int((time.perf_counter() - start) * 1000)
    choice = response.choices[0]
    text = choice.message.content or ""
    if not text and getattr(choice, "finish_reason", None) == "length":
        # Reasoning models spend max_tokens on hidden reasoning first; an empty
        # answer with finish_reason "length" means the cap is too low for this call.
        print(f"[LLM] WARNING — {agent} hit max_tokens={max_tokens} before writing an answer")
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0

    _emit(LLMCallRecord(
        agent=agent,
        model=model,
        prompt=user_prompt,
        response=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=estimate_cost_usd(model, prompt_tokens, completion_tokens),
        latency_ms=latency_ms,
        status="success",
        error="",
    ))
    return text
