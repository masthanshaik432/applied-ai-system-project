import os

import streamlit as st

from ai_agent import PawPalAgent, PawPalRAG
from pawpal_system import (
    Constraint,
    OwnerPreferences,
    Pet,
    Planner,
    Task,
    TaskHistory,
    TaskType,
)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# ---------------------------------------------------------------------------
# Sidebar — Anthropic API key
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("AI Settings")
    api_key_input = st.text_input(
        "Anthropic API key",
        type="password",
        placeholder="sk-ant-...",
        help="Required for AI-powered schedule explanations. Get a key at console.anthropic.com.",
    )
    api_key = api_key_input or os.environ.get("ANTHROPIC_API_KEY", "")

    if api_key:
        st.success("API key loaded — AI explanations enabled.")
    else:
        st.info("No API key — schedule will use rule-based explanations.")

# ---------------------------------------------------------------------------
# Session state initialisation
#
# st.session_state works like a dictionary that survives reruns.
# The pattern below is the standard guard:
#
#   if "key" not in st.session_state:
#       st.session_state["key"] = <create object once>
#
# Without this guard the object would be recreated (and reset) on every
# button click, because Streamlit reruns the whole script top-to-bottom.
# ---------------------------------------------------------------------------

if "pets" not in st.session_state:
    st.session_state["pets"] = []               # list[Pet]  — grows as user adds pets

if "tasks" not in st.session_state:
    st.session_state["tasks"] = []              # list[Task] — grows as user adds tasks

if "history" not in st.session_state:
    st.session_state["history"] = TaskHistory() # one shared history log for the session

if "constraint" not in st.session_state:
    st.session_state["constraint"] = Constraint()

if "preferences" not in st.session_state:
    # Sensible defaults — owner can adjust these via the UI later
    st.session_state["preferences"] = OwnerPreferences(
        max_daily_time=180,
        preferred_times={
            "morning":   (7,  12),
            "afternoon": (14, 17),
            "evening":   (18, 20),
        },
        task_priorities_override={},
        break_duration=10,
    )

if "planner" not in st.session_state:
    # Planner is rebuilt whenever pets or tasks change (see "Add pet" / "Add task" buttons)
    st.session_state["planner"] = Planner(
        pets=st.session_state["pets"],
        tasks=st.session_state["tasks"],
        preferences=st.session_state["preferences"],
        history=st.session_state["history"],
        constraint=st.session_state["constraint"],
    )

st.title("🐾 PawPal+")
st.caption("Smart pet care scheduling — powered by your backend classes.")

# ---------------------------------------------------------------------------
# Section 1 — Add a Pet  →  calls Pet() and Pet.get_daily_needs()
# ---------------------------------------------------------------------------
st.subheader("Add a Pet")

