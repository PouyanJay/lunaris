import asyncio
import contextlib
import os
import resource
import signal
from pathlib import Path

import structlog

from lunaris_video.models.sandbox_result import SandboxResult

_logger = structlog.get_logger(__name__)

_OUTPUT_TAIL_CHARS = 4_000
_DEFAULT_FSIZE_LIMIT_BYTES = 512 * 1024 * 1024  # renders are <100MB; a runaway writer dies early
_NOFILE_LIMIT = 256


def _build_minimal_env(home: Path) -> dict[str, str]:
    """An env built from scratch — the parent's secrets (API keys, tokens) never reach the child.

    Principle 6: generated code is untrusted. Only PATH crosses the boundary (manim must find
    ffmpeg); HOME points INTO the sandbox dir so font/config caches land there and nothing reads
    the real user profile.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "TMPDIR": str(home / "tmp"),
        "MPLCONFIGDIR": str(home / "tmp"),
        "LANG": "C.UTF-8",
    }


def _apply_rlimits() -> None:  # pragma: no cover — runs inside the forked child
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (_DEFAULT_FSIZE_LIMIT_BYTES, _DEFAULT_FSIZE_LIMIT_BYTES)
    )
    resource.setrlimit(resource.RLIMIT_NOFILE, (_NOFILE_LIMIT, _NOFILE_LIMIT))


async def run_sandboxed(argv: list[str], *, cwd: Path, timeout_s: float) -> SandboxResult:
    """Run untrusted work in a subprocess with a wall-clock kill, rlimits, and a minimal env.

    The hardening contract (principle 6, security-reviewed in V1-T5):

    - **Minimal env.** Built from scratch; no parent secrets, HOME/TMPDIR inside ``cwd``.
    - **Wall-clock timeout.** The child runs in its own session (process group); on expiry the
      WHOLE group gets SIGKILL — manim's ffmpeg children die with it.
    - **Rlimits.** No core dumps, bounded file size (kills runaway writers with SIGXFSZ),
      bounded open files.
    - **Bounded output.** Only the stdout/stderr TAILS are kept — a print-loop can't balloon
      worker memory or logs.

    Network egress is NOT blocked at this layer: that is deployment-level policy (the worker
    container, V7); the env carries no credentials to exfiltrate.
    """
    (cwd / "tmp").mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=_build_minimal_env(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        preexec_fn=_apply_rlimits,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except TimeoutError:
        _kill_process_group(process.pid)
        await process.wait()
        _logger.warning("sandbox.timed_out", argv0=argv[0], timeout_s=timeout_s)
        return SandboxResult(
            returncode=-signal.SIGKILL,
            stdout_tail="",
            stderr_tail=f"timed out after {timeout_s}s (process group killed)",
            timed_out=True,
        )
    return SandboxResult(
        returncode=process.returncode if process.returncode is not None else -1,
        stdout_tail=stdout.decode(errors="replace")[-_OUTPUT_TAIL_CHARS:],
        stderr_tail=stderr.decode(errors="replace")[-_OUTPUT_TAIL_CHARS:],
        timed_out=False,
    )


def _kill_process_group(pid: int) -> None:
    # The SIGKILL already raced the child's own exit if either fires: ProcessLookupError (group
    # gone) or PermissionError (a container runtime reparented/reaped it first). Either way the
    # group is dying — a failed confirmation must not surface to the caller.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)
