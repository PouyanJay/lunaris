import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, get_type_hints

import structlog
from fastapi import Depends, Header, HTTPException, status
from lunaris_agent import (
    LessonRegenerator,
    build_agent_course_builder,
    build_orchestrator,
    build_stub_orchestrator,
)
from lunaris_agent.subagents.goal_interpreter import (
    ClaudeGoalInterpreter,
    DefaultGoalInterpreter,
    IGoalInterpreter,
)
from lunaris_grounding import (
    InMemoryCorpusStore,
    InMemorySourceAuthorityStore,
    ISourceAuthorityStore,
    StubEmbedder,
    SupabaseCorpusStore,
    SupabaseSourceAuthorityStore,
    VoyageEmbedder,
)
from lunaris_runtime.persistence import (
    CourseStore,
    ICourseStore,
    InMemoryRunEventStore,
    InMemoryRunStore,
    IRunEventStore,
    IRunStore,
    SupabaseCourseStore,
    SupabaseRunEventStore,
    SupabaseRunStore,
)
from structlog.contextvars import bind_contextvars

from .auth import (
    AuthError,
    CompositeUserVerifier,
    IUserVerifier,
    JwksUserVerifier,
    JwtUserVerifier,
)
from .config import Settings, get_settings
from .config_store import ConfigStore
from .corpus_service import CorpusService
from .credential_vault import CredentialVault
from .explain import ClaudeExplainer, IExplainer
from .run_registry import RunRegistry
from .secrets import (
    BYOK_PROVIDERS,
    KNOWN_SECRETS,
    AnthropicProbeValidator,
    ICredentialStore,
    InMemoryCredentialStore,
    ISecretValidator,
    SecretCipher,
    SecretStore,
    SupabaseCredentialStore,
    build_secret_cipher,
)
from .service import CourseService, CredentialResolver, PipelineFactory

logger = structlog.get_logger()

# Worker-tier model for the cheap, short calls (Explain + the P7.5 brief interpretation behind the
# clarifier); overridable via the usual env knob. One literal so a model bump is a single edit.
_WORKER_MODEL = "claude-haiku-4-5-20251001"

# LUNARIS_PIPELINE → the per-run pipeline factory. ``agent`` (the default) is the real deep-agent
# harness; ``stub`` is the deterministic no-key demo; ``live`` is the legacy orchestrator.
_PIPELINE_FACTORIES: dict[str, PipelineFactory] = {
    "stub": build_stub_orchestrator,
    "agent": build_agent_course_builder,
    "live": build_orchestrator,
}


def pipeline_supports_lesson_regeneration(pipeline: str) -> bool:
    """Whether the configured pipeline implements the optional ``LessonRegenerator`` capability.

    Derived from the factory's declared return type — never by instantiating it (building the agent
    pipeline constructs LLM clients and needs an API key) — so it stays in lockstep with the
    ``isinstance(pipeline, LessonRegenerator)`` gate in ``CourseService.regenerate_lesson``: the
    single-shot Orchestrator regenerates, the deep-agent builder does not. The web reads this to
    show or hide the per-lesson regenerate action instead of offering a button that always 501s.
    (``issubclass`` against the runtime_checkable Protocol matches method *names* only — sufficient
    for the closed, hand-curated set of pipeline factories.)
    """
    factory = _PIPELINE_FACTORIES.get(pipeline)
    if factory is None:
        return False
    try:
        return_type = get_type_hints(factory).get("return")
    except Exception:
        # A factory whose annotations can't be resolved (e.g. PEP 563 string hints losing a name in
        # scope) falls back to "unsupported" — the same fail-safe as an unknown pipeline above.
        return False
    return isinstance(return_type, type) and issubclass(return_type, LessonRegenerator)


# One run store per process, shared across requests (mirrors _secret_stores). The in-memory
# fallback MUST be a singleton or the sidebar would see an empty history every request; the
# Supabase store is shared too, so its lazy client is built once, not per request. Tests inject
# their own via the get_course_service override.
_in_memory_run_store = InMemoryRunStore()
_supabase_run_store = SupabaseRunStore()

# The replayable build-event log (build-timeline Phase B), one per process (same singleton rationale
# as the run store: an in-memory log must be shared so a build's writes survive for a later replay
# read). The Supabase-store singleton rationale lives in get_run_event_store's docstring.
_in_memory_run_event_store = InMemoryRunEventStore()
_supabase_run_event_store = SupabaseRunEventStore()

# The durable course store (one per process, same lazy-client rationale as the run store): its
# service-role client is built on first write, so the singleton needs no network until then. The
# file-backed store is built per-request from course_dir (cheap), so it isn't a singleton.
_supabase_course_store = SupabaseCourseStore()

