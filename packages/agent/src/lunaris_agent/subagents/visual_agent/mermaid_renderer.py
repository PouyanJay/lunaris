import asyncio
import hashlib
from collections.abc import Sequence
from pathlib import Path

import structlog

from .render_result import RenderResult

logger = structlog.get_logger()

# How to invoke the skill's render.ts. Per the beautiful-mermaid skill the prefix is
# "bun run", "npx tsx", or "deno run --allow-read --allow-write --allow-net".
_DEFAULT_RUNTIME = ("bun", "run")


class MermaidRenderer:
    """Live renderer that shells out to the beautiful-mermaid skill (Mermaid → SVG).

    Runs the skill's ``render.ts`` in a sandbox and treats a non-empty SVG as a successful
    render. Any failure (bad syntax, missing runtime) is caught and returned as
    ``RenderResult(ok=False)`` — never raised — so the engine can repair or skip.
    """

    def __init__(
        self,
        render_script: Path,
        output_dir: Path,
        *,
        runtime: Sequence[str] = _DEFAULT_RUNTIME,
        theme: str = "tokyo-night",
        timeout_s: float = 30.0,
    ) -> None:
        self._render_script = render_script
        self._output_dir = output_dir
        self._runtime = tuple(runtime)
        self._theme = theme
        self._timeout_s = timeout_s

    async def render(self, source: str) -> RenderResult:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        stem = hashlib.sha256(source.encode()).hexdigest()[:16]
        out = self._output_dir / stem
        try:
            process = await asyncio.create_subprocess_exec(
                *self._runtime,
                str(self._render_script),
                "--code",
                source,
                "--output",
                str(out),
                "--theme",
                self._theme,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as error:
            return RenderResult(ok=False, error=f"renderer failed to start: {error}")
        try:
            # An LLM can emit a valid-but-pathological diagram; never let render stall the run.
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=self._timeout_s)
        except TimeoutError:
            process.kill()
            return RenderResult(ok=False, error=f"renderer timed out after {self._timeout_s}s")

        svg = out.with_suffix(".svg")
        if process.returncode == 0 and svg.exists() and svg.stat().st_size > 0:
            return RenderResult(ok=True, path=str(svg))
        detail = stderr.decode(errors="replace").strip()[:200] if stderr else "no SVG produced"
        logger.warning("mermaid_render_failed", detail=detail)
        return RenderResult(ok=False, error=detail)
