"""Shared hardening defaults for every live LLM client (provider-agnostic constants).

The Anthropic SDK's request timeout defaults to ``None`` — a stalled socket then hangs the call
(and, with no overall wall-clock bound, the whole agent run) forever. Every live Claude adapter
constructs its client with these defaults so a dead connection fails fast and the app-level
``retry_on_rate_limit`` / the agent's own retry can recover. Kept here (not in each adapter) so the
values live in one place; this module deliberately imports no provider SDK, so ``lunaris_runtime``
stays dependency-light.
"""

# Per-request timeout (seconds). Individual Claude calls in this app complete well under this; the
# bound exists to turn a hung socket into a prompt, recoverable error.
LLM_REQUEST_TIMEOUT_S = 60.0

# Bounded SDK-level retries for transient connection/5xx failures. Rate-limit (429) backoff is
# handled separately by ``retry_on_rate_limit``; this is a small safety net on top.
LLM_MAX_RETRIES = 2