# One in-flight run-task registry per process, shared across requests — the cancel request and the
# build request must see the same in-flight set, so this MUST be a singleton.
_run_registry = RunRegistry()


def get_run_registry() -> RunRegistry:
    """The process-wide registry of in-flight build tasks (for cancellation)."""
    return _run_registry


def get_run_store(settings: Annotated[Settings, Depends(get_settings)]) -> IRunStore:
    """The run-history index: Supabase when creds are present, else the in-process fallback.

    The Supabase client is lazy, so the process-wide instance needs no network until the first
    write touches the environment. Without creds, history lives for the process lifetime only
    (durable, cross-machine history requires Supabase).
    """
    if settings.has_supabase:
        return _supabase_run_store
    return _in_memory_run_store


def get_run_event_store(settings: Annotated[Settings, Depends(get_settings)]) -> IRunEventStore:
    """The replayable build-event log: Supabase when creds are present, else the in-process store.

    Same lazy-client / process-singleton posture as ``get_run_store`` — without creds the log lives
    for the process lifetime only (durable, cross-machine replay requires Supabase).
    """
    if settings.has_supabase:
        return _supabase_run_event_store
    return _in_memory_run_event_store


# Process-wide corpus collaborators (singletons, like the run store): the in-memory corpus must be
# shared so a manually-ingested source survives for a later list/delete within the process; the
# Supabase store + Voyage embedder are shared so their lazy clients are built once, not per request.
# The in-memory store is the no-key fallback (lost on restart). Tests inject their own via override.
_in_memory_corpus_store = InMemoryCorpusStore()
_supabase_corpus_store = SupabaseCorpusStore()
_voyage_embedder = VoyageEmbedder()


def get_corpus_service(settings: Annotated[Settings, Depends(get_settings)]) -> CorpusService:
    """The manual-ingest service: real Voyage embeddings + Supabase corpus when keyed, else the
    in-memory store + a deterministic stub embedder (so manual ingest runs offline, non-durably)."""
    if settings.has_supabase and settings.has_embeddings:
        return CorpusService(_supabase_corpus_store, _voyage_embedder)
    logger.info("corpus_service_in_memory", reason="supabase/embeddings creds unset")
    return CorpusService(_in_memory_corpus_store, StubEmbedder())


CorpusServiceDep = Annotated[CorpusService, Depends(get_corpus_service)]

# The editable trust config (P6.2), one per process (same singleton rationale as the corpus store):
# an in-memory config must be shared so an added authority survives for a later list/delete within
# the process; the Supabase store is shared so its lazy client is built once. The in-memory store is
# the no-key fallback (empty + lost on restart — the durable, seeded config requires Supabase).
_in_memory_authority_store = InMemorySourceAuthorityStore()
_supabase_authority_store = SupabaseSourceAuthorityStore()


def get_authority_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ISourceAuthorityStore:
    """The trust-config store: Supabase (the seeded, durable table) when keyed, else in-memory."""
    if settings.has_supabase:
        return _supabase_authority_store
    return _in_memory_authority_store


AuthorityStoreDep = Annotated[ISourceAuthorityStore, Depends(get_authority_store)]

# One SecretStore per .env path (it owns process env + the on-disk file), so all requests share
# the same on-disk state. Tests override get_secret_store.
_secret_stores: dict[Path, SecretStore] = {}


def get_secret_store(settings: Annotated[Settings, Depends(get_settings)]) -> SecretStore:
    """The process-wide secret store for the configured .env path."""
    path = settings.env_file
    if path not in _secret_stores:
        _secret_stores[path] = SecretStore(path)
    return _secret_stores[path]


def get_secret_validator() -> ISecretValidator:
    """The live secret validator (probes Anthropic). Tests override with an accepting one."""
    return AnthropicProbeValidator()


SecretStoreDep = Annotated[SecretStore, Depends(get_secret_store)]
SecretValidatorDep = Annotated[ISecretValidator, Depends(get_secret_validator)]

# Process-wide BYOK credential stores (singletons, like the run/corpus stores): the in-memory store
# must be shared so a key set in one request survives for the next within the process; the Supabase
# store is shared so its lazy service-role client is built once. The in-memory store is the no-key
# fallback (lost on restart). Tests inject their own via the get_credential_store override.
_in_memory_credential_store = InMemoryCredentialStore()
_supabase_credential_store = SupabaseCredentialStore()


def get_credential_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ICredentialStore:
    """The BYOK credential store: Supabase (durable, RLS server-only) when keyed, else in-memory."""
    if settings.has_supabase:
        return _supabase_credential_store
    return _in_memory_credential_store


