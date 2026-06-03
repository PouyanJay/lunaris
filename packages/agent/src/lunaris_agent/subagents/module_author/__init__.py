from .assembler import LessonAssembler
from .claude import ClaudeModuleAuthor
from .lesson_draft import LessonDraft, SegmentDraft
from .parser import parse_lesson
from .prompt import build_authoring_prompt
from .protocol import IModuleAuthor
from .stub import StubModuleAuthor

__all__ = [
    "ClaudeModuleAuthor",
    "IModuleAuthor",
    "LessonAssembler",
    "LessonDraft",
    "SegmentDraft",
    "StubModuleAuthor",
    "build_authoring_prompt",
    "parse_lesson",
]
