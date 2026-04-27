from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic

from pawpal_system import DailyPlan, Planner


# ---------------------------------------------------------------------------
# RAG — keyword retriever over the knowledge base
# ---------------------------------------------------------------------------

class PawPalRAG:
    """Loads pet-care markdown documents and retrieves the most relevant ones
    for a given query using term-overlap scoring."""

    def __init__(self, knowledge_dir: str = "knowledge"):
        self.documents: dict[str, str] = {}
        self._load(Path(knowledge_dir))

    def _load(self, base: Path) -> None:
        if not base.exists():
            return
        for path in sorted(base.glob("*.md")):
            self.documents[path.stem] = path.read_text(encoding="utf-8")

    def retrieve(self, query: str, top_k: int = 3) -> list[tuple[str, str]]:
        """Return up to top_k (doc_name, content) pairs ranked by term overlap."""
        query_terms = set(re.findall(r"\w+", query.lower()))
        scored: list[tuple[int, str, str]] = []

        for name, content in self.documents.items():
            doc_terms = set(re.findall(r"\w+", content.lower()))
            name_terms = set(re.findall(r"\w+", name.lower()))
            # name matches count double — a query for "arthritis" should surface arthritis.md first
            score = len(query_terms & doc_terms) + 2 * len(query_terms & name_terms)
            scored.append((score, name, content))

        scored.sort(reverse=True)
        return [
            (name, content)
            for score, name, content in scored[:top_k]
            if score > 0
        ]

    def retrieve_as_text(self, query: str, top_k: int = 3) -> str:
        """Return retrieved docs as a single formatted string for injection into prompts."""
        results = self.retrieve(query, top_k)
        if not results:
            return "No relevant pet-care information found for this query."
        parts = [
            f"### {name.replace('_', ' ').title()}\n{content.strip()}"
            for name, content in results
        ]
        return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Agent — Claude-powered scheduling assistant
# ---------------------------------------------------------------------------

class PawPalAgent:
    """Wraps the existing Planner with a Claude-powered agentic loop.

    The agent:
      1. Generates a plan using the existing rule-based Planner.
      2. Passes the plan + any violations to Claude, which has access to
         the retrieve_pet_care_info tool backed by PawPalRAG.
      3. Claude calls the tool as many times as needed, then produces a
         grounded natural-language explanation for the owner.
      4. Returns the (plan, explanation) pair and a trace log for the UI.
    """

    MODEL = "claude-haiku-4-5-20251001"
    MAX_TOKENS = 1500
    MAX_TOOL_TURNS = 6  # safety cap on the agentic loop

    def __init__(self, planner: Planner, rag: PawPalRAG, api_key: str):
        self.planner = planner
        self.rag = rag
        self.client = anthropic.Anthropic(api_key=api_key)
        self.trace: list[str] = []  # human-readable log of agent steps for UI display

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate_and_explain(self, date: datetime) -> tuple[DailyPlan, str]:
        """Run the full pipeline and return (DailyPlan, grounded_explanation)."""
        self.trace = []

        # Step 1 — existing rule-based scheduler
        plan = self.planner.generate_daily_plan(date)
        conflicts = plan.detect_conflicts()
        summary = plan.get_summary()

        self.trace.append(
            f"Planner generated {summary['scheduled_count']} scheduled task(s), "
            f"{summary['unscheduled_count']} unscheduled, "
            f"{len(conflicts)} conflict(s) detected."
        )

        # Step 2 — build prompt for Claude
        plan_text = plan.explain_plan()
        conflict_text = "\n".join(conflicts) if conflicts else "None."
        unscheduled_text = (
            "\n".join(f"- {t['task']} ({t['pet']})" for t in summary["unscheduled_tasks"])
            if summary["unscheduled_tasks"]
            else "None."
        )

        # Build pet context so Claude doesn't have to ask
        pet_lines = []
        for pet in self.planner.pets:
            conditions = ", ".join(pet.health_conditions) if pet.health_conditions else "none"
            pet_lines.append(
                f"- {pet.name}: {pet.species}, age {pet.age}, health conditions: {conditions}"
            )
        pet_context = "\n".join(pet_lines) if pet_lines else "No pets registered."

        user_message = (
            f"**Pets in this household:**\n{pet_context}\n\n"
            f"**Today's automatically generated schedule:**\n{plan_text}\n\n"
            f"**Detected conflicts:**\n{conflict_text}\n\n"
            f"**Tasks that could not be scheduled:**\n{unscheduled_text}\n\n"
            "Please review this schedule. Use the retrieve_pet_care_info tool to look up "
            "relevant guidelines for the pets' health conditions, task types, or species needs. "
            "Then write a clear, friendly explanation for the owner that covers:\n"
            "1. Why the high-priority tasks were placed where they were.\n"
            "2. Any health-related concerns flagged by the schedule (conflicts, restrictions).\n"
            "3. What was skipped and why, and what the owner should do about it.\n"
            "Keep it concise and practical — the owner is busy."
        )

        # Step 3 — agentic loop
        messages: list[dict] = [{"role": "user", "content": user_message}]
        explanation = self._run_loop(messages, plan)

        return plan, explanation

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        return (
            "You are PawPal+, a helpful and knowledgeable pet care scheduling assistant. "
            "Your role is to review automatically generated daily schedules for pet owners, "
            "look up evidence-based care guidelines when relevant, and explain the schedule "
            "clearly. Always use the retrieve_pet_care_info tool before making any claim about "
            "a health condition, medication, or species-specific need. Be warm, concise, and "
            "practical — the owner is busy and just needs to know what to do and why."
        )

    def _tool_definitions(self) -> list[dict]:
        return [
            {
                "name": "retrieve_pet_care_info",
                "description": (
                    "Search the pet care knowledge base for guidelines relevant to a specific "
                    "health condition, species, task type, or medication. Returns the most "
                    "relevant documents from the knowledge base."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "A short search phrase, e.g. 'arthritis dog exercise', "
                                "'medication twice daily timing', 'cat feeding schedule'."
                            ),
                        }
                    },
                    "required": ["query"],
                },
            }
        ]

    def _run_loop(self, messages: list[dict], plan: DailyPlan) -> str:
        """Drive the Claude tool-use loop until the model produces a final text response."""
        system_block = [
            {
                "type": "text",
                "text": self._system_prompt(),
                "cache_control": {"type": "ephemeral"},  # cache across turns in this session
            }
        ]

        for turn in range(self.MAX_TOOL_TURNS):
            response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=self.MAX_TOKENS,
                system=system_block,
                tools=self._tool_definitions(),
                messages=messages,
            )

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if not tool_uses:
                # No more tool calls — Claude is done
                self.trace.append(f"Agent produced final explanation after {turn + 1} turn(s).")
                return "\n".join(b.text for b in text_blocks).strip()

            # Process each tool call
            tool_results = []
            for tc in tool_uses:
                query = tc.input.get("query", "")
                self.trace.append(f"RAG lookup → \"{query}\"")
                retrieved = self.rag.retrieve_as_text(query)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": retrieved,
                    }
                )

            # Append assistant turn and tool results before next iteration
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        # Fallback if loop cap is hit — return the rule-based explanation
        self.trace.append("Agent loop reached max turns — falling back to rule-based explanation.")
        return plan.explain_plan()
