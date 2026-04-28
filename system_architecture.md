# PawPal+ System Architecture

## Component & Layer Diagram

```mermaid
graph TD
    subgraph UI["🖥️ Presentation Layer — app.py"]
        UI1[Add Pet Form]
        UI2[Add Task Form]
        UI3[Generate Schedule Button]
        UI4[Schedule Table]
        UI5[AI Explanation Panel]
        UI6[Confidence Badge]
        UI7[Agent Trace Expander]
    end

    subgraph AI["🤖 AI Layer — ai_agent.py"]
        AG[PawPalAgent\n─────────────\n+ generate_and_explain\n+ confidence: dict\n+ trace: list]
        RAG[PawPalRAG\n─────────────\n+ retrieve\n+ retrieve_as_text\n+ documents: dict]
        CLAUDE["Claude Haiku\nclaude-haiku-4-5\n─────────────\ntool: retrieve_pet_care_info\ntool: report_confidence"]
    end

    subgraph KB["📚 Knowledge Base — knowledge/"]
        K1[arthritis.md]
        K2[heart_disease.md]
        K3[obesity.md]
        K4[post_surgery.md]
        K5[dog_care.md]
        K6[cat_care.md]
        K7[medication_guidelines.md]
    end

    subgraph CORE["⚙️ Core Layer — pawpal_system.py"]
        PL[Planner\n─────────────\n+ generate_daily_plan\n+ filter_tasks\n+ complete_task\n+ prioritize_tasks]
        DP[DailyPlan\n─────────────\n+ detect_conflicts\n+ explain_plan\n+ get_summary]
        CN[Constraint\n─────────────\n+ check_time_constraint\n+ check_pet_health_constraints\n+ validate_schedule]
        TS[TimeSlot\n─────────────\n+ duration\n+ can_fit\n+ split]
    end

    subgraph DATA["🗄️ Data Layer — pawpal_system.py"]
        PET[Pet\n─────────────\n+ name, species, age\n+ health_conditions\n+ get_daily_needs\n+ special_care_needed]
        TASK[Task\n─────────────\n+ name, type, duration\n+ priority, frequency\n+ mark_complete\n+ next_occurrence\n+ get_priority_score]
        HIST[TaskHistory\n─────────────\n+ log_completion\n+ get_completion_rate\n+ streak]
        PREF[OwnerPreferences\n─────────────\n+ max_daily_time\n+ preferred_times\n+ get_available_time_slots]
    end

    subgraph TEST["🧪 Test Layer — tests/test_pawpal.py"]
        T1[Scheduling Tests]
        T2[Recurrence Tests]
        T3[Conflict Detection Tests]
        T4[RAG Retriever Tests]
    end

    %% UI → AI
    UI3 -->|trigger| AG
    AG -->|plan + violations| CLAUDE
    CLAUDE -->|tool call| RAG
    RAG <-->|keyword search| KB
    RAG -->|retrieved docs| CLAUDE
    CLAUDE -->|report_confidence| AG
    CLAUDE -->|explanation text| AG
    AG -->|DailyPlan| UI4
    AG -->|explanation| UI5
    AG -->|confidence| UI6
    AG -->|trace| UI7

    %% UI → Core
    UI1 -->|Pet object| PET
    UI2 -->|Task object| TASK

    %% AI → Core
    AG -->|calls| PL

    %% Core internals
    PL -->|produces| DP
    PL -->|uses| CN
    PL -->|uses| PREF
    PL -->|reads/writes| HIST
    DP -->|contains| TS
    CN -->|checks| PET

    %% Core → Data
    PL -->|owns| TASK
    PL -->|owns| PET
    TASK -->|belongs to| PET

    %% Tests → layers
    T1 & T2 & T3 -. verify .-> CORE
    T4 -. verify .-> AI
```

---

## Layer Responsibilities

| Layer | Files | Purpose |
|---|---|---|
| **Presentation** | `app.py` | Streamlit UI — all user input and output |
| **AI** | `ai_agent.py` | Claude agent loop, RAG retriever, confidence scoring |
| **Knowledge Base** | `knowledge/*.md` | Static pet-care documents searched by RAG |
| **Core** | `pawpal_system.py` | Rule-based scheduling, constraint checking, conflict detection |
| **Data** | `pawpal_system.py` | Domain objects: Pet, Task, TaskHistory, OwnerPreferences |
| **Test** | `tests/test_pawpal.py` | Automated verification of Core and AI layers |

---

## Key Design Boundaries

- The **AI layer never mutates** the Core or Data layers — it reads the plan and produces text.
- The **Core layer has no knowledge of Claude** — it is fully testable without an API key.
- The **RAG retriever is stateless** — it loads documents once at startup and only reads from that point on.
- The **UI is the only entry point** for user data — Pet and Task objects are created there and passed down.
