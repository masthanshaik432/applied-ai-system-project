from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskType(Enum):
    FEEDING = "feeding"
    WALK = "walk"
    MEDICATION = "medication"
    APPOINTMENT = "appointment"
    GROOMING = "grooming"


# Maps frequency strings to their interval in days.
FREQUENCY_INTERVALS: dict[str, int] = {
    "daily":       1,
    "twice_daily": 1,   # same-day recurrence; scheduler handles the count
    "weekly":      7,
    "biweekly":    14,
    "monthly":     30,
}

# Health conditions that restrict scheduling certain task types.
_HEALTH_RESTRICTIONS: dict[str, set[TaskType]] = {
    "heart_disease": {TaskType.WALK},
    "arthritis":     set(),   # walks are reduced in priority but not blocked — movement prevents muscle loss
    "post_surgery":  {TaskType.WALK, TaskType.GROOMING},
    "obesity":       set(),   # no hard block — priority boost handled elsewhere
}


# ---------------------------------------------------------------------------
# Core data objects (dataclasses)
# ---------------------------------------------------------------------------

@dataclass
class Pet:
    name: str
    species: str
    age: int
    health_conditions: list[str] = field(default_factory=list)
    height: float = 0.0
    weight: float = 0.0

    def get_daily_needs(self) -> list[Task]:
        """Return a baseline list of Tasks derived from this pet's species and health data."""
        needs: list[Task] = []

        # Every pet needs feeding
        needs.append(Task(
            name=f"Feed {self.name}",
            task_type=TaskType.FEEDING,
            duration=15,
            priority=5,
            frequency="twice_daily",
            pet=self,
            is_flexible=False,
        ))

        # Dogs need a daily walk (lower priority if health conditions restrict it)
        if self.species.lower() == "dog":
            needs.append(Task(
                name=f"Walk {self.name}",
                task_type=TaskType.WALK,
                duration=30,
                priority=3 if self.special_care_needed() else 4,
                frequency="daily",
                pet=self,
                is_flexible=True,
            ))

        # Any recorded health condition triggers a daily medication task
        if self.health_conditions:
            needs.append(Task(
                name=f"Medication for {self.name}",
                task_type=TaskType.MEDICATION,
                duration=10,
                priority=5,
                frequency="daily",
                pet=self,
                is_flexible=False,
            ))

        return needs

    def special_care_needed(self) -> bool:
        """Return True if any health conditions require special handling."""
        return len(self.health_conditions) > 0


@dataclass
class Task:
    name: str
    task_type: TaskType
    duration: int                           # minutes
    priority: int                           # 1 (low) – 5 (high)
    frequency: str                          # e.g. "daily", "twice_daily", "weekly"
    pet: Pet = field(repr=False)
    is_flexible: bool = True
    last_completed: Optional[datetime] = None
    completed: bool = False

    def mark_complete(self) -> None:
        """Mark this task as completed and record the current timestamp."""
        self.completed = True
        self.last_completed = datetime.now()

    def is_due(self, date: datetime) -> bool:
        """Return True if this task is due on the given date based on its frequency and last completion."""
        target = date.date() if isinstance(date, datetime) else date

        if self.last_completed is None:
            return True

        last = self.last_completed.date()

        if self.frequency == "twice_daily":
            if last < target:
                return True
            if last == target:
                last_hour = self.last_completed.hour
                current_hour = date.hour if isinstance(date, datetime) else 12
                return last_hour < 12 <= current_hour
            return False

        interval = FREQUENCY_INTERVALS.get(self.frequency, 1)
        return (target - last).days >= interval

    def get_priority_score(self) -> float:
        """Return a weighted numeric score used to sort tasks, boosted by health conditions, task type, and overdue days."""
        score = float(self.priority)

        if not self.is_flexible:
            score += 1.0

        if self.pet.special_care_needed():
            score += 0.5

        if self.task_type in (TaskType.MEDICATION, TaskType.FEEDING):
            score += 1.0

        if self.last_completed is not None:
            interval = FREQUENCY_INTERVALS.get(self.frequency, 1)
            days_overdue = (datetime.now().date() - self.last_completed.date()).days - interval
            if days_overdue > 0:
                score += min(days_overdue * 0.5, 2.0)

        return score

    def next_occurrence(self) -> Optional["Task"]:
        """Return a fresh Task instance representing the next scheduled occurrence of this task.

        Only recurring frequencies ("daily", "twice_daily", "weekly") produce a
        successor. Non-recurring tasks ("biweekly", "monthly") return None because
        those are typically owner-managed rather than auto-generated.

        The new instance carries forward ``last_completed`` from the current task
        so that ``is_due()`` can correctly compute when the successor falls due,
        while ``completed`` is reset to False so it appears as a pending task in
        filters and the scheduler.

        Returns:
            A new Task with identical attributes and ``completed=False``, or
            None if this task's frequency is not in the recurring set.
        """
        recurring = {"daily", "twice_daily", "weekly"}
        if self.frequency not in recurring:
            return None

        return Task(
            name=self.name,
            task_type=self.task_type,
            duration=self.duration,
            priority=self.priority,
            frequency=self.frequency,
            pet=self.pet,
            is_flexible=self.is_flexible,
            last_completed=self.last_completed,  # carries forward so is_due() knows when it last ran
            completed=False,
        )

    def fits_time_slot(self, slot: TimeSlot) -> bool:
        """Return True if this task can fit within the given TimeSlot."""
        return slot.available and slot.duration() >= self.duration


