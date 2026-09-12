# Integration evidence

The authenticated Chromium test uses the committed, actually verified linear simulator artifact.
It exercises the real Supabase browser token client, API JWT validation, approved HTML serving,
React host, keyboard control, HTTP interaction persistence, reload recovery, fresh state for a
second learner, revocation fallback, and blocked external self-navigation. External attack requests
are intercepted and aborted in the negative control; the corrected host emits none. The attached
image was inspected after a tutor demonstration returned the instrument to the origin.

The fixture coach is deterministic. This test does not claim a paid end-to-end tutor evaluation.
Real provider/domain evaluations and production acceptance are tracked separately in #237.

Real REST/Postgres tests cover queued cold sessions, supervisor publication, the next session turn,
rejected and unsuitable outcomes, no evidence on an ungraded cold turn, reuse without another
build, stale unpaid recovery and paid quotas. Worker tests additionally close/delete a session
while generation is paused and verify that its result is discarded.

Local validation: 3,164 Python tests passed (18 skipped); 1,752 web tests passed; 15 actual browser
cases passed. TypeScript, Ruff, formatting and database lint passed. ESLint retains one existing
Fast Refresh warning in CopilotSession.tsx and has no errors. Final full database count is recorded
in the PR. Python/style, test and security review findings were resolved and approved.
