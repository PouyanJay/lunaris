"""Lunaris grounding — evidence retrieval + the deterministic verifier (Failure-B moat).

The retriever pulls evidence for a claim; an independent assessor scores support;
deterministic code decides supported-vs-cut and enforces the publish gate (no course
ships with a live unsupported claim). Retriever + assessor are Protocols so the corpus
backend (Supabase pgvector, D2) and the model are swappable, and tests run with stubs.
"""

from lunaris_grounding.assessors import ClaudeSupportAssessor, StubSupportAssessor
from lunaris_grounding.evidence import Evidence, Support
from lunaris_grounding.protocols import IEvidenceRetriever, ISupportAssessor
from lunaris_grounding.retrievers import StubEvidenceRetriever
from lunaris_grounding.verifier import Verifier

__all__ = [
    "ClaudeSupportAssessor",
    "Evidence",
    "IEvidenceRetriever",
    "ISupportAssessor",
    "StubEvidenceRetriever",
    "StubSupportAssessor",
    "Support",
    "Verifier",
]
