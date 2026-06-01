# Walkthrough: build a real course with Lunaris

A step-by-step run-through — from a cold machine to a finished, explorable course — with the
**exact output you should expect** at each step. Follow it top to bottom the first time.

---

## The topic we'll build: **Dijkstra's shortest-path algorithm**

We'll use **"Dijkstra's shortest-path algorithm"** as the example topic. Why this one:

- **It has a real prerequisite ladder**, so it shows off Lunaris's first correctness moat (the
  prerequisite graph — *never teach a concept before its prerequisite*). A good build will order
  concepts roughly: *graph* → *weighted edges* → *greedy method* + *priority queue* → *edge
  relaxation* → *Dijkstra's algorithm* as the goal node. If the agent tried to teach "relaxation"
  before "weighted graph," the moat would reorder it.
- **It's meaty enough to span several modules** (you'll typically see 3–5), so the lesson Reader,
  the Map view, and the per-lesson visuals all have something real to show.
- **One-line primer** (so you know what "good" looks like): Dijkstra's algorithm finds the
  shortest path from a start node to every other node in a graph with non-negative edge weights, by
  repeatedly expanding the closest not-yet-finalized node and *relaxing* its neighbours' tentative
  distances.

Anything else works too — the topic box hints `e.g. how a hash map works…`. Pick whatever you like;
the steps are identical.

---

## Step 0 — Pre-flight (2 minutes, do this once)

### 0a. Decide: real AI, or the free stub?

`make run` is **live-by-default** now. With a real `ANTHROPIC_API_KEY` in `.env` it runs the **real
deep-agent harness** (costs Claude tokens, ~2–4 min per build). With no key it falls back to the
**deterministic stub** (instant, free, but always returns the same fixed binary-search course — not
your topic).

For *this* walkthrough you want the real thing, so you need a working key.

### 0b. 🔴 Rotate your Anthropic key first

Your current key was pasted into a chat earlier — treat it as burned. Rotate it at
**console.anthropic.com → API Keys**, then put the new value in `.env`:

```bash
# edit the line in .env  (do NOT commit .env — it's gitignored)
ANTHROPIC_API_KEY=sk-ant-<your-new-key>
```

### 0c. Confirm what `make run` will do

```bash
grep -E '^ANTHROPIC_API_KEY=' .env | sed 's/=.*/=<set>/'
```

**Expect:** `ANTHROPIC_API_KEY=<set>` (and the value is *not* the `sk-ant-xxxx…` placeholder).
If it shows the placeholder or is missing, `make run` will silently use the stub.

> **Optional — confirm prerequisites are healthy:** `docker info >/dev/null && echo "docker ok"`
> should print `docker ok`. Docker Desktop must be running (Supabase runs inside it).

---

## Step 1 — Start the stack: `make run`

```bash
make run
```

This installs everything (idempotent) and brings up **Supabase + API + web**.

**Expect** (roughly — banners are styled in colour):

```
╶─ make setup ─ Setting up the Lunaris developer environment
  ✔ uv …    ✔ Python workspace …    ✔ web deps …    ✔ .env already exists

╶─ make start ─ Starting the Lunaris stack
  [1/3] supabase (Postgres + pgvector data layer)
      ✔ supabase start …      ✔ Supabase REST ready at http://127.0.0.1:54321/rest/v1/
  [2/3] api (FastAPI delivery service — uvicorn)
      ℹ pipeline mode: agent  (real Claude — the deep-agent harness)
      ✔ API ready at http://127.0.0.1:8000 (PID …)
  [3/3] web (Vite prerequisite-graph explorer)
      ✔ web dev server ready at http://localhost:5173 (PID …)

  Startup Summary
    supabase   running
    api        http://127.0.0.1:8000 (agent)
    web        http://localhost:5173

  Open http://localhost:5173 — enter a topic and watch Lunaris build the course.
  Logs: .run-state/*.log · tear down with 'make stop'.
```

