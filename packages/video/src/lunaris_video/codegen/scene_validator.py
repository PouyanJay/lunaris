import re

import structlog

from lunaris_video.schemas import SceneContract

_logger = structlog.get_logger(__name__)

# The no-LaTeX rule and the CE-only rule, enforced deterministically — a completion that
# violates them is rejected BEFORE any subprocess runs, with the violation named so the repair
# turn can fix it. `include_numbers` is banned outright: Axes numbers secretly invoke LaTeX.
_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(MathTex|Tex|SingleStringMathTex|BulletedList|Title)\s*\("), "LaTeX mobject"),
    (re.compile(r"include_numbers"), "Axes numbers (secretly LaTeX)"),
    (re.compile(r"\bmanimlib\b|\bmanimgl\b"), "manimgl import (CE only)"),
]

_CODE_FENCE = re.compile(r"^```(?:python)?\s*\n|\n```\s*$", re.MULTILINE)
# A sane upper bound on a single scene's source — the model's context already bounds it; this is
# defense-in-depth against a degenerate completion making compile() chew unbounded CPU.
_MAX_SOURCE_CHARS = 200_000

# The model intermittently emits typographic "smart" punctuation where ASCII was meant: a curly
# quote used as a string delimiter, or a dash in code position, is an "invalid character"
# SyntaxError (the prod S1_hook failure). Normalize these to ASCII BEFORE compile so a weak-model
# quirk costs no LLM repair turn (the project lesson: normalize, don't instruction-repair). Keyed by
# codepoint so the table itself stays plain ASCII (no ambiguous glyphs in the source).
_SMART_PUNCTUATION: dict[int, str] = {
    0x2014: "-",  # em dash
    0x2013: "-",  # en dash
    0x2012: "-",  # figure dash
    0x2018: "'",  # left single quotation mark
    0x2019: "'",  # right single quotation mark / apostrophe
    0x201C: '"',  # left double quotation mark
    0x201D: '"',  # right double quotation mark
    0x2026: "...",  # horizontal ellipsis
    0x00A0: " ",  # no-break space
}


def validate_scene_source(completion: str, scene: SceneContract) -> str:
    """A CORRECTNESS gate on generated source (no-LaTeX/CE-only/parses); NOT a security boundary.

    ``compile()`` parses but never executes, so this cannot stop hostile runtime behaviour —
    ``import os; os.system(...)`` passes it and then runs under ``manim render``. The trust
    boundary is the subprocess sandbox (``run_sandboxed``), not this function. Public because
    Gate A's tests and the security review reason about it directly.
    """
    if len(completion) > _MAX_SOURCE_CHARS:
        raise ValueError(f"scene source exceeds {_MAX_SOURCE_CHARS} chars")
    source = _CODE_FENCE.sub("", completion).strip() + "\n"
    source = _sanitize(source, scene)
    for pattern, label in _FORBIDDEN_PATTERNS:
        match = pattern.search(source)
        if match:
            raise ValueError(f"forbidden construct ({label}): {match.group(0)!r}")
    if "from style_tokens import" not in source:
        raise ValueError("missing `from style_tokens import *` — tokens must come from the map")
    class_pattern = re.compile(rf"class\s+{re.escape(scene.scene_class_name)}\s*\(")
    if not class_pattern.search(source):
        raise ValueError(f"missing scene class {scene.scene_class_name}(Scene)")
    try:
        compile(source, f"{scene.id}.py", "exec")
    except SyntaxError as exc:
        raise ValueError(f"source does not parse: {exc}") from exc
    return source


def _sanitize(source: str, scene: SceneContract) -> str:
    """Apply the deterministic, meaning-preserving fixes for known weak-model quirks BEFORE compile,
    emitting a ``codegen.sanitized`` event per fix that fires.

    Only transforms that cannot change the program's meaning live here: line-ending normalization
    (CRLF/CR → LF) and smart-punctuation → ASCII (a curly quote/dash in code position is a parse
    error the existing table repairs). The audit event is the point of B2 — it lets us measure how
    often a completion is recovered deterministically (free, instant) versus by an LLM parse-repair
    turn. NOT fixed here, by design: unterminated strings and ``2x``-style decimal literals — those
    cannot be repaired without guessing at intent (``.5``/``5.`` are already valid Python), so they
    stay with the bounded parse-repair turn (B3), never a deterministic rewrite that could corrupt
    on-screen text.
    """
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    if normalized != source:
        _logger.info("codegen.sanitized", scene_id=scene.id, fix="line_endings")
    translated = normalized.translate(_SMART_PUNCTUATION)
    if translated != normalized:
        codepoints = sorted(f"U+{cp:04X}" for cp in _SMART_PUNCTUATION if chr(cp) in normalized)
        _logger.info(
            "codegen.sanitized", scene_id=scene.id, fix="smart_punctuation", codepoints=codepoints
        )
    return translated
