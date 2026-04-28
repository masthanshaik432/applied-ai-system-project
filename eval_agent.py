"""
eval_agent.py — Reliability evaluation for PawPal+ AI layer

Sections
--------
1. RAG retrieval quality  — no API key required
2. Output guardrail checks — no API key required (uses mock explanations)
3. Full pipeline smoke test — requires ANTHROPIC_API_KEY env variable (skipped if absent)

Run with:
    python eval_agent.py
"""

from __future__ import annotations

import os
import sys
import textwrap
from datetime import datetime

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

results: list[tuple[str, bool, str]] = []  # (test_name, passed, note)


def record(name: str, passed: bool, note: str = "") -> None:
    results.append((name, passed, note))
    status = PASS if passed else FAIL
    print(f"  [{status}] {name}" + (f"  → {note}" if note else ""))


# ---------------------------------------------------------------------------
# Section 1 — RAG retrieval quality (no API key needed)
# ---------------------------------------------------------------------------

print("\n=== Section 1: RAG Retrieval Quality ===\n")

from ai_agent import PawPalRAG

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge")
rag = PawPalRAG(knowledge_dir=KNOWLEDGE_DIR)

# 1a — correct document returned for known queries
cases = [
    ("arthritis dog exercise",   "arthritis"),
    ("cat feeding schedule",     "cat"),
    ("heart disease medication",  "heart"),
    ("post surgery recovery",    "surgery"),
    ("obesity weight management", "obesity"),
    ("medication twice daily",   "medication"),
]
for query, expected_term in cases:
    result_text = rag.retrieve_as_text(query, top_k=1)
    passed = expected_term.lower() in result_text.lower()
    record(f"RAG: '{query}' → contains '{expected_term}'", passed, result_text[:60].strip())

# 1b — top_k respected
results_list = rag.retrieve("dog cat walk medication", top_k=2)
record("RAG: top_k=2 returns at most 2 docs", len(results_list) <= 2, f"got {len(results_list)}")

# 1c — irrelevant query returns nothing
empty = rag.retrieve("xyzzy blockchain nanobot", top_k=3)
record("RAG: nonsense query returns empty list", empty == [], f"got {len(empty)} result(s)")

# 1d — all 7 docs loaded
expected_docs = {"arthritis","heart_disease","obesity","post_surgery","dog_care","cat_care","medication_guidelines"}
record("RAG: all 7 knowledge docs loaded", set(rag.documents.keys()) == expected_docs,
       f"found: {sorted(rag.documents.keys())}")


# ---------------------------------------------------------------------------
# Section 2 — Output guardrail checks (no API key needed)
# ---------------------------------------------------------------------------

print("\n=== Section 2: Output Guardrail Checks ===\n")

from pawpal_system import (
    Constraint, OwnerPreferences, Pet, Planner, Task, TaskHistory, TaskType,
)
from ai_agent import PawPalAgent

# Build a minimal planner so the agent has a context (no real API calls)
rex = Pet(name="Rex", species="dog", age=4, health_conditions=["arthritis"])
task = Task(name="Walk Rex", task_type=TaskType.WALK, duration=30,
            priority=3, frequency="daily", pet=rex)
prefs = OwnerPreferences(
    max_daily_time=120,
    preferred_times={"morning": (7, 12)},
    task_priorities_override={},
)
planner = Planner(pets=[rex], tasks=[task], preferences=prefs,
                  history=TaskHistory(), constraint=Constraint())

# Use a dummy key — guardrail tests never reach the API
agent = PawPalAgent(planner=planner, rag=rag, api_key="dummy-not-used")
now = datetime.now()

def run_guardrails(label: str, explanation: str) -> list[str]:
    _, issues = agent._apply_guardrails(explanation, now)
    return issues


# 2a — empty string is caught
issues = run_guardrails("empty", "")
record("Guardrail: empty explanation is flagged",
       any("empty" in i for i in issues), str(issues))

# 2b — too-short explanation is caught
short = "Rex needs a walk."
issues = run_guardrails("short", short)
record("Guardrail: too-short explanation is flagged",
       any("short" in i for i in issues), str(issues))

# 2c — missing pet name is caught
no_name = " ".join(["The medication should be given consistently with food."] * 6)
issues = run_guardrails("no_pet_name", no_name)
record("Guardrail: explanation missing pet name is flagged",
       any("pet by name" in i for i in issues), str(issues))

# 2d — refusal pattern is caught
refusal = (
    "I don't have enough information about your pet to give specific advice. "
    "Could you provide more details about what species Rex is and what conditions "
    "he has? I want to make sure I give you the right guidance for his care needs."
)
issues = run_guardrails("refusal", refusal)
record("Guardrail: refusal/clarifying-question pattern is flagged",
       any("refusal" in i for i in issues), str(issues))

# 2e — good explanation passes all guardrails
good = textwrap.dedent("""\
    Rex's medication has been scheduled first thing in the morning and this is intentional.
    For dogs with arthritis, NSAIDs need to be given consistently with food to maintain
    stable therapeutic levels. The walk has been kept short and placed mid-morning when
    Rex's joints are typically less stiff. High-impact or prolonged walks should be avoided.
    If Rex shows any limping after today's walk, shorten it tomorrow. Overall the plan
    looks solid for a dog managing a chronic joint condition.
""")
issues = run_guardrails("good_explanation", good)
record("Guardrail: good explanation passes all checks", issues == [], str(issues))


# ---------------------------------------------------------------------------
# Section 3 — Full pipeline smoke test (requires API key)
# ---------------------------------------------------------------------------

print("\n=== Section 3: Full Pipeline Smoke Test ===\n")

api_key = os.environ.get("ANTHROPIC_API_KEY", "")

if not api_key:
    print(f"  [{SKIP}] No ANTHROPIC_API_KEY set — skipping live API tests.\n"
          "          Set the variable and re-run to include this section.")
else:
    live_agent = PawPalAgent(planner=planner, rag=rag, api_key=api_key)

    try:
        plan, explanation = live_agent.generate_and_explain(now)

        record("Pipeline: returns a non-empty DailyPlan",
               plan is not None and hasattr(plan, "scheduled_tasks"))

        record("Pipeline: explanation is a non-empty string",
               isinstance(explanation, str) and len(explanation.strip()) > 0,
               f"{len(explanation.split())} words")

        record("Pipeline: no guardrail failures on live output",
               live_agent.guardrail_issues == [],
               str(live_agent.guardrail_issues))

        record("Pipeline: confidence level is set",
               live_agent.confidence.get("level") in ("High", "Medium", "Low"),
               str(live_agent.confidence))

        record("Pipeline: agent trace has at least one entry",
               len(live_agent.trace) >= 1,
               f"{len(live_agent.trace)} trace entries")

    except Exception as exc:
        record("Pipeline: smoke test completed without exception", False, str(exc))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 52)
print("  EVALUATION SUMMARY")
print("=" * 52)

passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
print(f"\n  {passed}/{total} checks passed\n")

if passed < total:
    print("  Failed checks:")
    for name, ok, note in results:
        if not ok:
            print(f"    - {name}")
            if note:
                print(f"      {note}")

print()
sys.exit(0 if passed == total else 1)