@dataclass
class TimeSlot:
    start_time: datetime
    end_time: datetime
    available: bool = True

    def duration(self) -> int:
        """Return slot length in minutes."""
        return int((self.end_time - self.start_time).total_seconds() // 60)

    def can_fit(self, task: Task) -> bool:
        """Return True if the task duration fits within this slot."""
        return self.available and self.duration() >= task.duration

    def split(self, task_duration: int) -> list[TimeSlot]:
        """Carve task_duration minutes from the start of this slot and return any remaining time as a new TimeSlot."""
        task_end = self.start_time + timedelta(minutes=task_duration)
        if task_end >= self.end_time:
            return []
        return [TimeSlot(start_time=task_end, end_time=self.end_time, available=True)]


@dataclass
class Notification:
    task: Task
    trigger_time: datetime
    message: str

    def send(self) -> None:
        """Dispatch the notification (prints to console; swap for push/email in prod)."""
        print(f"[{self.trigger_time.strftime('%H:%M')}] REMINDER — {self.message}")


@dataclass
class TaskHistory:
    completed_tasks: list[tuple[Task, datetime]] = field(default_factory=list)

    def _records_for(self, task: Task) -> list[datetime]:
        """Return all completion timestamps for the given task."""
        return [
            ts for t, ts in self.completed_tasks
            if t.name == task.name and t.pet.name == task.pet.name
        ]

    def log_completion(self, task: Task) -> None:
        """Record that a task was completed right now."""
        self.completed_tasks.append((task, datetime.now()))

    def get_last_completed(self, task: Task) -> Optional[datetime]:
        """Return the most recent completion datetime for the given task."""
        times = self._records_for(task)
        return max(times) if times else None

    def get_completion_rate(self, task: Task, since: Optional[datetime] = None) -> float:
        """Return completed vs expected occurrences as a 0.0–1.0 ratio, optionally filtered by a start date."""
        all_times = self._records_for(task)
        if not all_times:
            return 0.0

        cutoff = since or min(all_times)
        completions_in_window = [ts for ts in all_times if ts >= cutoff]
        if not completions_in_window:
            return 0.0

        days_in_window = max((datetime.now() - cutoff).days, 1)
        interval = FREQUENCY_INTERVALS.get(task.frequency, 1)
        expected = days_in_window / interval

        return min(len(completions_in_window) / expected, 1.0)

    def streak(self, task: Task) -> int:
        """Return the number of consecutive days the task has been completed."""
        completed_dates = sorted(
            {ts.date() for ts in self._records_for(task)},
            reverse=True,
        )
        if not completed_dates:
            return 0

        # Start from the most recent completion, not today —
        # prevents a streak from resetting just because today isn't done yet.
        check = max(completed_dates[0], datetime.now().date())

        streak = 0
        for d in completed_dates:
            if d == check:
                streak += 1
                check -= timedelta(days=1)
            else:
                break
        return streak


@dataclass
class DailyPlan:
    date: datetime
    scheduled_tasks: list[tuple[Task, TimeSlot]] = field(default_factory=list)
    unscheduled_tasks: list[Task] = field(default_factory=list)

    @property
    def total_time(self) -> int:
        """Compute total scheduled minutes on demand — never stale."""
        return sum(task.duration for task, _ in self.scheduled_tasks)

    def add_task(self, task: Task, slot: TimeSlot) -> None:
        """Add a task/slot pair to the plan and mark the slot unavailable."""
        slot.available = False
        self.scheduled_tasks.append((task, slot))

    def calculate_total_time(self) -> int:
        """Delegate to the total_time property (kept for API compatibility)."""
        return self.total_time

    def get_summary(self) -> dict:
        """Return a dict summary suitable for display in the Streamlit UI."""
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "scheduled_count": len(self.scheduled_tasks),
            "unscheduled_count": len(self.unscheduled_tasks),
            "total_time_minutes": self.total_time,
            "scheduled_tasks": [
                {
                    "task": task.name,
                    "pet": task.pet.name,
                    "type": task.task_type.value,
                    "duration_minutes": task.duration,
                    "priority": task.priority,
                    "start": slot.start_time.strftime("%H:%M"),
                    "end": slot.end_time.strftime("%H:%M"),
                    "flexible": task.is_flexible,
                }
                for task, slot in sorted(self.scheduled_tasks, key=lambda x: x[1].start_time)
            ],
            "unscheduled_tasks": [
                {"task": t.name, "pet": t.pet.name, "reason": "no suitable slot found"}
                for t in self.unscheduled_tasks
            ],
        }

    def detect_conflicts(self) -> list[str]:
        """Check every pair of scheduled tasks for overlapping time slots.

        Uses the standard interval-overlap test:
            A.start < B.end  AND  B.start < A.end

        Runs in O(n²) over the number of scheduled tasks — acceptable for
        typical daily plans (< 20 tasks) and avoids crashing the program by
        returning warnings instead of raising exceptions.

        This catches conflicts introduced by external slot injection (e.g. the
        Streamlit UI or manual DailyPlan construction). The normal allocator
        prevents overlaps by design, so this acts as a safety net.

        Returns:
            A list of human-readable warning strings, one per conflicting pair.
            An empty list means the schedule is conflict-free.
        """
        warnings_out: list[str] = []

        for i, (task_a, slot_a) in enumerate(self.scheduled_tasks):
            for task_b, slot_b in self.scheduled_tasks[i + 1:]:
                overlaps = (
                    slot_a.start_time < slot_b.end_time
                    and slot_b.start_time < slot_a.end_time
                )
                if overlaps:
                    warnings_out.append(
                        f"CONFLICT: '{task_a.name}' ({task_a.pet.name}) "
                        f"{slot_a.start_time.strftime('%H:%M')}–{slot_a.end_time.strftime('%H:%M')}"
                        f"  overlaps  "
                        f"'{task_b.name}' ({task_b.pet.name}) "
                        f"{slot_b.start_time.strftime('%H:%M')}–{slot_b.end_time.strftime('%H:%M')}"
                    )

        return warnings_out

    def explain_plan(self) -> str:
        """Return a human-readable explanation of the day's schedule."""
        lines = [f"Daily plan for {self.date.strftime('%A, %B %d %Y')}:"]
        lines.append(f"  {len(self.scheduled_tasks)} task(s) scheduled — {self.total_time} minutes total\n")

        for task, slot in sorted(self.scheduled_tasks, key=lambda x: x[1].start_time):
            tag = "(fixed)" if not task.is_flexible else "(flexible)"
            lines.append(
                f"  {slot.start_time.strftime('%H:%M')} – {slot.end_time.strftime('%H:%M')}  "
                f"{task.name} [{task.task_type.value}] {tag}"
            )

        if self.unscheduled_tasks:
            lines.append("\n  Could not schedule:")
            for t in self.unscheduled_tasks:
                lines.append(f"    - {t.name} (priority {t.priority})")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Configuration / preferences
