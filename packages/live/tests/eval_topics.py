"""The ten topics Phase 1 has to survive, and the probes that interrogate each map.

The plan's exit criterion is "ten *diverse* topics", and diversity here is not ten flavours of the
same shape. Prerequisite structure is obvious in mathematics and contentious in history; a language
has rules while jazz has conventions; a legislative process is a sequence where an ecosystem is a
web. A compiler that only works where the subject is already a ladder has not been shown to work.

Each topic carries two probes, because C1 and C2 are Phase 1 success criteria and proving them
against a stub proves them about the stub:

``paraphrase`` is the same question a learner would ask in their own words — not the compiler's, so
it exercises the aliases rather than the names. ``off_map`` is deliberately adjacent-but-absent: a
real thing a learner would ask that a map of *this* topic has no business already containing, which
is exactly the case that must resolve to nothing and route to an extension.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalTopic:
    """One topic of the exit criterion, with the two questions asked of the map it produces."""

    #: Short id — the test id, and the digest's filename.
    slug: str
    topic: str
    #: A learner's wording for something the map should already cover (C2 must resolve it).
    paraphrase: str
    #: A learner's wording for something it should not (C2 returns None; C1 then grows it).
    off_map: str


TOPICS: tuple[EvalTopic, ...] = (
    EvalTopic(
        slug="neural-networks",
        topic="How neural networks learn",
        paraphrase="what's the step size in gradient descent",
        off_map="how do I deploy this to a phone",
    ),
    EvalTopic(
        slug="seasons",
        topic="Why the seasons change",
        paraphrase="why is the earth tilted",
        off_map="what causes tides",
    ),
    EvalTopic(
        slug="bayesian-inference",
        topic="Bayesian inference",
        paraphrase="what's a prior probability",
        off_map="how do I run a t-test",
    ),
    EvalTopic(
        slug="crispr",
        topic="How CRISPR gene editing works",
        paraphrase="what is guide RNA",
        off_map="what are the ethics of editing embryos",
    ),
    EvalTopic(
        slug="us-legislation",
        topic="How a bill becomes law in the United States",
        paraphrase="what does a committee do to a bill",
        off_map="how are supreme court justices confirmed",
    ),
    EvalTopic(
        slug="structural-loads",
        topic="Why bridges don't fall down",
        paraphrase="what is tension in a beam",
        off_map="how much does a bridge cost to build",
    ),
    EvalTopic(
        slug="supply-and-demand",
        topic="Supply and demand",
        paraphrase="what is the equilibrium price",
        off_map="what is quantitative easing",
    ),
    EvalTopic(
        slug="spanish-verbs",
        topic="How Spanish verb conjugation works",
        paraphrase="what is the subjunctive mood",
        off_map="how is Spanish pronounced in Argentina",
    ),
    EvalTopic(
        slug="jazz-harmony",
        topic="Jazz harmony",
        paraphrase="what is a tritone substitution",
        off_map="how do I mic a double bass",
    ),
    EvalTopic(
        slug="roman-republic",
        topic="What caused the fall of the Roman Republic",
        paraphrase="what were the Gracchi reforms",
        off_map="how did the Roman Empire finally end",
    ),
)
