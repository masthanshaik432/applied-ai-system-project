# PawPal+ — Enhanced System Architecture

The diagram below shows how the AI enhancements (Agentic Workflow + RAG) integrate with the existing scheduling system.

```mermaid
flowchart TD
    subgraph UI["🖥️ Streamlit UI  •  app.py"]
        U1[Owner enters\npet & task info]
        U2[Trigger: Generate Schedule]
        U3[View plan,\nexplanations & conflicts]
    end

    subgraph AGENT["🤖 Agent Loop  •  Planner"]
        AG1[Generate initial plan\ngenerate_daily_plan]
        AG2{Validate\nconstraints & conflicts}
        AG3[Revise plan using\nretrieved context]
        AG4[Build grounded\nexplanation\nexplain_decisions]
    end

    subgraph RAG["📚 RAG  •  Retriever"]
        R1[(Pet Care\nKnowledge Base\nbreed guides · health\ncondition notes · med timing)]
        R2[Vector / keyword\nlookup]
    end

    subgraph CORE["⚙️ Core System  •  pawpal_system.py"]
        C1[Planner\nallocate_tasks_to_slots]
        C2[Constraint Checker\ncheck_pet_health_constraints]
        C3[DailyPlan\ndetect_conflicts]
        C4[TaskHistory\nstreak · completion rate]
    end

    subgraph HUMAN["👤 Human in the Loop"]
        H1[Owner reviews\nschedule & reasoning]
        H2[Mark tasks complete\nor adjust priorities]
    end

    subgraph TESTS["🧪 Test Suite  •  pytest"]
        T1[test_pawpal.py\nscheduling · recurrence\nconflicts · constraints]
    end

    U1 -->|pet + task data| AG1
    U2 -->|trigger| AG1
    AG1 --> C1
    C1 --> C3
    C2 --> AG2
    C3 --> AG2
    AG2 -->|violations found| R2
    R2 <-->|query / results| R1
    R2 -->|retrieved context| AG3
    AG3 -->|revised tasks| C1
    AG2 -->|plan is valid| AG4
    AG4 --> U3
    U3 --> H1
    H1 --> H2
    H2 -->|completion logged| C4
    C4 -->|informs due-task filter| AG1
    TESTS -. verifies .-> CORE
    TESTS -. verifies .-> AGENT
```

## Flow summary

| Stage | What happens |
|---|---|
| **Input** | Owner adds pets and tasks via the Streamlit UI |
| **Agent loop** | Generates a plan, validates it, and iterates until constraints are satisfied |
| **RAG lookup** | When a violation is found, the retriever pulls relevant pet-care context from the knowledge base to inform the revision |
| **Output** | A conflict-free, grounded daily schedule with natural-language explanations |
| **Human review** | Owner reads the plan, marks tasks complete; completions feed back into `TaskHistory` |
| **Testing** | `pytest` suite independently verifies the core scheduling logic and agent behavior |
