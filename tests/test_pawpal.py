import pytest
from datetime import datetime, timedelta
from pawpal_system import (
    Constraint,
    DailyPlan,
    OwnerPreferences,
    Pet,
    Planner,
    Task,
    TaskHistory,
    TaskType,
    TimeSlot,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rex():
    return Pet(name="Rex", species="dog", age=4)

@pytest.fixture
def luna():
    return Pet(name="Luna", species="cat", age=2)

@pytest.fixture
def planner(rex, luna):
    tasks = [
        Task(name="Walk Rex",   task_type=TaskType.WALK,     duration=30, priority=3, frequency="daily",   pet=rex),
        Task(name="Feed Rex",   task_type=TaskType.FEEDING,  duration=15, priority=5, frequency="daily",   pet=rex),
        Task(name="Feed Luna",  task_type=TaskType.FEEDING,  duration=15, priority=5, frequency="daily",   pet=luna),
    ]
    preferences = OwnerPreferences(
        max_daily_time=120,
        preferred_times={"morning": (7, 12)},
        task_priorities_override={},
    )
    return Planner(
        pets=[rex, luna],
        tasks=tasks,
        preferences=preferences,
        history=TaskHistory(),
        constraint=Constraint(),
    )


# ---------------------------------------------------------------------------
# Test 1 — mark_complete() changes task status
# ---------------------------------------------------------------------------

def test_mark_complete_sets_completed_flag(rex):
    task = Task(
        name="Rex medication",
        task_type=TaskType.MEDICATION,
        duration=10,
        priority=5,
        frequency="daily",
        pet=rex,
    )

    assert task.completed is False
    assert task.last_completed is None

    task.mark_complete()

    assert task.completed is True
    assert task.last_completed is not None


# ---------------------------------------------------------------------------
# Test 2 — adding a task to a planner increases that pet's task count
# ---------------------------------------------------------------------------

def test_adding_task_increases_pet_task_count(planner, rex):
    rex_tasks_before = [t for t in planner.tasks if t.pet.name == rex.name]
    count_before = len(rex_tasks_before)

    planner.tasks.append(Task(
        name="Rex grooming",
        task_type=TaskType.GROOMING,
        duration=20,
        priority=2,
        frequency="weekly",
        pet=rex,
    ))

    rex_tasks_after = [t for t in planner.tasks if t.pet.name == rex.name]
    assert len(rex_tasks_after) == count_before + 1


# ===========================================================================
# SORTING CORRECTNESS — scheduled tasks are returned in chronological order
# ===========================================================================

# ---------------------------------------------------------------------------
# Helper: build a planner whose time window produces multiple distinct slots
# ---------------------------------------------------------------------------

def _make_planner(pets, tasks, max_time=300):
    preferences = OwnerPreferences(
        max_daily_time=max_time,
        preferred_times={"morning": (7, 12)},
        task_priorities_override={},
        break_duration=0,        # no break so tasks pack tightly and we can predict start times
    )
    return Planner(
        pets=pets,
        tasks=tasks,
        preferences=preferences,
        history=TaskHistory(),
        constraint=Constraint(),
    )


# Happy path: two tasks with different priorities end up in time order in the plan
def test_scheduled_tasks_are_in_chronological_order(rex, luna):
    tasks = [
        Task(name="Walk Rex",  task_type=TaskType.WALK,    duration=30, priority=3, frequency="daily", pet=rex),
        Task(name="Feed Luna", task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=luna),
    ]
    planner = _make_planner([rex, luna], tasks)
    plan = planner.allocate_tasks_to_slots(planner.prioritize_tasks(tasks), date=datetime(2025, 1, 1, 8, 0))

    start_times = [slot.start_time for _, slot in plan.scheduled_tasks]
    assert start_times == sorted(start_times), "Scheduled tasks must be in ascending start-time order"


# Happy path: three tasks pack sequentially — each starts after the previous ends
def test_sequential_tasks_have_non_overlapping_start_times(rex):
    tasks = [
        Task(name="Feed Rex",    task_type=TaskType.FEEDING,   duration=15, priority=5, frequency="daily", pet=rex),
        Task(name="Walk Rex",    task_type=TaskType.WALK,       duration=30, priority=3, frequency="daily", pet=rex),
        Task(name="Groom Rex",   task_type=TaskType.GROOMING,   duration=20, priority=2, frequency="daily", pet=rex),
    ]
    planner = _make_planner([rex], tasks)
    plan = planner.allocate_tasks_to_slots(planner.prioritize_tasks(tasks), date=datetime(2025, 1, 1, 8, 0))

    slots = [slot for _, slot in plan.scheduled_tasks]
    for i in range(len(slots) - 1):
        assert slots[i].end_time <= slots[i + 1].start_time, (
            f"Task at index {i} ends after task at index {i + 1} starts"
        )


# Edge case: single task — trivially chronological
def test_single_task_plan_is_chronological(rex):
    tasks = [Task(name="Feed Rex", task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=rex)]
    planner = _make_planner([rex], tasks)
    plan = planner.allocate_tasks_to_slots(tasks, date=datetime(2025, 1, 1, 8, 0))

    assert len(plan.scheduled_tasks) == 1   # placed
    # A one-element list is trivially sorted; confirm no exception and correct placement
    start_times = [slot.start_time for _, slot in plan.scheduled_tasks]
    assert start_times == sorted(start_times)


# Edge case: no tasks — plan produces an empty scheduled list with no errors
def test_empty_task_list_produces_empty_plan(rex):
    planner = _make_planner([rex], [])
    plan = planner.allocate_tasks_to_slots([], date=datetime(2025, 1, 1, 8, 0))

    assert plan.scheduled_tasks == []
    assert plan.unscheduled_tasks == []


# Edge case: high-priority task still appears first in the plan
# (inflexible tasks are placed before flexible ones regardless of priority)
def test_inflexible_task_is_scheduled_before_flexible_task(rex):
    low_priority_fixed = Task(
        name="Rex medication", task_type=TaskType.MEDICATION,
        duration=10, priority=1, frequency="daily", pet=rex, is_flexible=False,
    )
    high_priority_flex = Task(
        name="Walk Rex", task_type=TaskType.WALK,
        duration=30, priority=5, frequency="daily", pet=rex, is_flexible=True,
    )
    planner = _make_planner([rex], [low_priority_fixed, high_priority_flex])
    plan = planner.allocate_tasks_to_slots([low_priority_fixed, high_priority_flex], date=datetime(2025, 1, 1, 8, 0))

    scheduled_names = [task.name for task, _ in plan.scheduled_tasks]
    assert scheduled_names.index("Rex medication") < scheduled_names.index("Walk Rex"), (
        "Inflexible task must be placed (and therefore start earlier) before the flexible task"
    )


# ===========================================================================
# RECURRENCE LOGIC — completing a daily task registers a successor
# ===========================================================================

# Happy path: completing a daily task adds exactly one new task to the planner
def test_complete_daily_task_adds_successor(planner):
    daily_task = next(t for t in planner.tasks if t.name == "Feed Rex")
    count_before = len(planner.tasks)

    successor = planner.complete_task(daily_task)

    assert successor is not None, "complete_task must return a successor for a daily task"
    assert len(planner.tasks) == count_before + 1, "Successor must be appended to planner.tasks"


# Happy path: successor carries forward last_completed so is_due() is correct
def test_successor_last_completed_matches_original(planner):
    daily_task = next(t for t in planner.tasks if t.name == "Feed Rex")
    successor = planner.complete_task(daily_task)

    assert successor.last_completed == daily_task.last_completed, (
        "Successor's last_completed must equal the original task's completion time"
    )


# Happy path: successor is due the following day but not the same day
def test_successor_is_due_next_day_not_same_day(planner):
    daily_task = next(t for t in planner.tasks if t.name == "Feed Rex")
    successor = planner.complete_task(daily_task)

    today = daily_task.last_completed
    tomorrow = today + timedelta(days=1)

    assert not successor.is_due(today), "Successor must NOT be due on the same day it was just completed"
    assert successor.is_due(tomorrow), "Successor MUST be due the following day"


# Happy path: successor starts as incomplete
def test_successor_is_not_completed(planner):
    daily_task = next(t for t in planner.tasks if t.name == "Feed Rex")
    successor = planner.complete_task(daily_task)

    assert successor.completed is False, "Successor must start with completed=False"


# Edge case: completing a weekly task also produces a successor
def test_complete_weekly_task_adds_successor(rex):
    weekly_task = Task(
        name="Groom Rex", task_type=TaskType.GROOMING,
        duration=20, priority=2, frequency="weekly", pet=rex,
    )
    planner = _make_planner([rex], [weekly_task])
    count_before = len(planner.tasks)

    successor = planner.complete_task(weekly_task)

    assert successor is not None
    assert len(planner.tasks) == count_before + 1


# Edge case: completing a monthly task does NOT produce a successor
def test_complete_monthly_task_returns_none(rex):
    monthly_task = Task(
        name="Vet visit", task_type=TaskType.APPOINTMENT,
        duration=60, priority=4, frequency="monthly", pet=rex,
    )
    planner = _make_planner([rex], [monthly_task])
    count_before = len(planner.tasks)

    successor = planner.complete_task(monthly_task)

    assert successor is None, "monthly tasks must not auto-generate a successor"
    assert len(planner.tasks) == count_before, "Task list must not grow for non-recurring frequency"


# Edge case: completing a task twice still only adds one successor per call
def test_completing_task_twice_adds_two_successors(planner):
    daily_task = next(t for t in planner.tasks if t.name == "Feed Rex")
    count_before = len(planner.tasks)

    planner.complete_task(daily_task)
    planner.complete_task(daily_task)   # completing the same object again (simulates user double-tap)

    assert len(planner.tasks) == count_before + 2, (
        "Each call to complete_task must append a successor regardless of prior calls"
    )


# Edge case: completion is logged in history
def test_complete_task_logs_to_history(planner):
    daily_task = next(t for t in planner.tasks if t.name == "Feed Rex")
    planner.complete_task(daily_task)

    last = planner.history.get_last_completed(daily_task)
    assert last is not None, "TaskHistory must record the completion timestamp"


# ===========================================================================
# CONFLICT DETECTION — overlapping time slots are flagged
# ===========================================================================

# Happy path: two back-to-back non-overlapping tasks produce no conflicts
def test_no_conflict_for_sequential_tasks(rex, luna):
    base = datetime(2025, 1, 1, 9, 0)
    task_a = Task(name="Feed Rex",  task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=rex)
    task_b = Task(name="Feed Luna", task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=luna)

    slot_a = TimeSlot(start_time=base,                        end_time=base + timedelta(minutes=15))
    slot_b = TimeSlot(start_time=base + timedelta(minutes=15), end_time=base + timedelta(minutes=30))

    plan = DailyPlan(date=base, scheduled_tasks=[(task_a, slot_a), (task_b, slot_b)])
    assert plan.detect_conflicts() == [], "Back-to-back tasks must not be reported as conflicting"


# Happy path: tasks on completely separate hours produce no conflicts
def test_no_conflict_for_widely_separated_tasks(rex):
    task_a = Task(name="Feed Rex",  task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=rex)
    task_b = Task(name="Walk Rex",  task_type=TaskType.WALK,    duration=30, priority=3, frequency="daily", pet=rex)

    slot_a = TimeSlot(start_time=datetime(2025, 1, 1,  8, 0), end_time=datetime(2025, 1, 1,  8, 15))
    slot_b = TimeSlot(start_time=datetime(2025, 1, 1, 11, 0), end_time=datetime(2025, 1, 1, 11, 30))

    plan = DailyPlan(date=datetime(2025, 1, 1), scheduled_tasks=[(task_a, slot_a), (task_b, slot_b)])
    assert plan.detect_conflicts() == []


# Happy path: a plan with a single task never produces a conflict
def test_single_task_no_conflict(rex):
    task = Task(name="Feed Rex", task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=rex)
    slot = TimeSlot(start_time=datetime(2025, 1, 1, 8, 0), end_time=datetime(2025, 1, 1, 8, 15))

    plan = DailyPlan(date=datetime(2025, 1, 1), scheduled_tasks=[(task, slot)])
    assert plan.detect_conflicts() == []


# Happy path: empty plan has no conflicts
def test_empty_plan_no_conflict():
    plan = DailyPlan(date=datetime(2025, 1, 1), scheduled_tasks=[])
    assert plan.detect_conflicts() == []


# Edge case: exact same start and end time (duplicate slot) is flagged
def test_exact_duplicate_slot_is_flagged(rex, luna):
    task_a = Task(name="Feed Rex",  task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=rex)
    task_b = Task(name="Feed Luna", task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=luna)

    slot_a = TimeSlot(start_time=datetime(2025, 1, 1, 9, 0), end_time=datetime(2025, 1, 1, 9, 15))
    slot_b = TimeSlot(start_time=datetime(2025, 1, 1, 9, 0), end_time=datetime(2025, 1, 1, 9, 15))

    plan = DailyPlan(date=datetime(2025, 1, 1), scheduled_tasks=[(task_a, slot_a), (task_b, slot_b)])
    conflicts = plan.detect_conflicts()
    assert len(conflicts) == 1, "Exact duplicate slots must produce exactly one conflict entry"


# Edge case: partial overlap (task B starts before task A ends) is flagged
def test_partial_overlap_is_flagged(rex, luna):
    task_a = Task(name="Walk Rex",  task_type=TaskType.WALK,    duration=30, priority=3, frequency="daily", pet=rex)
    task_b = Task(name="Feed Luna", task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=luna)

    slot_a = TimeSlot(start_time=datetime(2025, 1, 1, 9,  0), end_time=datetime(2025, 1, 1, 9, 30))
    slot_b = TimeSlot(start_time=datetime(2025, 1, 1, 9, 20), end_time=datetime(2025, 1, 1, 9, 35))

    plan = DailyPlan(date=datetime(2025, 1, 1), scheduled_tasks=[(task_a, slot_a), (task_b, slot_b)])
    conflicts = plan.detect_conflicts()
    assert len(conflicts) >= 1, "Partially overlapping tasks must be flagged as a conflict"


# Edge case: one task fully contained inside another is flagged
def test_contained_overlap_is_flagged(rex, luna):
    outer = Task(name="Long walk",  task_type=TaskType.WALK,    duration=60, priority=3, frequency="daily", pet=rex)
    inner = Task(name="Feed Luna",  task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=luna)

    slot_outer = TimeSlot(start_time=datetime(2025, 1, 1, 9,  0), end_time=datetime(2025, 1, 1, 10,  0))
    slot_inner = TimeSlot(start_time=datetime(2025, 1, 1, 9, 15), end_time=datetime(2025, 1, 1,  9, 30))

    plan = DailyPlan(date=datetime(2025, 1, 1), scheduled_tasks=[(outer, slot_outer), (inner, slot_inner)])
    conflicts = plan.detect_conflicts()
    assert len(conflicts) >= 1, "A slot fully contained inside another must be detected as a conflict"


# Edge case: three mutually-overlapping tasks produce three conflict pairs
def test_three_overlapping_tasks_produce_three_conflicts(rex):
    task_a = Task(name="Task A", task_type=TaskType.FEEDING,  duration=30, priority=5, frequency="daily", pet=rex)
    task_b = Task(name="Task B", task_type=TaskType.WALK,     duration=30, priority=4, frequency="daily", pet=rex)
    task_c = Task(name="Task C", task_type=TaskType.GROOMING, duration=30, priority=3, frequency="daily", pet=rex)

    # All three share the same 30-minute window
    slot = TimeSlot(start_time=datetime(2025, 1, 1, 9, 0), end_time=datetime(2025, 1, 1, 9, 30))
    slot_a = TimeSlot(start_time=slot.start_time, end_time=slot.end_time)
    slot_b = TimeSlot(start_time=slot.start_time, end_time=slot.end_time)
    slot_c = TimeSlot(start_time=slot.start_time, end_time=slot.end_time)

    plan = DailyPlan(date=datetime(2025, 1, 1), scheduled_tasks=[(task_a, slot_a), (task_b, slot_b), (task_c, slot_c)])
    conflicts = plan.detect_conflicts()
    assert len(conflicts) == 3, "Three mutually-overlapping tasks must produce 3 conflict pairs (A-B, A-C, B-C)"


# Edge case: conflict message contains both task names
def test_conflict_message_contains_task_names(rex, luna):
    task_a = Task(name="Walk Rex",  task_type=TaskType.WALK,    duration=30, priority=3, frequency="daily", pet=rex)
    task_b = Task(name="Feed Luna", task_type=TaskType.FEEDING, duration=15, priority=5, frequency="daily", pet=luna)

    slot_a = TimeSlot(start_time=datetime(2025, 1, 1, 9,  0), end_time=datetime(2025, 1, 1, 9, 30))
    slot_b = TimeSlot(start_time=datetime(2025, 1, 1, 9, 10), end_time=datetime(2025, 1, 1, 9, 25))

    plan = DailyPlan(date=datetime(2025, 1, 1), scheduled_tasks=[(task_a, slot_a), (task_b, slot_b)])
    conflicts = plan.detect_conflicts()

    assert any("Walk Rex" in msg for msg in conflicts), "Conflict message must name the first task"
    assert any("Feed Luna" in msg for msg in conflicts), "Conflict message must name the second task"
