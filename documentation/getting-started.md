# Getting started: build your first course

A step-by-step run-through — from a cold machine to a finished, explorable course — with the
**output you should expect** at each step. Follow it top to bottom the first time.

---

## The topic we'll build: Dijkstra's shortest-path algorithm

We'll use **"Dijkstra's shortest-path algorithm"** as the example. Why this one:

- **It has a real prerequisite ladder**, so it shows off Lunaris's first correctness guarantee — the
  prerequisite graph that never teaches a concept before its prerequisite. A good build orders
  concepts roughly: *graph* → *weighted edges* → *greedy method* + *priority queue* → *edge
  relaxation* → *Dijkstra's algorithm* as the goal. If the agent tried to teach "relaxation" before
  "weighted graph," the ordering step would correct it.
- **It's meaty enough to span several modules** (typically 3–5), so the lesson reader, the map view,
  and the per-lesson visuals all have something real to show.
- **One-line primer** (so you know what "good" looks like): Dijkstra's algorithm finds the shortest
  path from a start node to every other node in a graph with non-negative edge weights, by repeatedly
  expanding the closest not-yet-finalized node and *relaxing* its neighbours' tentative distances.

Anything else works too — the topic box hints `e.g. how a hash map works…`. Pick whatever you like;
the steps are identical.

---

## Step 0 — Pre-flight (2 minutes, do this once)

### 0a. Decide: real AI, or the free stub?

`make run` is **live by default**. With an `ANTHROPIC_API_KEY` set in `.env` it runs the **real
deep-agent harness** (uses Claude tokens, ~2–4 min per build). With no key it falls back to the
**deterministic stub** — instant and free, but it always returns the same fixed binary-search course,
not your topic.

For this walkthrough you want the real thing, so you'll need a working key.

### 0b. Set your Anthropic key

Create an API key in the [Anthropic Console](https://console.anthropic.com) (**Settings → API
Keys**), then add it to `.env`:

```bash
# edit this line in .env  (.env is gitignored — never commit it)
ANTHROPIC_API_KEY=sk-ant-...
```

### 0c. Confirm what `make run` will do

```bash
grep -E '^ANTHROPIC_API_KEY=' .env | sed 's/=.*/=<set>/'
```

**Expect:** `ANTHROPIC_API_KEY=<set>` (and the value is *not* the `sk-ant-xxxx…` placeholder from
`.env.sample`). If it shows the placeholder or is missing, `make run` will silently use the stub.

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
> Supabase ports (54321–3) are fixed; if another stack holds them it'll prompt to stop it (your
> data is preserved).

**Sanity-check the API directly (new terminal):**

```bash
curl -s localhost:8000/api/healthz
```

**Expect:** `{"status":"ok"}`

---

## Step 2 — Open the studio and enter the topic

Open **http://localhost:5173** in a browser.

**Expect:** the Lunaris studio — a left sidebar (brand, **New course**, run history, Settings) and a
main canvas with a topic form:

- Eyebrow **"Build a course"**, heading **"What do you want to learn?"**
- A text field (placeholder *"e.g. how a hash map works…"*)
- A **Generate course** button (disabled until you type something — it shows the hint *"Enter a topic
  to build a course."*)

Type:

```
Dijkstra's shortest-path algorithm
```

…and click **Generate course** (or press Enter).

> **Optional — "Personalize before building…"** Under the field is an opt-in link. Click it (with a
> topic entered) and Lunaris first *interprets* your goal and shows a short confirm panel — your
> level, what you already know, the depth and writing style you want — each pre-picked to its best
> guess. Adjust anything, then **Build course**; your answers steer what's taught (skip what you
> know) and how it's written. Skipping it (just **Generate course**) uses the inference as-is. See
> [relevance.md](relevance.md) for how those answers flow through the build.

> You can also set the key in the UI instead of `.env`: sidebar → **Settings** → paste the Anthropic
> key (write-only; it shows only set/unset + last-4). Then come back and build.

---

## Step 3 — Watch the live agent build it

The canvas switches to the **live transcript**. This is the real agent thinking out loud — not a
fake progress bar.

**Expect, in order (takes ~2–4 minutes):**

