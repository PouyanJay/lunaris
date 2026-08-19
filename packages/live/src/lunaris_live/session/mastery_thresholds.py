"""The band a belief can sit in, and the one place it is written down.

Two constants rather than one export, because they are one fact: each is only meaningful relative
to the other. They live here rather than inside ``decide_move`` because Tier 2's composer keys the
lesson's scaffolding off the same band (T5). A learner the director considers to have mastered a
concept, still being handed the scaffolding for somebody who has not, is two rule sets disagreeing
about what "has it" means — drift that is invisible to every test reading only one of them, and
exactly what makes an adaptive system feel arbitrary to the person using it.
"""

#: Recall at or above this counts as "the learner has this".
#:
#: It gates introductions, so it is the number that decides whether progress through the map is
#: earned or waved through. Set above what a single MET can reach (one piece of evidence lands at
#: 0.45), so mastery takes more than one right answer — a guess must not unlock a dependent.
MASTERED = 0.6

#: Recall below this on a concept the learner HAS demonstrated means it is slipping and is worth
#: coming back to. Under ``MASTERED`` by design: a concept between the two is neither solid enough
#: to build on nor faded enough to interrupt for.
DECAYED = 0.45
