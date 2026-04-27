# PawPal+

A smart pet care scheduling app that combines rule-based planning with an AI-powered agent and retrieval-augmented generation (RAG) to help busy pet owners stay on top of daily care tasks.

---

## Original Project

PawPal+ began as a Module 1–3 project for Codepath AI 110. The original goal was to build a Streamlit app that helps a pet owner plan and track daily care tasks — walks, feeding, medication, grooming, and vet appointments — across multiple pets. The system used a rule-based scheduler that prioritized tasks by urgency and health constraints, allocated them into time slots based on owner preferences, and detected scheduling conflicts automatically. It supported recurring tasks, task history, streak tracking, and pet health condition filtering, all backed by a clean class hierarchy in Python.

---

## Title and Summary

**PawPal+** turns a static daily task list into an intelligently reasoned pet care plan. The app generates a schedule using a constraint-aware rule-based planner, then passes that plan to a Claude-powered AI agent. The agent retrieves relevant pet care guidelines from a local knowledge base (RAG), and produces a grounded, natural-language explanation of the schedule tailored to each pet's species, age, and health conditions.

**Why it matters:** Generic scheduling apps don't know that an arthritic dog needs shorter walks, or that cardiac medication must be given exactly 12 hours apart. PawPal+ connects scheduling logic to real care knowledge, so the owner doesn't just see *what* to do — they understand *why*.

---

## Architecture Overview

See [enhanced_class_diagram.md](enhanced_class_diagram.md) for the full Mermaid diagram.

The system has five layers:

| Layer | Role |
|---|---|
| **Streamlit UI** (`app.py`) | Owner enters pet/task info, triggers schedule generation, reads the AI explanation |
| **Agent Loop** (`ai_agent.py` — `PawPalAgent`) | Generates the plan via the existing Planner, then drives a Claude tool-use loop to retrieve context and produce a grounded explanation |
| **RAG Retriever** (`ai_agent.py` — `PawPalRAG`) | Keyword-scores 7 pet-care markdown documents and returns the most relevant content for a given query |
| **Core System** (`pawpal_system.py`) | Rule-based `Planner`, `Constraint` checker, `DailyPlan` with conflict detection, `TaskHistory` with streak tracking |
| **Knowledge Base** (`knowledge/`) | 7 markdown documents covering arthritis, heart disease, obesity, post-surgery recovery, dog care, cat care, and medication guidelines |

**Data flow:** Owner input → Planner generates plan → Agent reviews plan and calls `retrieve_pet_care_info` tool as needed → RAG returns relevant documents → Claude produces grounded explanation → Owner sees schedule + explanation + agent trace.

The human is in the loop at two points: reviewing the final plan before acting on it, and marking tasks complete (which feeds back into `TaskHistory` for future planning).

---

## Setup Instructions