1. **A plan / todo list** appears and updates as steps complete.
2. **Reasoning** snippets (the model's short narration).
3. **Tool-call cards**, each with a name and a result summary, in this order:
   - `interpret_request` → a **brief** card (subject / goal / level / assumed prior) — Lunaris reading
     the request as a goal before building anything.
   - `research_standard` → grounds a named standard in its real competencies **(only with a
     `SEARCH_API_KEY`; otherwise this shows `unavailable` and the build continues)**.
   - `model_learner` → the inferred **frontier** (the foundations to skip). For a level-neutral topic
     like Dijkstra it may be small or empty; for a request like *"reach CLB 10"* it's the whole
     beginner ladder.
   - `extract_concepts` → "Extracted N concepts", **scoped to the gap** (you'll see ~10–16 knowledge
     components for Dijkstra — graph, weight, greedy, priority queue, relaxation, …, dijkstra).
   - `build_prerequisite_graph` → an **acyclic** graph; this is the guarantee that enforces teaching
     order.
   - `design_curriculum` → "Designed curriculum: M modules" (mapped to competencies where researched).
   - `task → module-author` → the author → verify → revise subagent writes and grounds each lesson
     (you'll see claim-verification beats: "Verified K claims: X supported, Y cut").
   - `curate_resources` → vetted per-lesson external resources **(only with a `SEARCH_API_KEY`;
     otherwise no resources are attached — the verified lesson is still the spine)**.
   - `finalize_course` → "Published" *or* "Needs review".
4. A coarse **stage rail** mirrors this: Brief → Research → Learner → Mapping → Sequencing →
   Designing → Authoring → Verifying → Resources → Done.

When it finishes, the canvas hands off to the **result view**.

> ⚠️ **On a first run you'll likely see status = "Needs review", with most or all claims "cut" — this
> is correct, not a failure.** Claim grounding verifies each sentence against a *corpus* of evidence;
> with an empty corpus (and no embeddings key) the verifier *fails safe* — it cuts every claim rather
> than ship an unsupported one, so the publish gate withholds "Published". The structure, lessons,
> ordering, and visuals are all still real and correct — only the green "supported-by-a-source"
> citations are absent. **[Step 5](#step-5--fill-the-corpus-so-citations-go-green) shows how to fill
> the corpus so those citations go green** (it needs an embeddings key + Supabase).

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
  app (with no render toolchain you may instead see a labelled "Diagram source" block, which is the
  intended fallback).
- **Claims with their verification status** — mostly "cut" until you ground the course
  ([Step 5](#step-5--fill-the-corpus-so-citations-go-green)); "supported" claims carry their source
  and its trust tier.
- A per-lesson **Regenerate lesson** button (re-authors just that lesson via the agent).

### Map (the prerequisite graph)

Flip to **Map**.

**Expect:** an interactive node-graph of the knowledge components, prerequisites flowing into the
**goal** node (`dijkstra…`), tier-coloured nodes, and a detail panel when you click a node (prereqs /
unlocks / covering modules / sources). Clicking **"Open lesson"** drills back into the reader.
**There should be no cycles and no edge pointing "backwards"** — that's the prerequisite-ordering
guarantee, made visible.

---

## Step 5 — Fill the corpus so citations go green

The verifier cuts claims it can't ground because the corpus is *empty* — so fill it, re-ground, and
watch the citations turn green. There are **three ways** evidence enters the corpus (all write the
same trust-graded corpus; the full model is in [grounding.md](grounding.md)). You'll need an
embeddings key + Supabase for any of them to persist — set `EMBEDDINGS_API_KEY` (Voyage) in `.env` or
the Settings panel (note: Voyage's free tier is 3 requests/minute — fine for a small manual upload,
too slow for a whole auto-discovered corpus; a paid tier is needed for a full run).

### 5a. Manual — upload your own trusted sources (the Corpus tab)

Open a finished course and switch the canvas to the **Corpus** tab (the `Learn | Map | Build | Corpus`
toggle). Add evidence three ways — **Paste** notes, give a **URL**, or upload a **File** (PDF / DOCX /
MD / TXT). Each source is classified **vouched** (you chose it), deduped, embedded, and stored for
*this* course. Then click **Re-ground course** and reopen **Learn**:

**Expect:** the sources you added listed with their trust tier, and — for claims your evidence
actually supports — citations now showing **"supported"** with the source, instead of "cut".

> Operator shortcut: `make ingest DIR=./my-notes COURSE=<course-id>` ingests a whole folder.

### 5b. Auto — let the system find its own evidence

On the topic form, the **search depth** control (`Standard` / `Thorough`) governs auto-discovery:
with a `SEARCH_API_KEY` set, the agent searches the web, fetches and extracts pages, scores each for
trust, and ingests the ones that clear the bar — *before* it verifies claims. Watch it happen live in
the **Build** canvas: a streaming source-vetting table shows each domain, its tier + credibility, and
a ✓/✕ verdict with a one-line reason. `Thorough` widens the search budget (and cost) to corroborate
more concepts across more domains.

**Expect:** with a search key, several claims ship **supported** with real citations on the first
build — no manual upload. Without a search key the table shows the step was stubbed and the build
continues ungrounded.

### 5c. Seed — reuse what the build already read (near-free)

If a `SEARCH_API_KEY` is set, the **research** stage already fetched and vetted authoritative pages to
ground the brief. Seed mode carries that text into the corpus automatically — no second fetch, **no
extra search key** — so the build's claims verify against the very pages it just read. You'll see a
**Seeding** phase in the build timeline ("seeded N sources from research"). This is automatic; there's
no button.

> All three are graded by the **same** scorer and risk-tiered trust floor — a source is never trusted
> just for being uploaded, found, or seeded. A lone open-web source that merely *agrees* with a claim
> is still cut at HIGH risk; only a curated source or genuine cross-source agreement clears the floor.
> See [grounding.md](grounding.md#the-moat-defends-itself).

---

## Step 6 — Verify it for real (optional, but satisfying)

You don't have to trust the UI. Two independent checks:

### 6a. Re-build over the API and grab the run id

```bash
curl -s -D - -o /tmp/course.json \
  -X POST localhost:8000/api/courses \
  -H 'content-type: application/json' \
  -d '{"topic":"Dijkstra'\''s shortest-path algorithm"}' | grep -i x-run-id
```

**Expect:** an `x-run-id: <hex>` header (this id threads every log line), and a full course object
written to `/tmp/course.json`. (This is the synchronous build — it blocks ~2–4 min, then returns.)

### 6b. Score it against the definition of done

```bash
uv run lunaris-eval /tmp/course.json
```

**Expect:** a per-check report and an exit status. The **prerequisite-order** and **fit** checks
should **PASS** (the guarantees held on real model output). The **factuality** check reflects
grounding — with the stub retriever every claim is cut, which the checker treats as *no unsupported
claim shipped*, so the definition of done can still report met. Exit `0` = passed.

---

## Step 7 — Triangulate the logs (optional)

Every layer tags its logs with the same `run_id`. Using the id from Step 6a:

```bash
grep '"run_id":"<id>"' .run-state/api.log | head -40
```

**Expect:** a single ordered trail — `agent_course_run_started` → `prerequisite_graph_built` →
`authoring_loop_verified` → `agent_course_finalized` → `agent_course_run_completed` — all sharing that
one `run_id`. Any secret-looking field is shown as `***REDACTED***` by the logging redaction
processor.

---

## Step 8 — Shut down

```bash
make stop
```

**Expect:** a "Shutdown Summary" with `web stopped`, `api stopped`, `supabase stopped`. Your Supabase
**data is preserved** (volumes survive); `make run` brings it all back.

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
| Score a course | `uv run lunaris-eval <file.json>` | per-check report, exit 0 = met |
| Ground a course (manual) | Corpus tab → add source → **Re-ground**, or `make ingest DIR=… COURSE=…` | supported claims' citations go green |
| Stop everything | `make stop` | shutdown summary; data preserved |

## Troubleshooting

- **It built the binary-search course, not Dijkstra** → `make run` ran the stub. Your key is the
  placeholder or missing. Fix `.env` (Step 0b/0c) and re-run, or set the key in the UI Settings panel.
- **Status "Needs review" / all claims cut** → expected on a first run with an empty corpus (Step 3
  note). The course is still correct; only source citations are absent. **Fill the corpus
  ([Step 5](#step-5--fill-the-corpus-so-citations-go-green)) — manually, via auto-discovery, or the
  seed feed — then re-ground to turn citations green.**
- **Build is slow or returns 429s** → a full build is ~30–40 Claude calls; on lower rate-limit tiers,
  space runs out so you don't exhaust the per-minute budget.
- **Docker errors on start** → Docker Desktop isn't running. Start it, wait ~10s, `make run` again.
- **Port held** → answer the prompt to stop the holder or relocate; Supabase ports are fixed and will
  prompt to stop a conflicting stack (data preserved).

---

*See also [relevance.md](relevance.md) — how Lunaris scopes a course to the right level, what the
search keys unlock, and how it degrades honestly without them — and [grounding.md](grounding.md) —
the trust model, the three acquisition modes, and the corpus costs behind Step 5.*