**The one line to check:** `pipeline mode: agent  (real Claude …)`.
If you instead see **`pipeline mode: stub — no ANTHROPIC_API_KEY found …`**, stop here and fix
Step 0b — otherwise you'll build the canned binary-search course, not Dijkstra.

> If a port (8000/5173) is held, `make run` asks whether to stop the holder or relocate. The
> Supabase ports (54321-3) are fixed; if another stack holds them it'll prompt to stop it (your
> data is preserved).

**Sanity-check the API directly (new terminal):**

```bash
curl -s localhost:8000/api/healthz
```

**Expect:** `{"status":"ok"}`

---

## Step 2 — Open the studio and enter the topic

Open **http://localhost:5173** in a browser.

**Expect:** the Lunaris "Workstation" studio — a left sidebar (brand, **New course**, run history,
Settings) and a main canvas with a topic form:

- Eyebrow: **"Build a course"**, heading **"What do you want to learn?"**
- A text field (placeholder *"e.g. how a hash map works…"*)
- A **Generate course** button (disabled until you type something — it shows the hint
  *"Enter a topic to build a course."*)

Type:

```
Dijkstra's shortest-path algorithm
```

…and click **Generate course** (or press Enter).

> You can also set the key in the UI instead of `.env`: sidebar → **Settings** → paste the Anthropic
> key (write-only; it shows only set/unset + last-4). Then come back and build.

---

## Step 3 — Watch the live agent build it

The canvas switches to the **live transcript**. This is the real deep agent thinking out loud — not
a fake progress bar.

**Expect, in order (takes ~2–4 minutes on Tier-2):**

