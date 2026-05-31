"""The structlog redaction processor — strip sensitive values before any sink sees them.

Operational logs must never carry secrets or credentials (SECURITY.md, PYTHON.md). This processor
sits in the structlog pipeline ahead of the renderer and replaces the value of any event key whose
name marks it sensitive (API keys, tokens, passwords, authorization, credentials) with a fixed
marker. It is defense-in-depth: the secret store already keeps values out of logs by never logging
them, but a stray ``logger.info("...", api_key=value)`` would otherwise leak — this catches it.
"""

from collections.abc import Mapping
from typing import Any

_REDACTED = "***REDACTED***"

# Substring markers matched case-insensitively against each event key. Substrings (not exact keys)
# so ``api_key``, ``anthropic_api_key``, ``x-api-key``, ``access_token``, ``client_secret`` and
# ``service_role_key`` all match. Deliberately omits broad words like bare ``key`` / ``session`` /
# ``email`` that would clobber legitimate operational fields (``cache_key``, ``session_id``,
# correlation ids): redact credentials without hiding the data that makes logs useful.
_SENSITIVE_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "service_role",
    "cookie",
)


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_MARKERS)


def _redact_value(value: Any) -> Any:
    """Recurse into nested mappings/sequences so a secret nested under a non-sensitive key is still
    caught (e.g. a logged ``payload={"api_key": "..."}``). Scalars pass through unchanged."""
    if isinstance(value, Mapping):
        return {
            k: (_REDACTED if _is_sensitive(str(k)) else _redact_value(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def redact_sensitive(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: redact values under sensitive keys, recursively. Never raises."""
    for key in list(event_dict.keys()):
        if _is_sensitive(str(key)):
            event_dict[key] = _REDACTED
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict
