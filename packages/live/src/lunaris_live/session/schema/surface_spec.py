from typing import Annotated

from pydantic import Field

from .concept_map_card import ConceptMapCard
from .criterion_card import CriterionCard
from .explain_back import ExplainBack
from .mastery_meter import MasteryMeter
from .quiz_card import QuizCard
from .sim_app_card import SimAppCard

#: What a turn puts on screen, discriminated by ``kind``.
#:
#: A tagged union rather than one model with a mode field and a dozen optional props: every renderer
#: on the other side of the wire switches on ``kind`` anyway, and a union makes an impossible
#: combination — a quiz with a criterion statement, a meter with options — unrepresentable rather
#: than merely undocumented. Pydantic validates the discriminator on parse, so a stored turn from a
#: build that knew a kind this one does not fails loudly here instead of arriving half-read.
type SurfaceSpec = Annotated[
    CriterionCard | QuizCard | ExplainBack | MasteryMeter | ConceptMapCard | SimAppCard,
    Field(discriminator="kind"),
]
