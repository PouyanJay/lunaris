import asyncio
import contextlib
import functools
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
# Virtual-memory cap: bounds a memory bomb (e.g. `bytearray(8 * 1024**3)`) below the worker's RAM,
# so an OOM fails the one job instead of OOM-killing the whole in-process API. 3 GiB leaves a 720p
# render ample headroom; tunable for the larger overview kind. macOS ignores RLIMIT_AS (dev no-op);
# Linux (CI + the prod worker) enforces it.
_DEFAULT_MEM_LIMIT_BYTES = 3 * 1024 * 1024 * 1024
_MEM_LIMIT_ENV = "LUNARIS_VIDEO_MEM_LIMIT_BYTES"
# CPU-seconds backstop: a multiple of the wall-clock budget, so a legitimate (possibly
# multi-threaded) render never approaches it but a tight loop that starves this worker's own event
# loop — delaying the asyncio wall-clock kill — still gets a hard kernel SIGXCPU.
_CPU_LIMIT_MULTIPLIER = 4
_CPU_LIMIT_GRACE_S = 30


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


def _mem_limit_bytes() -> int:
    raw = os.getenv(_MEM_LIMIT_ENV)
    if raw is None:
        return _DEFAULT_MEM_LIMIT_BYTES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MEM_LIMIT_BYTES
    return value if value > 0 else _DEFAULT_MEM_LIMIT_BYTES


def _apply_rlimits(*, mem_limit_bytes: int, cpu_seconds: int) -> None:  # pragma: no cover (child)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (_DEFAULT_FSIZE_LIMIT_BYTES, _DEFAULT_FSIZE_LIMIT_BYTES)
    )
    resource.setrlimit(resource.RLIMIT_NOFILE, (_NOFILE_LIMIT, _NOFILE_LIMIT))
    # CPU + AS are suppressed the same way: a host that already imposes a tighter limit (a stricter
    # container) must DEGRADE containment, never fail every render. NOTE: neither is a fork-bomb
    # control — RLIMIT_NPROC is per-UID, so lowering it in this in-process (API-shared-UID) worker
    # would starve the API itself; PID-namespace isolation is the V7 container's job.
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_AS, (mem_limit_bytes, mem_limit_bytes))


async def run_sandboxed(argv: list[str], *, cwd: Path, timeout_s: float) -> SandboxResult:
    """Run untrusted work in a subprocess with a wall-clock kill, rlimits, and a minimal env.

    The hardening contract (principle 6, security-reviewed in V1-T5). This is the REAL trust
    boundary — the code-validator (no-LaTeX/CE gate) is a correctness check, NOT a security
    control; ``manim render`` executes the module, so the isolation here is what contains it:

    - **Minimal env.** Built from scratch; no parent secrets, HOME/TMPDIR inside ``cwd``.
    - **Wall-clock timeout.** The child runs in its own session (process group); on expiry the
      WHOLE group gets SIGKILL — manim's ffmpeg children die with it.
    - **Rlimits.** No core dumps; bounded file size (SIGXFSZ); bounded open files; a virtual-memory
      cap (a memory bomb fails the one job, never OOM-kills the in-process API); a CPU-seconds
      backstop (independent of the async wall clock, which a CPU-pinned child could delay by
      starving this worker's event loop).
    - **Bounded output.** Only the stdout/stderr TAILS are kept — a print-loop can't balloon
      worker memory or logs.

    NOT contained at this in-process layer, and REQUIRED of the V7 worker container (its own
    non-root UID + PID/network namespaces): **egress** — a hostile render can still reach the
    network, an SSRF risk against the cloud metadata endpoint / internal services even though the
    env carries no secrets; and **fork bombs** — RLIMIT_NPROC is per-UID and unusable in a worker
    sharing the API's UID. V7 MUST run with an egress-deny default and a process-namespace.
    """
    (cwd / "tmp").mkdir(parents=True, exist_ok=True)
    apply_rlimits = functools.partial(
        _apply_rlimits,
        mem_limit_bytes=_mem_limit_bytes(),
        cpu_seconds=int(timeout_s) * _CPU_LIMIT_MULTIPLIER + _CPU_LIMIT_GRACE_S,
    )
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=_build_minimal_env(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        preexec_fn=apply_rlimits,
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
