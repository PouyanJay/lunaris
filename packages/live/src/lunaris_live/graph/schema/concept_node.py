from pydantic import Field

from .base import LiveModel
from .mastery_criterion import MasteryCriterion
from .node_provenance import NodeProvenance
from .teaching_spec import TeachingSpec


class ConceptNode(LiveModel):
    """One atomic concept: the unit a session teaches and assesses.

    Identity and dependency say where the concept sits; ``teaching_spec`` and ``mastery_criteria``
    say what to do with it. The asset index (lesson text, quizzes, simulators, video segments) joins
    them in later phases. All of it lives on this one type rather than in a parallel structure, so
    there is exactly one node contract for the whole product.

    Both authored fields are optional: a graph is still structurally sound without them, and
    treating a missing spec as a broken node would make one failed authoring call condemn a whole
    compile. A node without them is teachable-in-principle but not yet teachable-in-practice.
    """

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    definition: str = Field(min_length=1, max_length=2000)
    #: Ids of the concepts that must be understood before this one.
    requires: list[str] = Field(default_factory=list)
    provenance: NodeProvenance = NodeProvenance.COMPILED
    #: Other names a learner might call this concept. What makes a question resolvable when it is
    #: asked in the learner's words rather than the compiler's.
    aliases: list[str] = Field(default_factory=list)
    teaching_spec: TeachingSpec | None = None
    #: What the learner must be able to do to have understood this — the basis of every later check.
    mastery_criteria: list[MasteryCriterion] = Field(default_factory=list)