with st.form("add_pet_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        pet_name = st.text_input("Name", value="")
    with col2:
        species = st.selectbox("Species", ["dog", "cat", "rabbit", "fish", "other"])
    with col3:
        age = st.number_input("Age (years)", min_value=0, max_value=30)

    health_input = st.text_input(
        "Health conditions (comma-separated, leave blank if none)",
        value="",
        placeholder="e.g. arthritis, diabetes",
    )
    auto_tasks = st.checkbox("Auto-generate baseline tasks from pet profile", value=False)
    submitted_pet = st.form_submit_button("Add Pet")

if submitted_pet:
    conditions = [c.strip() for c in health_input.split(",") if c.strip()]
    new_pet = Pet(name=pet_name, species=species, age=age, health_conditions=conditions)
    st.session_state["pets"].append(new_pet)

    if auto_tasks:
        # get_daily_needs() inspects species + health_conditions and returns Task objects
        baseline_tasks = new_pet.get_daily_needs()
        st.session_state["tasks"].extend(baseline_tasks)
        st.success(
            f"Added **{new_pet.name}** ({species}) with "
            f"{len(baseline_tasks)} auto-generated task(s)."
        )
    else:
        st.success(f"Added **{new_pet.name}** ({species}).")

if st.session_state["pets"]:
    pets = st.session_state["pets"]

    # Metric card — quick count at a glance
    special_care_count = sum(1 for p in pets if p.special_care_needed())
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Total pets", len(pets))
    col_m2.metric("Require special care", special_care_count)

    st.dataframe(
        [
            {
                "Name": p.name,
                "Species": p.species,
                "Age": p.age,
                "Health conditions": ", ".join(p.health_conditions) or "—",
                "Special care": "⚠️ yes" if p.special_care_needed() else "✅ no",
            }
            for p in pets
        ],
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# ---------------------------------------------------------------------------
# Section 2 — Add a Task  →  calls Task() with a real Pet reference
# ---------------------------------------------------------------------------
st.subheader("Add a Task")

if not st.session_state["pets"]:
    st.info("Add a pet first — tasks must be linked to a pet.")
else:
    with st.form("add_task_form"):
        col1, col2 = st.columns(2)
        with col1:
            task_name = st.text_input("Task name", value="")
            task_type = st.selectbox("Type", [t.value for t in TaskType])
            frequency = st.selectbox("Frequency", ["daily", "twice daily", "weekly", "biweekly", "monthly"])
        with col2:
            duration = st.number_input("Duration (minutes)", min_value=1, max_value=240)
            priority = st.slider("Priority", min_value=1, max_value=5, value=3)
            is_flexible = st.checkbox("Flexible (can be skipped if no slot available)", value=True)

        pet_names = [p.name for p in st.session_state["pets"]]
        selected_pet_name = st.selectbox("Assign to pet", pet_names)
        submitted_task = st.form_submit_button("Add Task")

    if submitted_task:
        linked_pet = next(p for p in st.session_state["pets"] if p.name == selected_pet_name)
        new_task = Task(
            name=task_name,
            task_type=TaskType(task_type),
            duration=duration,
            priority=priority,
            frequency=frequency,
            pet=linked_pet,
            is_flexible=is_flexible,
        )
        st.session_state["tasks"].append(new_task)
        st.success(f"Added task **{task_name}** for {selected_pet_name}.")

    if st.session_state["tasks"]:
        planner: Planner = st.session_state["planner"]
        all_tasks = st.session_state["tasks"]

        # Metric cards
        pending = [t for t in all_tasks if not t.completed]
        done    = [t for t in all_tasks if t.completed]
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total tasks", len(all_tasks))
        col_m2.metric("Pending", len(pending))
        col_m3.metric("Completed", len(done))

        # Filter controls — backed by planner.filter_tasks()
        st.caption("Filter tasks")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filter_pet = st.selectbox(
                "By pet",
                ["All pets"] + [p.name for p in st.session_state["pets"]],
                key="filter_pet",
            )
        with col_f2:
            filter_status = st.selectbox(
                "By status",
                ["All", "Pending", "Completed"],
                key="filter_status",
            )

        pet_arg    = None if filter_pet == "All pets" else filter_pet
        status_arg = None if filter_status == "All" else (filter_status == "Completed")
        filtered   = planner.filter_tasks(completed=status_arg, pet_name=pet_arg)

        # Sort filtered results by priority score — highest first
        sorted_tasks = planner.prioritize_tasks(filtered)

        if sorted_tasks:
            st.caption(
                f"Showing {len(sorted_tasks)} task(s) · sorted by priority score (highest first)"
            )
            st.dataframe(
                [
                    {
                        "Task": t.name,
                        "Pet": t.pet.name,
                        "Type": t.task_type.value,
                        "Duration (min)": t.duration,
                        "Priority": t.priority,
                        "Priority score": round(t.get_priority_score(), 2),
                        "Frequency": t.frequency,
                        "Flexible": "yes" if t.is_flexible else "no",
                        "Status": "✅ done" if t.completed else "🔲 pending",
                    }
                    for t in sorted_tasks
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning("No tasks match the selected filters.")
    else:
        st.info("No tasks yet.")

st.divider()

# ---------------------------------------------------------------------------
# Section 3 — Generate Schedule
# ---------------------------------------------------------------------------
st.subheader("Generate Today's Schedule")

if not st.session_state["tasks"]:
    st.info("Add at least one task before generating a schedule.")
else:
    if st.button("Generate schedule"):
        from datetime import datetime

        planner: Planner = st.session_state["planner"]

        if api_key:
            # ── AI path: agent generates plan + grounded explanation ──────────
            rag = PawPalRAG(knowledge_dir="knowledge")
            agent = PawPalAgent(planner=planner, rag=rag, api_key=api_key)

            with st.spinner("Agent is reviewing your schedule and looking up care guidelines…"):
                plan, explanation = agent.generate_and_explain(datetime.now())

            summary = plan.get_summary()

            # Summary metrics
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Scheduled", summary["scheduled_count"])
            col_m2.metric("Could not schedule", summary["unscheduled_count"])
            col_m3.metric("Total time (min)", summary["total_time_minutes"])

            # Conflict warnings
            conflicts = plan.detect_conflicts()
            if conflicts:
                st.error(f"⚠️ {len(conflicts)} scheduling conflict(s) detected.")
                for c in conflicts:
                    st.error(c)
            else:
                st.success("No scheduling conflicts detected.")

            # Chronological schedule table
            if summary["scheduled_tasks"]:
                st.write("**Chronological schedule:**")
                st.dataframe(
                    summary["scheduled_tasks"],
                    use_container_width=True,
                    hide_index=True,
                )

            # Unscheduled tasks
            if summary["unscheduled_tasks"]:
                st.warning(
                    f"{summary['unscheduled_count']} task(s) could not be scheduled — "
                    "no suitable time slot was available."
                )
                st.dataframe(
                    summary["unscheduled_tasks"],
                    use_container_width=True,
                    hide_index=True,
                )

            # AI explanation — the main new feature
            st.divider()
            st.subheader("AI Explanation")

            conf = agent.confidence
            level, reason = conf.get("level", "Unknown"), conf.get("reason", "")
            if level == "High":
                st.success(f"Confidence: {level} — {reason}")
            elif level == "Medium":
                st.warning(f"Confidence: {level} — {reason}")
            elif level == "Low":
                st.error(f"Confidence: {level} — {reason}")
            else:
                st.info(f"Confidence: {level}")

            st.markdown(explanation)

            # Agent reasoning trace — collapsed by default
            if agent.trace:
                with st.expander("View agent reasoning trace"):
                    for step in agent.trace:
                        st.markdown(f"- {step}")

            with st.expander("View raw plan"):
                st.text(plan.explain_plan())

        else:
            # ── Rule-based fallback (no API key) ──────────────────────────────
            plan = planner.generate_daily_plan(datetime.now())
            summary = plan.get_summary()

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Scheduled", summary["scheduled_count"])
            col_m2.metric("Could not schedule", summary["unscheduled_count"])
            col_m3.metric("Total time (min)", summary["total_time_minutes"])

            conflicts = plan.detect_conflicts()
            if conflicts:
                st.error(f"⚠️ {len(conflicts)} scheduling conflict(s) detected.")
                for c in conflicts:
                    st.error(c)
            else:
                st.success("No scheduling conflicts detected.")

            if summary["scheduled_tasks"]:
                st.write("**Chronological schedule:**")
                st.dataframe(
                    summary["scheduled_tasks"],
                    use_container_width=True,
                    hide_index=True,
                )

            if summary["unscheduled_tasks"]:
                st.warning(
                    f"{summary['unscheduled_count']} task(s) could not be scheduled — "
                    "no suitable time slot was available."
                )
                st.dataframe(
                    summary["unscheduled_tasks"],
                    use_container_width=True,
                    hide_index=True,
                )

            with st.expander("View full chronological plan"):
                st.text(plan.explain_plan())

            with st.expander("View scheduling decisions"):
                st.text(planner.explain_decisions(plan))
