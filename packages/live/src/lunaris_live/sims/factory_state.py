from typing import TypedDict

from ..graph.schema import ConceptNode, MasteryCriterion
from .schema.build_result import SimBuildCall
from .schema.candidate import SimCandidate
from .schema.teaching_spec import TeachingSpec
from .schema.verification_report import VerificationReport
from .schema.verified_bundle import VerifiedBundle
from .schema.visual_verdict import SimVisualVerdict


class FactoryState(TypedDict):
    node: ConceptNode
    criterion: MasteryCriterion
    spec: TeachingSpec | None
    candidates: list[SimCandidate]
    candidate: SimCandidate | None
    bundle: VerifiedBundle | None
    calls: list[SimBuildCall]
    reports: list[VerificationReport]
    visual_reviews: list[SimVisualVerdict]
    reserved: int
    attempts: int
    status: str
    reason: str | None
