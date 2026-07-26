-- Course-cost metering: what each course actually cost to build (calculated, not estimated).
--
-- Two owner-scoped tables. `cost_events` is the append-only ledger — one row per paid (or metered)
-- call during a build (a Claude completion, an embedding batch, a web search, a cover image, a
-- voiceover beat, a render), each carrying the MEASURED usage and the CALCULATED cost
-- (amount = usage x the price-book rate). `course_costs` is the one-row-per-course rollup the course
-- Overview reads: the total plus a breakdown (per-component / per-provider subtotals, user_key vs
-- platform pocket split). The ledger is the source of truth; the rollup is recomputable from it.
--
-- Identity notes:
--  * course_id is the rollup + purge key (text, no hard FK to public.courses — house precedent, so a
--    row survives a course rebuild). One course's cost aggregates every event across the main build
--    run AND the separate video-job / cover-job runs; run_id is per-event provenance.
--  * seq is the run-scoped emission index; the UNIQUE (run_id, seq) index makes double-recording a
--    run a failed insert rather than a silent duplicate.
--  * usage / breakdown are jsonb (the raw measured units / the subtotal tree), read back typed.
--  * price_book_version pins each row to the rate table it was priced under — a later rate change
--    never rewrites an existing cost (financial facts are immutable).
--  * pocket in ('user_key','platform') separates tenant BYOK spend from platform/infra spend.
--
-- Access posture: RLS enabled, OWNER-READ / SERVER-WRITE. Costs are recorded only by the build
-- (backend service_role client, which bypasses RLS), never by a user, so `authenticated` gets a
-- SELECT grant + an owner-only SELECT policy and nothing else — no insert/update/delete grant or
-- policy on either table. cost_events is therefore append-only AND read-only at the user layer; the
-- rollup is server-upserted. The revoke includes authenticated's DEFAULT grant so
-- TRUNCATE/REFERENCES/TRIGGER never leak (TRUNCATE is not governed by RLS).
--
-- To reverse: DROP TABLE IF EXISTS public.cost_events, public.course_costs;

create table if not exists public.cost_events (
    id                 bigint generated always as identity primary key,
    user_id            uuid references auth.users (id) on delete cascade,
    run_id             text not null check (length(run_id) between 1 and 200),
    course_id          text not null check (length(course_id) between 1 and 100),
    seq                integer not null check (seq >= 0),
    component          text not null check (length(component) between 1 and 100),
    provider           text not null check (provider in
                           ('anthropic', 'voyage', 'tavily', 'openai', 'elevenlabs', 'manim', 'local')),
    model              text check (length(model) between 1 and 200),
    pocket             text not null check (pocket in ('user_key', 'platform')),
    usage              jsonb not null default '{}'::jsonb,
    amount             numeric not null check (amount >= 0),
    currency           text not null check (length(currency) between 1 and 10),
    price_book_version text not null check (length(price_book_version) between 1 and 40),
    created_at         timestamptz not null default now(),
    -- Mirror the recorder's contract: a run's (run_id, seq) is unique, so a re-recorded build can't
    -- silently double-count (inline table constraint, matching the bookmarks natural-key style).
    unique (run_id, seq)
);

-- The one read shape: a course's whole ledger (drill-through + rollup recompute).
create index if not exists cost_events_course_idx on public.cost_events (course_id);
-- Defense-in-depth for the owner-only SELECT policy: an index on the RLS predicate column so a
-- direct user-JWT read (without a course_id predicate) doesn't sequential-scan under RLS.
create index if not exists cost_events_user_idx on public.cost_events (user_id);

create table if not exists public.course_costs (
    course_id          text primary key check (length(course_id) between 1 and 100),
    user_id            uuid references auth.users (id) on delete cascade,
    total_amount       numeric not null check (total_amount >= 0),
    currency           text not null check (length(currency) between 1 and 10),
    breakdown          jsonb not null default '{}'::jsonb,
    price_book_version text not null check (length(price_book_version) between 1 and 40),
    updated_at         timestamptz not null default now()
);

-- The owner's my-courses read shape (list costs for a user's courses).
create index if not exists course_costs_user_idx on public.course_costs (user_id);

-- RLS (BLOCKING): owner-read on both — the owner sees their own course's cost; the build writes via
-- service_role (bypasses RLS).
alter table public.cost_events enable row level security;
alter table public.course_costs enable row level security;

-- Defense in depth: drop ALL default grants (public, anon, and authenticated's defaults — the
-- latter so TRUNCATE/REFERENCES/TRIGGER never leak), then grant back only SELECT. No user ever
-- writes cost rows, so no insert/update/delete grant. The identity sequence needs no grant.
revoke all on table public.cost_events from public, anon, authenticated;
revoke all on table public.course_costs from public, anon, authenticated;
grant select on public.cost_events to authenticated;
grant select on public.course_costs to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
-- SELECT-only policies (owner-read); writes are server-side via service_role only.
create policy cost_events_select_own on public.cost_events
    for select to authenticated using ((select auth.uid()) = user_id);
create policy course_costs_select_own on public.course_costs
    for select to authenticated using ((select auth.uid()) = user_id);
