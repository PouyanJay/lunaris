"""Lunaris agent — the course pipelines (orchestrator + deep-agent harness) and model router."""

from .composition import build_agent_course_builder, build_orchestrator
from .composition_stub import build_stub_orchestrator
from .critic import ICritic, MinimalCritic
from .harness.runner import AgentCourseBuilder
from .orchestrator import Orchestrator
from .pipeline import CoursePipeline

__all__ = [
    "AgentCourseBuilder",
    "CoursePipeline",
    "ICritic",
    "MinimalCritic",
    "Orchestrator",
    "build_agent_course_builder",
    "build_orchestrator",
    "build_stub_orchestrator",
]