1. **A plan / todo list** appears and updates as steps complete.
2. **Reasoning** snippets (the model's short narration).
3. **Tool-call cards**, each with name + a result summary, in this order:
   - `extract_concepts` → "Extracted N concepts" (you'll see ~10–16 KCs — graph, weight, greedy,
     priority queue, relaxation, … , dijkstra).
   - `build_prerequisite_graph` → an **acyclic** graph; this is the moat enforcing teaching order.
   - `design_curriculum` → "Designed curriculum: M modules".
   - `task → module-author` → the author→verify→revise subagent writes + grounds each lesson
     (you'll see claim-verification beats: "Verified K claims: X supported, Y cut").
   - `finalize_course` → "Published" *or* "Needs review".
4. A coarse **stage rail** mirrors this: Mapping → Sequencing → Designing → Authoring → Verifying →
   Done.

When it finishes, the canvas hands off to the **result view**.

> ⚠️ **Expect status = "Needs review", and most/all claims "cut" — this is correct, not a failure.**
> Claim grounding needs a Voyage embeddings key + an ingested corpus. Without them the verifier
> *fails safe*: it cuts every claim rather than ship an unsupported one, so the publish gate withholds
> "Published". The course structure, lessons, ordering, and visuals are all still real and correct —
> only the green "supported-by-a-source" citations are absent. (To get real citations you need a paid
> Voyage tier + corpus ingestion; out of scope here.)

---

## Step 4 — Explore the finished course

The result view has a **Learn | Map** toggle.

### Learn (the reader)

**Expect:**

- A **module → lesson table of contents** on the left.
- A lesson pane with **Prev / Next** and "Lesson N of M".
- Each lesson shows the four **Merrill phases** (Activate / Demonstrate / Apply / Integrate) with
  plain-language cues.
- The module's **objectives** (Bloom-tagged) on its first lesson, and the module **assessment**
  (with an answer-reveal) on its last.
- **Branded visuals** on the Demonstrate phase — a flow / steps / comparison diagram drawn by the
  app (this is the P5 wiring; with no render toolchain you may instead see a labelled "Diagram
  source" block, which is the intended fallback).
- **Claims with their verification status** — here mostly "cut" (see the note above).
- A per-lesson **Regenerate lesson** button (re-authors just that lesson via the agent).

### Map (the prerequisite graph)

Flip to **Map**.

**Expect:** an interactive node-graph of the knowledge components, prerequisites flowing into the
**goal** node (`dijkstra…`), tier-coloured nodes, and a detail panel when you click a node
(prereqs / unlocks / covering modules / sources). Clicking **"Open lesson"** drills back into the
reader. **There should be no cycles and no edge pointing "backwards"** — that's the Failure-A moat,
visible.

---

## Step 5 — Verify it for real (optional, but satisfying)

You don't have to trust the UI. Two independent checks:

### 5a. Re-build over the API and grab the run id

```bash
curl -s -D - -o /tmp/course.json \
  -X POST localhost:8000/api/courses \
  -H 'content-type: application/json' \
  -d '{"topic":"Dijkstra'\''s shortest-path algorithm"}' | grep -i x-run-id
```

**Expect:** an `x-run-id: <hex>` header (this id threads every log line), and a full course-object
written to `/tmp/course.json`. (This is the synchronous build — it blocks ~2–4 min, then returns.)

### 5b. Score it against the definition of done

```bash
uv run lunaris-eval /tmp/course.json
```

**Expect:** a per-check report and an exit status. The **prerequisite-order** and **fit** checks
should **PASS** (the moats held on real model output). The **factuality** check reflects grounding —
with the stub retriever every claim is cut, which the checker treats as *no unsupported claim
shipped*, so the DoD can still report met. Exit `0` = DoD passed.

---

## Step 6 — Triangulate the logs (optional)

Every layer tags its logs with the same `run_id`. Using the id from Step 5a:

```bash
grep '"run_id":"<id>"' .run-state/api.log | head -40
```

**Expect:** a single ordered trail — `agent_course_run_started` → `prerequisite_graph_built` →
`authoring_loop_verified` → `agent_course_finalized` → `agent_course_run_completed` — all sharing
that one `run_id`. (And note: any secret-looking field is `***REDACTED***` — that's the P5 redaction
processor.)

---

## Step 7 — Shut down

```bash
make stop
```

**Expect:** a "Shutdown Summary" with `web stopped`, `api stopped`, `supabase stopped`. Your
Supabase **data is preserved** (volumes survive); `make run` brings it all back.

Verify nothing's left:

```bash
lsof -ti :8000 :5173 ; docker ps -q | wc -l
```

**Expect:** no output from `lsof` (ports free) and `0` running containers (if you have no other
Docker projects up).

---

## Quick reference

| Action | Command | Expect |
|---|---|---|
| Start everything (real agent) | `make run` | `pipeline mode: agent`, web on :5173 |
| Start everything (free/stub) | `LUNARIS_PIPELINE=stub make run` | `pipeline mode: stub`, fixed demo course |
| API health | `curl -s localhost:8000/api/healthz` | `{"status":"ok"}` |
| Build via API | `POST /api/courses {"topic":"…"}` | 201 + `X-Run-Id` header |
| Score a course | `uv run lunaris-eval <file.json>` | per-check report, exit 0 = DoD met |
| Stop everything | `make stop` | shutdown summary; data preserved |

## Troubleshooting

- **It built the binary-search course, not Dijkstra** → `make run` ran the stub. Your key is the
  placeholder/missing. Fix `.env` (Step 0b/0c) and re-run, or set the key in the UI Settings panel.
- **Status "Needs review" / all claims cut** → expected without a Voyage key + corpus (Step 3 note).
  The course is still correct; only source citations are absent.
- **Build is slow or 429s** → a full build is ~30–40 Claude calls; on lower tiers space out runs.
  You're on Tier-2 (1000 req/min), so this is usually fine.
- **Docker errors on start** → Docker Desktop isn't running. Start it, wait ~10s, `make run` again.
- **Port held** → answer the prompt to stop the holder or relocate; Supabase ports are fixed and
  will prompt to stop a conflicting stack (data preserved).

---

*This doc lives in `documentation/` and is currently uncommitted — keep it, edit it, or delete it as
you like.*
</content>
