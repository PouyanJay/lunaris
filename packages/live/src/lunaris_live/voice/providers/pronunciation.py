import re

_TERMS = re.compile(r"\b(HIPAA|EHR)\b")
_ALIASES = {"HIPAA": "Hippa", "EHR": "E-H-R"}


def spoken_text(text: str) -> str:
    """Pronunciation affects the provider input only; the canonical transcript stays verbatim."""
    return _TERMS.sub(lambda match: _ALIASES[match.group()], text)