# Cipher cache keyed on a SHA-256 digest of the master key — NOT the key itself, so the raw base64
# secret is never retained as a cache key (an lru_cache would keep it in its wrapper dict). The
# AES-GCM context is built once per key and reused across requests.
_cipher_by_key_digest: dict[bytes, SecretCipher] = {}


def _build_cipher(master_key_b64: str | None) -> SecretCipher | None:
    """The at-rest cipher for the configured master key, or ``None`` when BYOK is off. A
    present-but-malformed key raises ``MasterKeyUnavailableError`` (a loud deployment error)."""
    if not master_key_b64:
        return None
    digest = hashlib.sha256(master_key_b64.encode()).digest()
    if digest not in _cipher_by_key_digest:
        cipher = build_secret_cipher(master_key_b64)
        assert cipher is not None  # non-empty key → build_secret_cipher returns a cipher or raises
        _cipher_by_key_digest[digest] = cipher
    return _cipher_by_key_digest[digest]


def get_credential_vault(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[ICredentialStore, Depends(get_credential_store)],
    validator: SecretValidatorDep,
) -> CredentialVault | None:
    """The BYOK vault, or ``None`` when BYOK is unconfigured (no master key) → the route 503s. The
    cipher is the gate: present ⇒ BYOK is on; the store + validator compose with it."""
    cipher = _build_cipher(settings.key_enc_master)
    if cipher is None:
        return None
    return CredentialVault(store=store, cipher=cipher, validator=validator)


CredentialVaultDep = Annotated[CredentialVault | None, Depends(get_credential_vault)]


def _byok_credential_resolver(vault: CredentialVault) -> CredentialResolver:
    """A per-run resolver over the vault: user_id → {env-var name: decrypted key} for keys they set.

    A provider the user hasn't set is omitted (its env-var key absent), so a missing required key
    surfaces as a refused build and an optional one degrades the capability honestly."""

    async def resolve(user_id: str) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for provider in BYOK_PROVIDERS:
            key = await vault.reveal(user_id=user_id, provider=provider)
            if key:
                resolved[KNOWN_SECRETS[provider]] = key
        return resolved

    return resolve


def get_course_service(
    settings: Annotated[Settings, Depends(get_settings)],
    run_store: Annotated[IRunStore, Depends(get_run_store)],
    registry: Annotated[RunRegistry, Depends(get_run_registry)],
    event_store: Annotated[IRunEventStore, Depends(get_run_event_store)],
    vault: CredentialVaultDep,
) -> CourseService:
    """Compose the CourseService for the configured pipeline (overridable in tests)."""
    # Durable Postgres store when Supabase is configured (courses survive restarts + are shared
    # across replicas — the stateless-container need); the file store otherwise (offline dev).
    store: ICourseStore = (
        _supabase_course_store if settings.has_supabase else CourseStore(settings.course_dir)
    )
    factory = _PIPELINE_FACTORIES.get(settings.pipeline)
    if factory is None:
        # An unrecognized LUNARIS_PIPELINE shouldn't silently run the paid live path; warn loudly.
        logger.warning("unknown_pipeline_falling_back", requested=settings.pipeline, default="live")
        factory = build_orchestrator
    # BYOK on (a vault is configured) → builds run on the caller's own keys; off → on the process
    # environment (admin/single-user), keeping today's behaviour.
    resolver = _byok_credential_resolver(vault) if vault is not None else None
    return CourseService(
        store, factory, run_store, registry, event_store, credential_resolver=resolver
    )


CourseServiceDep = Annotated[CourseService, Depends(get_course_service)]

# One ConfigStore per config-file path (owns process env + the on-disk file), shared by requests.
# Tests override get_config_store.
_config_stores: dict[Path, ConfigStore] = {}


def get_config_store(settings: Annotated[Settings, Depends(get_settings)]) -> ConfigStore:
    """The process-wide non-secret config store for the configured config path."""
    path = settings.config_path
    if path not in _config_stores:
        _config_stores[path] = ConfigStore(path)
    return _config_stores[path]


ConfigStoreDep = Annotated[ConfigStore, Depends(get_config_store)]


def explain_is_available() -> bool:
    """Whether plain-language Explain can run — i.e. an Anthropic key is reachable.

    Keyed on the environment variable (the unified runtime source, named once in ``KNOWN_SECRETS``):
    a key set in ``.env`` OR entered via the Settings UI (the SecretStore applies stored keys to
    ``os.environ``) both satisfy it.
    """
    return bool(os.getenv(KNOWN_SECRETS["anthropic"]))


# One explainer per process (built lazily on first availability). NOT cached as None — the key can
# be added at runtime via the Settings UI, so availability is re-checked every call.
_explainer: ClaudeExplainer | None = None


