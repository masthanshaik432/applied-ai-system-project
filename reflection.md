# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
- What classes did you include, and what responsibilities did you assign to each?

Three core actions that a user should be able to perform
1) add a pet, including info such as diet and meds
2) view a daily schedule around the pet
3) obtain a reasoning for the given schedule

Here are objects that I have brainstormed along with their attributes and functions:
Class Pet:
attributes
- name: string
- species: string
- age: int
- health_conditions: list[string]
- height: float
- weight: float
methods
- get_daily_needs()
- special_care_needed()

Class Task:
attributes
- name: string
- task_type: string
- duration: int
- priority: int (1–5)
- frequency: string
- pet: Pet
- is_flexible: bool
- last_completed: datetime
methods
- is_due(date)
- get_priority_score()
- fits_time_slot(slot)

Class TimeSlot:
attributes
- start_time: datetime
- end_time: datetime
- available: bool
methods
- duration()
- can_fit(task)
- split(task_duration)

Class OwnerPreferences
attributes
- max_daily_time: int
- preferred_times: dict
- task_priorities_override: dict
- break_duration: int
methods
- adjust_task_priority(task)
- is_preferred_time(task, slot)
- get_available_time_slots()

Class DailyPlan
attributes
- date: datetime
- scheduled_tasks: list[(Task, TimeSlot)]
- unscheduled_tasks: list[Task]
- total_time: int
methods
- add_task(task, slot)
- calculate_total_time()
- get_summary()
- explain_plan()

Class Planner
attributes
- tasks: list[Task]
- pets: list[Pet]
- preferences: OwnerPreferences
- time_slots: list[TimeSlot]
methods
- filter_due_tasks(date)
- prioritize_tasks(tasks)
- allocate_tasks_to_slots(tasks)
- generate_daily_plan(date)
- explain_decisions(plan)

Class TaskHistory
attributes
- completed_tasks: list[(Task, datetime)]
methods
- log_completion(task)
- get_last_completed(task)
- get_completion_rate(task)

Class Constraint
attributes
- rules: list
methods
- check_time_constraint(task, slot)
- check_priority_constraint(task)
- check_pet_health_constraints(task)
- validate_schedule(plan)


**b. Design changes**

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

After creating the skeleton, I asked AI to review and look for potential setbacks. AI gave quite a few change suggestions (9 in total) and the below are the changes I made

Change 1: Planner now owns TaskHistory and Constraint
Planner.__init__ now takes history and constraint, and time_slots was removed. Slots are pulled from preferences.get_available_time_slots() instead.
Before this, the planner didn’t actually know when tasks were last completed, so “due” logic was guessy. It also wasn’t enforcing any rules when placing tasks, which meant invalid schedules could slip through.

Change 4: Plan is validated before returning
generate_daily_plan() now calls self.constraint.validate_schedule() at the end.
Previously, validation existed but wasn’t part of the normal flow, so bad schedules could make it all the way to the UI without being caught.

Change 7: Two-pass task allocation
Scheduling now happens in two passes:
-Inflexible tasks first (like meds or appointments)
-Flexible tasks after
The old single-pass approach could fill good time slots with low-priority tasks and leave important ones unscheduled.

Change 8: Completion rate now supports time windows
get_completion_rate() now takes a since parameter.
Without it, stats were based on all-time history, which made them misleading—especially for new or recently resumed tasks.

Change 9: total_time is now computed, not stored
Removed the stored total_time field and replaced it with a @property.
Before, it could easily get out of sync depending on how tasks were added. Now it’s always accurate since it’s calculated from the current schedule.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