**Requirements:** Python 3.10+, an Anthropic API key ([console.anthropic.com](https://console.anthropic.com))

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd applied-ai-system-final

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python -m streamlit run app.py
```

Once the app opens in your browser, paste your Anthropic API key into the **AI Settings** sidebar. The app works without a key (rule-based fallback), but the AI explanation and RAG lookups require one.

> **Optional:** Set `ANTHROPIC_API_KEY` as an environment variable to skip pasting it each session:
> ```bash
> export ANTHROPIC_API_KEY="sk-ant-..."
> python -m streamlit run app.py
> ```

---

## Sample Interactions

### Example 1 — Dog with arthritis

**Input:**
- Pet: Rex, dog, age 4, health condition: `arthritis`
- Auto-generated tasks: Feed Rex (twice daily), Walk Rex (daily), Medication for Rex (daily)

**Agent trace:**
```
Planner generated 3 scheduled task(s), 0 unscheduled, 0 conflict(s) detected.
RAG lookup → "arthritis dog exercise restrictions"
RAG lookup → "medication timing consistency"
Agent produced final explanation after 2 turn(s).
```

**AI Explanation (excerpt):**
> Rex's medication has been scheduled first thing in the morning — this is intentional. For dogs with arthritis, NSAIDs like carprofen need to be given consistently and with food to maintain stable therapeutic levels and reduce GI irritation. Skipping or delaying this task has a real impact on pain management.
>
> The walk has been kept short and placed mid-morning when joints are typically less stiff after waking. Based on arthritis guidelines, high-impact or prolonged walks should be avoided — if Rex shows any limping or reluctance after today's walk, consider shortening it tomorrow.

---

### Example 2 — Healthy cat, no conditions

**Input:**
- Pet: Luna, cat, age 2, no health conditions
- Auto-generated tasks: Feed Luna (twice daily)
- Manual task: Groom Luna (weekly, flexible)

**Agent trace:**
```
Planner generated 2 scheduled task(s), 0 unscheduled, 0 conflict(s) detected.
RAG lookup → "cat feeding schedule"
RAG lookup → "cat grooming"
Agent produced final explanation after 2 turn(s).
```

**AI Explanation (excerpt):**
> Luna's feeding tasks are locked in at morning and evening — cats do best with consistent meal times rather than free feeding, especially for weight management. Fresh water should be refreshed at both feeding times.
>
> Grooming is scheduled for this afternoon. For a short-haired cat like Luna, a weekly brush is enough to manage shedding and give you a chance to check for any skin issues early. It's marked flexible, so if today gets busy it can shift — just don't skip more than a week or two in a row.

---

### Example 3 — Scheduling conflict detected

**Input:**
- Pet: Max, dog, age 6, health condition: `heart_disease`
- Tasks: Feed Max, Walk Max (60 min, inflexible), Medication for Max — all manually set to overlap in the morning window

**Agent trace:**
```
Planner generated 2 scheduled task(s), 1 unscheduled, 1 conflict(s) detected.
RAG lookup → "heart disease dog exercise"
RAG lookup → "cardiac medication timing"
Agent produced final explanation after 3 turn(s).
```

**AI Explanation (excerpt):**
> There is a scheduling conflict between the walk and the morning feeding — both were placed in the 7:00–8:00 window. This needs to be resolved before following this plan.
>
> More importantly: for a dog with heart disease, a 60-minute walk is too strenuous. Cardiac guidelines recommend limiting outings to 5–10 minutes for bathroom needs only. I'd suggest reducing the walk duration and marking it flexible so it can be trimmed on harder days.
>
> Max's cardiac medication must be given on a strict 12-hour schedule — this is the highest priority task in the plan and should not be moved or skipped under any circumstances.

---

## Design Decisions

**Why RAG over a fine-tuned model?**
A fine-tuned model would require labeled training data and infrastructure that doesn't exist at this project's scale. RAG achieves the same goal — grounding the AI's output in real pet-care knowledge — with a simple local knowledge base and no training cost. It's also easier to update: adding a new condition means adding one markdown file.

**Why keyword scoring instead of embeddings?**
Embedding-based retrieval (e.g., `sentence-transformers`) is more semantically powerful but adds a heavy dependency and latency. For 7 short documents with clear topical names, term-overlap scoring is fast, transparent, and accurate enough. The tradeoff is that synonyms ("cardiac" vs. "heart") can miss — mitigated by writing documents with varied terminology.

**Why Claude Haiku?**
The task — review a schedule, look up a doc, write a short explanation — doesn't require deep reasoning. Haiku is significantly cheaper and faster than Sonnet or Opus for this use case, making it practical to call on every schedule generation without cost concern.

**Why keep the rule-based planner?**
The existing Planner is fast, deterministic, and testable. The AI agent doesn't replace it — it wraps it. The planner handles the hard constraint logic (slot allocation, health restrictions, conflict detection); the agent handles the soft, language-heavy part (explanation, nuance, owner communication). This separation means the scheduling logic can be tested independently of the AI layer.

**Graceful fallback:**
If no API key is provided, the app falls back to the original rule-based `explain_decisions()` output. This keeps the app fully functional without the AI layer and makes it easier to demo in environments without API access.

---

## Testing Summary

Run the test suite with:
```bash
python -m pytest
```

**What the tests cover:**
- Basic task behavior: marking complete, timestamp updates, history logging
- Planner task management: adding tasks, pet associations
- Scheduling: chronological ordering, no unintended overlaps, two-pass allocation (inflexible before flexible)
- Recurrence: daily and weekly tasks generate correct successors on completion
- Conflict detection: overlapping slots are flagged, back-to-back slots are not

**What worked well:**
The rule-based scheduling logic is reliable and well-covered by tests. The two-pass allocator (inflexible tasks first) consistently produces sensible plans, and conflict detection catches edge cases without crashing the app.

**What didn't / limitations:**
- The keyword retriever can miss relevant documents if the query uses different terminology than the document (e.g., "cardiac" doesn't score `heart_disease.md` as highly as "heart"). A future improvement would be embedding-based retrieval.
- The agent explanation is not tested automatically — output quality is evaluated manually. Adding an LLM-as-judge evaluation layer would make this more rigorous.
- The scheduler is greedy (first-fit), so it doesn't always find the globally optimal arrangement when the schedule is dense.

**What I learned:**
Separating the deterministic logic from the AI layer made both easier to build and debug. The tests give confidence in the scheduler, which lets you trust the plan the agent is explaining. Without that foundation, it would be hard to know whether a bad explanation was a retrieval problem, a prompt problem, or a scheduling problem.

---

## Reflection

Building PawPal+ with an AI layer taught me that the most valuable thing an LLM can do in a real application is often not make decisions — it's *explain* them. The rule-based planner already makes the scheduling decisions; Claude's job is to translate those decisions into something the owner can understand and act on. That's a much more reliable and testable use of an LLM than asking it to do the planning itself.

RAG reinforced how much grounding matters. Without the knowledge base, Claude's explanations were generic ("this task has high priority"). With it, they referenced specific care guidelines tied to the pet's actual health conditions. The difference in output quality was immediate and obvious — and it came from 7 short markdown files, not a complex pipeline.

The biggest practical lesson was about failure modes: LLMs ask clarifying questions when they don't have enough context. The first version of the agent didn't pass pet details to Claude, so it responded by asking what species the pet was. The fix was simple (add pet context to the prompt), but it was a good reminder that prompt design is as important as model choice. Getting the input right matters more than picking the fanciest model.

---

## Screenshot

<a href="image.png" target="_blank"><img src='image.png' title='PawPal App' width='' alt='PawPal App' class='center-block' /></a>