def get_explainer() -> IExplainer | None:
    """The transcript-blob explainer (worker tier), or None when no Anthropic key is reachable.

    None makes the route fail closed with a 503 instead of constructing a client that can't call
    out; the web mirrors this via ``supportsExplain`` so it never shows a button that would 503.
    """
    global _explainer
    if not explain_is_available():
        return None
    if _explainer is None:
        _explainer = ClaudeExplainer(os.getenv("LUNARIS_MODEL_WORKER", _WORKER_MODEL))
    return _explainer


ExplainerDep = Annotated[IExplainer | None, Depends(get_explainer)]


# One goal interpreter per process (built lazily on first availability), mirroring ``_explainer``.
# NOT cached as None — a key can be added at runtime via the Settings UI, so availability is
# re-checked each call: a present key returns the cached Claude client, an absent one the fallback.
_goal_interpreter: ClaudeGoalInterpreter | None = None


def get_goal_interpreter() -> IGoalInterpreter:
    """The brief interpreter behind the P7.5 clarifier (phase 1).

    The live Claude interpreter (worker tier) when an Anthropic key is reachable (same env source as
    Explain — a key in ``.env`` or the Settings UI), else a deterministic topic-derived fallback so
    the brief endpoint still renders the clarifier with sensible defaults without a key. The Claude
    client is lazy, so building it makes no network call; it is cached per process like Explain.
    """
    global _goal_interpreter
    if not explain_is_available():
        return DefaultGoalInterpreter()
    if _goal_interpreter is None:
        _goal_interpreter = ClaudeGoalInterpreter(os.getenv("LUNARIS_MODEL_WORKER", _WORKER_MODEL))
    return _goal_interpreter


GoalInterpreterDep = Annotated[IGoalInterpreter, Depends(get_goal_interpreter)]


@lru_cache
def _build_user_verifier(secret: str | None, supabase_url: str | None) -> IUserVerifier | None:
    """Compose the token verifier from config, cached per (secret, url) so the JWKS client's key
    cache is reused across requests instead of refetched each call.

    HS256 (local / shared secret) and asymmetric ES256/RS256 (cloud JWKS) can both be present; the
    composite routes each token to the right one by its header ``alg``. None when neither is set.
    """
    hs256 = JwtUserVerifier(secret) if secret else None
    asymmetric = JwksUserVerifier(supabase_url) if supabase_url else None
    if hs256 is None and asymmetric is None:
        return None
    return CompositeUserVerifier(hs256=hs256, asymmetric=asymmetric)


def get_jwt_verifier(
    settings: Annotated[Settings, Depends(get_settings)],
) -> IUserVerifier | None:
    """The end-user token verifier, or None when auth is unconfigured (fails closed with 503).

    The composition seam: HS256 for local/shared-secret, JWKS/ES256 for cloud — chosen per token by
    the composite, so ``require_user_id`` never depends on a concrete verifier.
    """
    return _build_user_verifier(settings.supabase_jwt_secret, settings.supabase_url)


JwtVerifierDep = Annotated[IUserVerifier | None, Depends(get_jwt_verifier)]

_UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def require_user_id(
    verifier: JwtVerifierDep,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Authenticate the caller from the ``Authorization: Bearer`` token and return their user id.

    401 on a missing/malformed/invalid/expired token; 503 when no JWT secret is configured (a
    deployment error, not a client one). Binds ``user_id`` to the logging context so every
    downstream log line for the request carries it alongside ``request_id``/``run_id``.
    """
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("auth_failed", reason="missing_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers=_UNAUTHENTICATED_HEADERS,
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_id = verifier.verify(token)
    except AuthError as exc:
        logger.warning("auth_failed", reason="invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers=_UNAUTHENTICATED_HEADERS,
        ) from exc
    bind_contextvars(user_id=user_id)
    return user_id


CurrentUserIdDep = Annotated[str, Depends(require_user_id)]


def optional_user_id(
    verifier: JwtVerifierDep,
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """The owner id for per-user data scoping — ``None`` when auth is not configured.

    The server-side mirror of the frontend ``AuthGate``: when auth is OFF (no verifier configured)
    this returns ``None`` so the user-data routes stay open and unscoped — byte-for-byte today's
    single-user behavior. When auth is ON it is mandatory: a missing/invalid token is a 401 (via
    ``require_user_id``), and a valid one yields the caller's id, which the service stamps on writes
    and filters reads by. So "optional" means *optional only while auth is unconfigured*, never a
    per-request opt-out once a deployment turns auth on.
    """
    if verifier is None:
        return None
    return require_user_id(verifier, authorization)


OptionalUserIdDep = Annotated[str | None, Depends(optional_user_id)]
