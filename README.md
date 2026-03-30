# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Smarter Scheduling

Several algorithmic improvements were added to `pawpal_system.py` beyond the base scheduler:

**Task filtering** — `Planner.filter_tasks(completed, pet_name)` returns a filtered view of all registered tasks. Both parameters are optional and combinable, so you can query incomplete tasks for a specific pet in one call without mutating the task list.

**Auto-recurring tasks** — `Task.next_occurrence()` generates a successor instance when a recurring task is completed. `Planner.complete_task()` ties this together: it marks the task done, logs it to `TaskHistory`, and appends the successor to the planner automatically. Only `daily`, `twice_daily`, and `weekly` tasks recur; non-recurring frequencies (`biweekly`, `monthly`) return `None` and require manual rescheduling.

**Conflict detection** — `DailyPlan.detect_conflicts()` checks every pair of scheduled tasks for overlapping time slots using the interval-overlap test (`A.start < B.end AND B.start < A.end`). It returns a list of human-readable warning strings rather than raising exceptions, so the program keeps running and the owner sees exactly which tasks clash. `generate_daily_plan()` calls this automatically on every generated plan.

**Streak fix** — `TaskHistory.streak()` was corrected to start counting from the most recent completion date rather than today. Previously, a streak would reset to 0 any time the task had not yet been completed on the current day, even if the owner had a long run of consecutive prior days.

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.


## Testing PawPal + 
Run the tests with:

python -m pytest

The test suite checks a few key parts of the system. First, it makes sure basic task behavior works. That includes marking tasks complete, updating timestamps, and logging that information in history. It also verifies that adding tasks to the planner updates the task list correctly and keeps the association with each pet.
A large part of the tests focuses on scheduling. They check that tasks are ordered correctly in time, and that they do not overlap unless there is actually a conflict. The tests also confirm that the two-pass scheduling logic works as intended, with inflexible tasks placed before flexible ones. There are also simple edge cases like empty task lists or single-task plans to make sure nothing breaks in those situations.
There is also coverage for recurrence. When a task is completed, the system should create the next one if it is a daily or weekly task. The tests make sure that happens correctly, and that the new task has the right timing and is not immediately due again.
The final section checks conflict detection. It makes sure overlapping tasks are flagged and that the messages include the task names. It also confirms that back-to-back or separate tasks do not trigger false conflicts.

Confidence Level: 4/5
Overall, the system is in a solid place. The main behavior is well tested and reliable. The biggest limitation is the scheduling approach. It is simple and predictable, but it does not always produce the most efficient plan when the schedule gets more complex.