import os
import shlex
from pathlib import Path

import structlog
from lunaris_grounding import (
    IVideoSource,
    SearchVideoSource,
    TrafilaturaContentExtractor,
    YouTubeVideoSource,
)
from lunaris_runtime.credentials import resolve_secret

from ..coverage_critic import (
    ClaudeCoverageCritic,
    DeterministicCoverageCritic,
    ICoverageCritic,
)
from ..subagents.resource_curator import (
    ClaudeQueryTranslator,
    ClaudeResourceCurator,
    IResourceCurator,
)
from ..subagents.scope_polisher import ClaudeScopePolisher, IScopePolisher
from ..subagents.standard_researcher import ClaudeStandardResearcher, IStandardResearcher
from ..subagents.visual_agent import (
    ClaudeVisualGenerator,
    MermaidRenderer,
    PassthroughDiagramRenderer,
    VisualEngine,
)
from ._grounding import _search_provider_from_env

logger = structlog.get_logger()


def _researcher_from_env(worker_model: str) -> IStandardResearcher:
    """The standard researcher — always live now that search is keyless (Tavily or DuckDuckGo).

    Grounds the brief over the selected search provider + Trafilatura extraction (worker tier for
    distillation). The keyless path uses DuckDuckGo, so research no longer degrades to UNAVAILABLE.
    """
    return ClaudeStandardResearcher(
        worker_model, _search_provider_from_env(), TrafilaturaContentExtractor()
    )


def _video_source_from_env() -> IVideoSource:
    """The video source for resource curation: YouTube when keyed, else the shared-search fallback.

    With a ``YOUTUBE_API_KEY`` set, videos come from the YouTube Data API (guaranteed-video results
    + channel); without one, every video query routes through the shared ``ISearchProvider`` (itself
    keyless via DuckDuckGo when there's no Tavily key) so a video is still found + vetted, just
    without YouTube's metadata.
    """
    if resolve_secret("YOUTUBE_API_KEY"):
        return YouTubeVideoSource()
    logger.info("video_source_search_fallback", reason="YOUTUBE_API_KEY unset")
    return SearchVideoSource(_search_provider_from_env())


def _curator_from_env(worker_model: str) -> IResourceCurator:
    """Build the resource curator — always live now that search is keyless (P7.4).

    Mirrors the researcher: the live curator finds + vets resources over the selected search
    provider, plus an ``IVideoSource`` (worker tier for the relevance judge). The query translator
    (CQ Phase 2, worker tier) rewrites each competency into domain vernacular before the search.
    Search is keyless (Tavily or DuckDuckGo), so curation is always live rather than stubbing.
    """
    return ClaudeResourceCurator(
        worker_model,
        _search_provider_from_env(),
        _video_source_from_env(),
        translator=ClaudeQueryTranslator(worker_model),
    )


def _scope_polisher_from_env(worker_model: str) -> IScopePolisher | None:
    """Build the live scope-band polisher iff an Anthropic key is present, else ``None`` (CQ P3.1).

    The polish step refines only the wording of the scope band's does/doesn't lines (worker tier);
    its facts are owned by the deterministic estimator and re-asserted in code, so the model can
    sharpen the copy but never change the effort or invent a promise. ``None`` (no key) ships the
    deterministic band unchanged — the offline path stays byte-for-byte stable, no LLM call made.
    """
    if resolve_secret("ANTHROPIC_API_KEY"):
        return ClaudeScopePolisher(worker_model)
    logger.info("scope_polisher_disabled", reason="ANTHROPIC_API_KEY unset")
    return None


def _coverage_critic_from_env(strong_model: str) -> ICoverageCritic:
    """Build the coverage critic (CQ Phase 4.2): the LLM judge when keyed, else the fail-safe.

    The gate always runs. With an ``ANTHROPIC_API_KEY`` the primary is the ``ClaudeCoverageCritic``
    (strong tier — coverage is a judgement call, and it already degrades to the deterministic check
    on any failure). Without a key it is the ``DeterministicCoverageCritic`` directly — a structural
    check that needs no model, so a keyless build still gets an honest coverage gate. Either way an
    unresearched brief yields a clean report (nothing was promised), so the offline suite is stable.
    """
    if resolve_secret("ANTHROPIC_API_KEY"):
        return ClaudeCoverageCritic(strong_model)
    logger.info("coverage_critic_keyless", reason="ANTHROPIC_API_KEY unset")
    return DeterministicCoverageCritic()


def _visual_engine_from_env(worker_model: str) -> VisualEngine:
    """Wire the live visual engine, choosing the renderer from the environment.

    The generator (Claude, worker tier) always proposes a branded ``VisualSpec`` plus a Mermaid
    fallback. The renderer only gates the *source* path:
    - ``LUNARIS_MERMAID_SCRIPT`` set → the real :class:`MermaidRenderer` shells out to the
      beautiful-mermaid skill's ``render.ts`` (``LUNARIS_VISUAL_DIR`` = SVG output dir, default
      ``.visuals``; ``LUNARIS_MERMAID_RUNTIME`` = the invocation prefix, default ``bun run``,
      e.g. ``npx tsx``), validating each diagram to an SVG before it ships.
    - unset → the :class:`PassthroughDiagramRenderer`, which validates the source syntactically and
      ships it un-rendered (the web draws from the spec or the raw source, never the SVG path).

    Either way a course gets its branded visuals; the render toolchain is an enhancement, never a
    hard dependency. Always returns an engine (which still declines decorative diagrams itself).
    """
    script = os.getenv("LUNARIS_MERMAID_SCRIPT")
    if not script:
        logger.info("visual_engine_passthrough", reason="LUNARIS_MERMAID_SCRIPT unset")
        return VisualEngine(ClaudeVisualGenerator(worker_model), PassthroughDiagramRenderer())
    output_dir = Path(os.getenv("LUNARIS_VISUAL_DIR", ".visuals"))
    runtime_env = os.getenv("LUNARIS_MERMAID_RUNTIME")
    runtime = tuple(shlex.split(runtime_env)) if runtime_env else None
    renderer = (
        MermaidRenderer(Path(script), output_dir, runtime=runtime)
        if runtime
        else MermaidRenderer(Path(script), output_dir)
    )
    return VisualEngine(ClaudeVisualGenerator(worker_model), renderer)
