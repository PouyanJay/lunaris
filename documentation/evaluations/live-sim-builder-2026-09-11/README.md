# Builder smoke evidence — 2026-09-11

The committed key-gated test actually passed against `claude-sonnet-4-6`: one candidate,
three paid calls (plan, generate, screenshot review), 56.695 seconds, USD 0.072492. Its complete
synthetic result includes source/specification/content hashes, token/cost records, candidate HTML,
independent behavioral report and visual verdict. Both PNG states were also manually inspected:
x=0/y=0 and x=10/y=20, correctly labeled axes, the correct connecting line and legible controls.

- [Complete approved result](approved-result.json)
- [Maximum state](approved-state-0.png)
- [Minimum state](approved-state-1.png)
- [Development run evidence](development-runs.json)
- [Rejected Haiku candidate source](rejected-haiku.html)

Haiku development runs exposed behavioral failures, ambiguous planner outputs, output truncation,
and incorrect diagrams despite numerically passing labels. A separate screenshot review was added;
its negative control rejected a reversed-axis candidate. Subsequent screenshots exposed a verifier
capture bug: clicking a lower button scrolled the instrument, cropping the chart top. The runner now
captures the complete bounded instrument, with real scroll/oversized regression tests. The final
Haiku run still drew an incorrect line and was rejected; the Sonnet run above passed. The older
`behavior-only-result.json` development status predates the mandatory visual gate and is **not**
a publishable artifact. It is recorded for transparency, not counted as a successful factory build.

This single synthetic domain smoke establishes an inspectable working build, not a quality-rate
estimate or production acceptance. Cross-domain evaluation, durable reuse, production session
integration and the user's learner rating belong to the remaining Phase 3 tickets. Generated HTML
was executed only inside the isolated appliance; inspect it as source outside that environment.
