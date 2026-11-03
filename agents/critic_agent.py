"""
agents/critic_agent.py

Critic Agent — reviews the Writer's report, assigns a quality score (1–10),
and provides actionable feedback for revision if the score is below 7.

Why a Critic agent?
  Without review, the Writer produces whatever it feels like. The Critic
  enforces quality standards: factual grounding, structure, depth, source
  usage, and clarity. Reports scoring below 7 are sent back to the Writer
  with specific instructions — creating a self-correcting feedback loop.

Routing: critic_node makes the accept/revise decision and records it in
state["status"]; route_after_critic only reads that status.
  score >= 7 OR revision_count >= 2  →  status "done"     →  END
  score < 7  AND revision_count < 2  →  status "writing"  →  writer (revision_count + 1)
revision_count counts revisions actually requested, so at most 2 rewrites run.
"""

import re

from agents.llm import MODEL, chat

from graph.state import AgentState

# ── Constants ────────────────────────────────────────────────────────────────
MAX_TOKENS = 500
TEMPERATURE = 0.3    # Low — Critic must be consistent and deterministic
QUALITY_THRESHOLD = 7.0
MAX_REVISIONS = 2


def _parse_score(raw: str) -> float:
    """
    Extract the numeric score from the Critic's response.

    Tries to find a pattern like "Score: 7.5" or "7/10" or just a number.
    Falls back to 5.0 (below threshold) if no score found so the pipeline
    attempts a revision rather than silently accepting a bad report.

    Args:
        raw: Raw text response from the Critic LLM.

    Returns:
        Float score between 1.0 and 10.0.
    """
    # Pattern 1: "Score: 8" or "Score: 7.5"
    match = re.search(r"score[:\s]+(\d+(?:\.\d+)?)", raw, re.IGNORECASE)
    if match:
        return min(10.0, max(1.0, float(match.group(1))))

    # Pattern 2: "8/10" or "7.5/10"
    match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", raw, re.IGNORECASE)
    if match:
        return min(10.0, max(1.0, float(match.group(1))))

    # Pattern 3: standalone number at start of line
    match = re.search(r"^\s*(\d+(?:\.\d+)?)\s*$", raw, re.MULTILINE)
    if match:
        return min(10.0, max(1.0, float(match.group(1))))

    # Fallback — conservative: assume below threshold, trigger revision
    print("[CRITIC] WARNING — could not parse score from response. Defaulting to 5.0.")
    return 5.0


def critic_node(state: AgentState) -> dict:
    """
    LangGraph node: Critic Agent.

    Reads:
        state["report"]         — markdown report from Writer agent.
        state["query"]          — original user question.
        state["revision_count"] — current revision count.

    Writes:
        quality_score  — float 1–10.
        critique       — written feedback for Writer (empty if score >= 7).
        revision_count — incremented by 1 only when a revision is requested.
        status         — "done" if passing, "writing" if revision needed.
        messages       — appended with critic turn.
        error          — set if LLM call fails.

    Args:
        state: Current AgentState.

    Returns:
        Dict of updated state fields only.
    """
    query = state["query"]
    report = state.get("report", "")
    revision_count = state.get("revision_count", 0)

    print(f"[CRITIC] Starting — evaluating report | Revision {revision_count}/{MAX_REVISIONS}")

    if not report:
        error_msg = "Critic received empty report from Writer."
        print(f"[CRITIC] ERROR — {error_msg}")
        return {
            "quality_score": 0.0,
            "critique": error_msg,
            "revision_count": revision_count,
            "status": "error",
            "error": error_msg,
            "messages": state.get("messages", []) + [
                {"role": "critic", "content": f"ERROR: {error_msg}"}
            ],
        }

    try:
        system_prompt = (
            "You are a rigorous research quality reviewer. Evaluate the report below "
            "against the original research question and assign a score.\n\n"
            "Scoring criteria (each worth up to 2 points):\n"
            "1. Factual accuracy — claims backed by cited sources\n"
            "2. Completeness — all major angles of the question addressed\n"
            "3. Structure — clear sections, logical flow, readable prose\n"
            "4. Source usage — multiple sources referenced, URLs present\n"
            "5. Insight depth — goes beyond surface facts, provides analysis\n\n"
            "Response format (follow EXACTLY):\n"
            "Score: <number 1-10>\n\n"
            "Strengths:\n"
            "<2-3 bullet points on what the report does well>\n\n"
            "Issues:\n"
            "<2-3 specific, actionable problems to fix — be precise>\n\n"
            "Verdict: <one sentence on whether this report is publication-ready>"
        )

        user_prompt = (
            f"Original Research Question: {query}\n\n"
            f"Report to Evaluate:\n\n{report}"
        )

        raw_output = chat(
            agent="critic",
            model=MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        score = _parse_score(raw_output)

        print(f"[CRITIC] Score: {score}/10 — Revision {revision_count}/{MAX_REVISIONS}")

        # Only pass critique to Writer if revision is needed
        if score >= QUALITY_THRESHOLD or revision_count >= MAX_REVISIONS:
            if revision_count >= MAX_REVISIONS and score < QUALITY_THRESHOLD:
                print(f"[CRITIC] Max revisions reached. Accepting report with score {score}/10.")
            else:
                print(f"[CRITIC] Report passed quality threshold ({score}/10 >= {QUALITY_THRESHOLD}). Done.")

            return {
                "quality_score": score,
                "critique": raw_output,
                "revision_count": revision_count,
                "status": "done",
                "error": "",
                "messages": state.get("messages", []) + [
                    {"role": "critic", "content": f"Score: {score}/10. Report accepted."}
                ],
            }
        else:
            print(f"[CRITIC] Score {score}/10 below threshold. Sending back for revision.")
            return {
                "quality_score": score,
                "critique": raw_output,
                "revision_count": revision_count + 1,
                "status": "writing",
                "error": "",
                "messages": state.get("messages", []) + [
                    {"role": "critic", "content": f"Score: {score}/10. Revision requested."}
                ],
            }

    except Exception as exc:
        error_msg = f"Critic agent failed: {exc}"
        print(f"[CRITIC] ERROR — {error_msg}")
        return {
            "quality_score": 0.0,
            "critique": "",
            "revision_count": revision_count,
            "status": "error",
            "error": error_msg,
            "messages": state.get("messages", []) + [
                {"role": "critic", "content": f"ERROR: {error_msg}"}
            ],
        }


def route_after_critic(state: AgentState) -> str:
    """
    LangGraph conditional routing function called after critic_node.

    Decides whether the pipeline continues to END or loops back to Writer.

    Args:
        state: Current AgentState (after critic_node has run).

    Returns:
        "end"    — report accepted, max revisions reached, or critic error.
        "writer" — critic requested a revision (status == "writing").
    """
    # critic_node already applied the threshold and revision cap. Re-deriving
    # the decision here from the incremented revision_count caused an
    # off-by-one: only 1 revision ever ran, and critic errors looped back to
    # the writer instead of ending the run.
    if state.get("status") == "writing":
        return "writer"
    return "end"
