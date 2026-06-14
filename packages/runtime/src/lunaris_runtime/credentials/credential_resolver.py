from collections.abc import Awaitable, Callable, Mapping

# Resolves a user's BYOK provider keys for a run: ``user_id`` → {env-var name: key} for the keys
# they've set (absent providers omitted, so a missing required key surfaces honestly and an optional
# one degrades the capability). Bound as the run scope via :func:`run_credentials` so the live
# adapters' ``resolve_secret`` reads the tenant's keys, never the platform env. The API wires it
# from the CredentialVault when BYOK is on; the video worker takes the same shape to render on a
# job owner's keys at claim time (explainer-video V7). ``None`` (no resolver) means the env fallback
# — the admin / single-user / local-dev path.
CredentialResolver = Callable[[str], Awaitable[Mapping[str, str]]]