# ---------------------------------------------------------------------------

class OwnerPreferences:
    def __init__(
        self,
        max_daily_time: int,
        preferred_times: dict,
        task_priorities_override: dict,
        break_duration: int = 15,
    ):
        self.max_daily_time = max_daily_time            # minutes per day
        self.preferred_times = preferred_times          # e.g. {"morning": (7, 12)}
        self.task_priorities_override = task_priorities_override
        self.break_duration = break_duration            # minutes between tasks

    def adjust_task_priority(self, task: Task) -> int:
        """Return the owner-overridden priority for the task, falling back to the task's own priority."""
        override = (
            self.task_priorities_override.get(task.name)
            or self.task_priorities_override.get(task.task_type.value)
        )
        return int(override) if override is not None else task.priority

    def is_preferred_time(self, task: Task, slot: TimeSlot) -> bool:
        """Return True if the slot falls within the owner's preferred time window for this task type."""
        slot_hour = slot.start_time.hour

        type_window = self.preferred_times.get(task.task_type.value)
        if type_window and isinstance(type_window, (tuple, list)):
            return type_window[0] <= slot_hour < type_window[1]

        for _, window in self.preferred_times.items():
            if isinstance(window, (tuple, list)) and len(window) == 2:
                start_h, end_h = window
                if isinstance(start_h, int) and start_h <= slot_hour < end_h:
                    return True

        return False

    def get_available_time_slots(self, for_date: Optional[datetime] = None) -> list[TimeSlot]:
        """Return one TimeSlot per preferred window for the given date, capped to max_daily_time."""
        base = (for_date or datetime.now()).date()
        slots: list[TimeSlot] = []
        remaining_budget = self.max_daily_time

        for _, window in self.preferred_times.items():
            if remaining_budget <= 0:
                break
            if not isinstance(window, (tuple, list)) or len(window) != 2:
                continue

            start_h, end_h = window
            slot_start = datetime(base.year, base.month, base.day, start_h, 0)
            slot_end = datetime(base.year, base.month, base.day, end_h, 0)
            window_minutes = int((slot_end - slot_start).total_seconds() // 60)

            capped_minutes = min(window_minutes, remaining_budget)
            capped_end = slot_start + timedelta(minutes=capped_minutes)
            slots.append(TimeSlot(start_time=slot_start, end_time=capped_end))
            remaining_budget -= capped_minutes

        return slots


# ---------------------------------------------------------------------------
# Constraint checker
# ---------------------------------------------------------------------------

class Constraint:
    def __init__(self, rules: list = None):
        self.rules: list = rules or []

    def check_time_constraint(self, task: Task, slot: TimeSlot) -> bool:
        """Return True if the slot is available and long enough for the task."""
        return slot.available and slot.duration() >= task.duration

    def check_priority_constraint(self, task: Task) -> bool:
        """Return True if the task's priority is within the valid 1–5 range."""
        return 1 <= task.priority <= 5

    def check_pet_health_constraints(self, task: Task) -> bool:
        """Return True if no health condition on the pet blocks this task type."""
        for condition in task.pet.health_conditions:
            restricted = _HEALTH_RESTRICTIONS.get(condition.lower(), set())
            if task.task_type in restricted:
                return False
        return True

    def validate_schedule(self, plan: DailyPlan) -> bool:
        """Return True if every scheduled task passes duration, priority, and pet health checks."""
        for task, slot in plan.scheduled_tasks:
            if slot.duration() < task.duration:     # duration fit check (no availability flag)
                return False
            if not self.check_priority_constraint(task):
                return False
            if not self.check_pet_health_constraints(task):
                return False
        return True


# ---------------------------------------------------------------------------
# Planner (orchestrator)
# ---------------------------------------------------------------------------

class Planner:
    def __init__(
        self,
        pets: list[Pet],
        tasks: list[Task],
        preferences: OwnerPreferences,
        history: TaskHistory,
        constraint: Constraint,
    ):
        self.pets = pets
        self.tasks = tasks
        self.preferences = preferences
        self.history = history
        self.constraint = constraint

    def filter_due_tasks(self, date: datetime) -> list[Task]:
        """Return tasks due on the given date, synced from history and filtered by health constraints."""
        due: list[Task] = []
        for task in self.tasks:
            # Keep the task object in sync with the history record
            last = self.history.get_last_completed(task)
            if last is not None:
                task.last_completed = last

            if task.is_due(date) and self.constraint.check_pet_health_constraints(task):
                due.append(task)
        return due

    def filter_tasks(
        self,
        completed: Optional[bool] = None,
        pet_name: Optional[str] = None,
    ) -> list[Task]:
        """Return a filtered view of all tasks registered with this planner.

        Filters are optional and combinable — both can be applied at once,
        either alone, or omitted entirely to return the full task list.
        The original ``self.tasks`` list is never mutated.

        Args:
            completed: Pass ``True`` to return only tasks where ``task.completed
                       is True``; ``False`` for only incomplete tasks; ``None``
                       (default) to skip completion filtering entirely.
            pet_name:  Case-insensitive pet name to match against
                       ``task.pet.name``. Pass ``None`` (default) to include
                       tasks for all pets.

        Returns:
            A new list of Task objects that satisfy all supplied filters.
        """
        results = self.tasks

        if completed is not None:
            results = [t for t in results if t.completed == completed]

        if pet_name is not None:
            name_lower = pet_name.lower()
            results = [t for t in results if t.pet.name.lower() == name_lower]

        return results

    def complete_task(self, task: Task) -> Optional[Task]:
        """Mark a task as done, persist it to history, and auto-register its successor.

        This is the preferred way to complete a task instead of calling
        ``task.mark_complete()`` directly, because it keeps three things
        in sync atomically:

        1. Sets ``task.completed = True`` and stamps ``task.last_completed``.
        2. Appends the completion record to ``TaskHistory`` so
           ``get_completion_rate()`` and ``streak()`` stay accurate.
        3. Calls ``task.next_occurrence()`` and, if a successor is returned,
           appends it to ``self.tasks`` so it appears in future scheduling
           and filter calls without any manual intervention.

        Args:
            task: A Task object that is currently registered in ``self.tasks``.

        Returns:
            The newly created successor Task if the frequency is recurring
            ("daily", "twice_daily", or "weekly"), otherwise None.
        """
        task.mark_complete()
        self.history.log_completion(task)

        next_task = task.next_occurrence()
        if next_task is not None:
            self.tasks.append(next_task)

        return next_task

    def prioritize_tasks(self, tasks: list[Task]) -> list[Task]:
        """Sort tasks by priority score descending, applying owner preference overrides."""
        def sort_key(task: Task) -> float:
            adjusted = self.preferences.adjust_task_priority(task)
            original = task.priority
            task.priority = adjusted
            score = task.get_priority_score()
            task.priority = original   # restore — do not mutate the object permanently
            return score

        return sorted(tasks, key=sort_key, reverse=True)

    def allocate_tasks_to_slots(self, tasks: list[Task], date: Optional[datetime] = None) -> DailyPlan:
        """Place inflexible tasks first then flexible tasks into available slots, returning a DailyPlan."""
        plan = DailyPlan(date=date or datetime.now())
        slots = self.preferences.get_available_time_slots(for_date=date)

        inflexible = [t for t in tasks if not t.is_flexible]
        flexible   = [t for t in tasks if t.is_flexible]

        for task_group in (inflexible, flexible):
            for task in task_group:
                placed = False
                for slot in list(slots):
                    if (
                        self.constraint.check_time_constraint(task, slot)
                        and self.constraint.check_pet_health_constraints(task)
                    ):
                        # Carve a slot exactly the size of this task
                        task_slot = TimeSlot(
                            start_time=slot.start_time,
                            end_time=slot.start_time + timedelta(minutes=task.duration),
                        )
                        plan.add_task(task, task_slot)

                        # Shrink the parent slot by task duration + inter-task break
                        remainder = slot.split(task.duration + self.preferences.break_duration)
                        slots.remove(slot)
                        slots = remainder + slots   # fill from the same window first
                        placed = True
                        break

                if not placed:
                    plan.unscheduled_tasks.append(task)

        return plan

    def generate_daily_plan(self, date: datetime) -> DailyPlan:
        """End-to-end pipeline: filter → prioritize → allocate → validate → return."""
        due_tasks  = self.filter_due_tasks(date)
        prioritized = self.prioritize_tasks(due_tasks)
        plan = self.allocate_tasks_to_slots(prioritized, date=date)

        if not self.constraint.validate_schedule(plan):
            warnings.warn(
                "Generated plan contains one or more constraint violations. "
                "Review plan.unscheduled_tasks for tasks that could not be placed.",
                stacklevel=2,
            )

        for conflict in plan.detect_conflicts():
            warnings.warn(conflict, stacklevel=2)

        return plan

    def explain_decisions(self, plan: DailyPlan) -> str:
        """Return a natural-language summary of why each task was scheduled or skipped (LLM hook point)."""
        lines = [f"Scheduling decisions for {plan.date.strftime('%Y-%m-%d')}:\n"]

        for task, slot in sorted(plan.scheduled_tasks, key=lambda x: x[1].start_time):
            reason = "fixed time requirement" if not task.is_flexible else "best available slot"
            lines.append(
                f"  '{task.name}' ({task.pet.name}) → {slot.start_time.strftime('%H:%M')} "
                f"| priority {task.priority} | {reason}"
            )

        if plan.unscheduled_tasks:
            lines.append("\nCould not schedule:")
            for task in plan.unscheduled_tasks:
                lines.append(
                    f"  '{task.name}' ({task.pet.name}) "
                    f"— no slot with {task.duration} min available"
                )

        return "\n".join(lines)
