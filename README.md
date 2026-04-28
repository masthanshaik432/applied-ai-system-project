# PawPal+

A smart pet care scheduling app that combines rule-based planning with an AI-powered agent and retrieval-augmented generation (RAG) to help busy pet owners stay on top of daily care tasks.

Demo Video Loom Link: https://www.loom.com/share/31da675b876945a9af9f2675dd8b743c

---

## Original Project

PawPal+ started as a project for pet management. The idea was to build a simple Streamlit app that helps pet owners organize and keep up with daily care tasks like walks, feeding, medication, grooming, and vet visits for multiple pets.
The app uses a rule-based system to sort tasks by urgency and health needs, then fits them into a schedule based on the owner’s preferences. It can spot scheduling conflicts automatically and supports recurring tasks, task history, streak tracking, and filtering by a pet’s health conditions. Everything is structured with a clear class design in Python to keep the system organized and easy to extend.

---

## Title and Summary

**PawPal+** turns a static daily task list into a reasoned pet care plan. The app generates a schedule using a "constraint-aware rule-based" planner, then passes that plan to a Claude-powered AI agent. The agent retrieves relevant pet care guidelines from a local knowledge base (RAG), and produces an explanation of the schedule tailored to each pet's species, age, and health conditions.

**Why it matters:** Most scheduling apps don’t understand the details that matter for pet care, whether it be giving shorter walks to a dog with arthritis or making sure heart medication is spaced exactly 12 hours apart. PawPal+ ties scheduling logic to real care guidance, so owners don’t just see what to do, but they also understand why it matters.

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

One decision I made was choosing Retrieval Augmented Generation over a fine tuned model. There would be a lot of labelled data and infrastructure required to use a fine-tuned model as opposed to using RAG. RAG is able to get the specific data knowledge and apply it in its own way to make meaningful insights.

I specifically chose Claude Haiku as the AI model since the task at hand is quite simple in nature and does not need deep reasoning. The AI agent remains as a wrapper rather than an entire replacement for the planner and lets the planner handle the hard logic (scheduling, restriction consideration), whereas the agent handles the language heavy parts such as the explaination. From a decoupling standpoint, it lets the scheduling happen independently, and if the API key is not provided, then the app falls to the rule-based output.

---

## Reliability Mechanism

PawPal+ includes two reliability layers: **output guardrails** built into the agent, and an **evaluation script** that tests both layers without requiring an API key.

### Output guardrails

After Claude generates an explanation, `PawPalAgent._apply_guardrails()` runs four checks before the result is shown to the owner:

| Guardrail | What it checks | On failure |
|---|---|---|
| Not empty | Explanation is non-empty | Flags + falls back to rule-based output |
| Minimum length | At least 50 words | Flags issue in trace |
| Pet name present | At least one pet's name appears | Flags issue in trace |
| No refusal pattern | Doesn't contain phrases like "I don't have enough information" or "could you provide" | Flags + falls back to rule-based output |

If any guardrail triggers, the issue appears in the **"View agent reasoning trace"** expander in the UI. Critical failures (empty output or refusals) automatically swap in the rule-based `explain_decisions()` output so the owner always sees a usable result.

### Evaluation script

`eval_agent.py` runs 14 checks across two sections and produces a pass/fail report. **No API key is needed** for sections 1 and 2.

```bash
python eval_agent.py
```

**Example output:**

```
=== Section 1: RAG Retrieval Quality ===

  [PASS] RAG: 'arthritis dog exercise' → contains 'arthritis'
  [PASS] RAG: 'cat feeding schedule' → contains 'cat'
  [PASS] RAG: 'heart disease medication' → contains 'heart'
  [PASS] RAG: 'post surgery recovery' → contains 'surgery'
  [PASS] RAG: 'obesity weight management' → contains 'obesity'
  [PASS] RAG: 'medication twice daily' → contains 'medication'
  [PASS] RAG: top_k=2 returns at most 2 docs
  [PASS] RAG: nonsense query returns empty list
  [PASS] RAG: all 7 knowledge docs loaded

=== Section 2: Output Guardrail Checks ===

  [PASS] Guardrail: empty explanation is flagged
         → ['FAIL: explanation is empty.', 'FAIL: explanation too short (0 words; minimum 50).']
  [PASS] Guardrail: too-short explanation is flagged
         → ['FAIL: explanation too short (4 words; minimum 50).']
  [PASS] Guardrail: explanation missing pet name is flagged
         → ['FAIL: explanation does not reference any pet by name.']
  [PASS] Guardrail: refusal/clarifying-question pattern is flagged
         → ['FAIL: explanation appears to be a refusal or is asking for missing context.']
  [PASS] Guardrail: good explanation passes all checks
         → []

  14/14 checks passed
```

Section 3 (live pipeline smoke test) runs automatically when `ANTHROPIC_API_KEY` is set and verifies that a real Claude response passes all four guardrails end-to-end.

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

## Responsible AI

### Limitations and biases

The knowledge base is the most significant source of bias. The 7 documents were written using ChatGPT and reflect general Western veterinary guidelines. They don't account for things like breed differences or differences in available medications. If a user's pet has a condition not covered in the knowledge base, the retriever returns nothing relevant and Claude falls back on its training data, which has no transparency.

### Misuse potential and mitigations

The most likely misuse is an owner treating the AI’s explanation as a replacement for actual veterinary advice. The app can explain why something like medication timing matters, but it doesn’t know a pet’s exact diagnosis, current dosage, or any recent changes from the vet. That creates a real risk where someone could follow the schedule and overlook an updated instruction.
To reduce that risk, the app should include a clear, persistent disclaimer that its explanations are general guidance, not medical advice. It would also help to flag when a pet’s condition doesn’t have a matching document in the knowledge base, so the user knows the explanation may be incomplete or missing important context.

### Collaboration with AI during this project

AI assistance was used throughout the build, most heavily during the agent architecture design and the knowledge base content. 
When introducing RAG, AI was able to generate documentation such as the arthiritis.md and obesity.md, and connect that with the LLM. It was so nice to see that there was actual proof that the AI features in the PawPal were using the documents when possible.
The boilerplate code felt a little off at times. For example, I was not a fan of how it generated default values for pet names, ages, and task times. I removed these default generated values on my own so that it becomes more obvious that users have to plant them themselves.

---

## Reflection

Building PawPal+ with an AI layer taught me that the most valuable thing an LLM can do is explain the decision making really well. The rule based planner already makes the scheduling decisions, and Claude's job is to translate those decisions into something the owner can understand and act on. That's a much more reliable and testable use of an LLM than asking it to do the planning itself.

RAG reinforced how much grounding matters. Without the knowledge base, Claude's explanations were generic ("this task has high priority"). With the document based specifics, they referenced specific care guidelines tied to the pet's actual health conditions. The difference in output quality was pretty significant.

---

## Screenshot

<a href="image.png" target="_blank"><img src='image.png' title='PawPal App' width='' alt='PawPal App' class='center-block' /></a>
