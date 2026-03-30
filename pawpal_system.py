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
    "arthritis":     {TaskType.WALK},
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

    def is_due(self, date: datetime) -> bool:
        """Return True if this task is due on the given date.

        For twice_daily tasks, the task is due again if the last completion
        was before noon and the current hour is noon or later.
        """
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
        """Return a numeric score used for sorting.

        Base priority is boosted by:
        - +1.0 for inflexible tasks (must be placed first)
        - +0.5 if the pet has health conditions
        - +1.0 for MEDICATION or FEEDING task types
        - up to +2.0 for overdue tasks (0.5 per overdue day, capped)
        """
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
        """Split this slot around a task block; return remaining free time as new slot(s).

        Carves task_duration minutes from the start of the slot. Returns an empty
        list if no time remains after the task.
        """
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
        """Return the ratio of completed vs expected occurrences (0.0–1.0).

        Args:
            task:  The task to evaluate.
            since: If provided, only consider completions on or after this date.
                   Defaults to the earliest recorded completion.
        """
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

        streak = 0
        check = datetime.now().date()
        for d in completed_dates:
            if d == check:
                streak += 1
                check -= timedelta(days=1)
            elif d < check:
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
        """Return an adjusted priority for the task based on owner overrides.

        Override keys can be task names (e.g. "Walk Rex") or TaskType values
        (e.g. "walk"). Task-name keys take precedence over type-level keys.
        """
        override = (
            self.task_priorities_override.get(task.name)
            or self.task_priorities_override.get(task.task_type.value)
        )
        return int(override) if override is not None else task.priority

    def is_preferred_time(self, task: Task, slot: TimeSlot) -> bool:
        """Return True if the slot falls within the owner's preferred window for this task.

        Checks task-type-specific windows first (e.g. "medication": (8, 9)),
        then falls back to named time-of-day windows (e.g. "morning": (7, 12)).
        """
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
        """Return time slots that respect max_daily_time and break rules.

        Generates one contiguous TimeSlot per preferred_times window on for_date
        (defaults to today). Total slot time is capped at max_daily_time.
        """
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
        """Run all constraint checks across every task in the plan.

        Returns True only if every scheduled task passes time, priority,
        and pet health checks.
        """
        for task, slot in plan.scheduled_tasks:
            if not self.check_time_constraint(task, slot):
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
        """Return only the tasks that are due on the given date.

        Syncs each task's last_completed from history before calling is_due()
        so the freshest completion data is always used. Tasks blocked by a pet
        health constraint are excluded even if they are due.
        """
        due: list[Task] = []
        for task in self.tasks:
            # Keep the task object in sync with the history record
            last = self.history.get_last_completed(task)
            if last is not None:
                task.last_completed = last

            if task.is_due(date) and self.constraint.check_pet_health_constraints(task):
                due.append(task)
        return due

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
        """Assign tasks to available time slots in two passes.

        Pass 1 — inflexible tasks (is_flexible=False, e.g. medications, appointments).
        Pass 2 — flexible tasks (is_flexible=True, e.g. walks, grooming).

        Each assignment is gate-checked via self.constraint before committing.
        Unplaceable tasks land in DailyPlan.unscheduled_tasks. Slots come from
        self.preferences.get_available_time_slots(date).
        """
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

        return plan

    def explain_decisions(self, plan: DailyPlan) -> str:
        """Return a natural-language explanation of every scheduling decision.

        This is the LLM hook point — replace the body with a Claude API call
        (using plan.get_summary() as context) for a richer explanation.
        """
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
