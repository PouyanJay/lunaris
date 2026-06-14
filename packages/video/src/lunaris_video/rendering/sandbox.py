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
# Fork-bomb control (V7). RLIMIT_NPROC is PER-UID, so it is unusable in the in-process worker (it
# would throttle the API the worker shares a UID with). The dedicated worker container runs as its
# OWN UID with nothing else under it (Dockerfile.worker sets LUNARIS_VIDEO_DEDICATED_WORKER=1), so
# the cap is safe there — and stops a hostile render from exhausting the host's process table. 512
# is ample for a render (manim + a few sequential ffmpeg children); override with _NPROC_LIMIT_ENV.
_DEDICATED_WORKER_ENV = "LUNARIS_VIDEO_DEDICATED_WORKER"
_NPROC_LIMIT_ENV = "LUNARIS_VIDEO_NPROC_LIMIT"
_DEFAULT_NPROC_LIMIT = 512


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


def _positive_int_env(name: str, default: int) -> int:
    """A positive int from env ``name``, falling back to ``default`` when unset, non-numeric, or
    non-positive — so a bogus override degrades safely rather than weakening a limit to zero."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _mem_limit_bytes() -> int:
    return _positive_int_env(_MEM_LIMIT_ENV, _DEFAULT_MEM_LIMIT_BYTES)


def _nproc_limit() -> int | None:
    """The per-UID process cap for the render child, or ``None`` to leave RLIMIT_NPROC untouched.

    Returns ``None`` in the in-process worker (no dedicated-worker flag) — RLIMIT_NPROC is per-UID,
    so a cap there would throttle the API the worker shares a UID with. The dedicated worker
    container sets ``LUNARIS_VIDEO_DEDICATED_WORKER=1`` (its own UID), turning the fork-bomb cap on;
    a bogus or non-positive override degrades to the default rather than disabling the guard.
    """
    if os.getenv(_DEDICATED_WORKER_ENV) != "1":
        return None
    return _positive_int_env(_NPROC_LIMIT_ENV, _DEFAULT_NPROC_LIMIT)


def _apply_rlimits(
    *, mem_limit_bytes: int, cpu_seconds: int, nproc_limit: int | None
) -> None:  # pragma: no cover (child)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (_DEFAULT_FSIZE_LIMIT_BYTES, _DEFAULT_FSIZE_LIMIT_BYTES)
    )
    resource.setrlimit(resource.RLIMIT_NOFILE, (_NOFILE_LIMIT, _NOFILE_LIMIT))
    # CPU + AS + NPROC are suppressed the same way: a host that already imposes a tighter limit (a
    # stricter container) must DEGRADE containment, never fail every render.
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_AS, (mem_limit_bytes, mem_limit_bytes))
    # Fork-bomb cap — only when the dedicated worker container asked for it (its own UID). Per-UID,
    # so NEVER applied in the in-process worker (it would throttle the shared-UID API).
    if nproc_limit is not None:
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_NPROC, (nproc_limit, nproc_limit))


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

    Two gaps were deferred from the in-process worker to the V7 dedicated container (its own
    non-root UID): **fork bombs** — now capped via RLIMIT_NPROC, which is safe to set per-UID once
    nothing but the worker runs under that UID (``_nproc_limit`` / Dockerfile.worker sets the flag);
    and **egress** — a hostile render can still reach the network (an SSRF risk against the cloud
    metadata endpoint / internal services even though its env carries no secrets). A per-subprocess
    network namespace needs caps ACA Consumption does not grant, so egress containment stays at the
    no-secrets-env layer here; tightening it (a netns / egress-deny sidecar) is a documented
    follow-up, weighed in the V7 security review.
    """
    (cwd / "tmp").mkdir(parents=True, exist_ok=True)
    apply_rlimits = functools.partial(
        _apply_rlimits,
        mem_limit_bytes=_mem_limit_bytes(),
        cpu_seconds=int(timeout_s) * _CPU_LIMIT_MULTIPLIER + _CPU_LIMIT_GRACE_S,
        nproc_limit=_nproc_limit(),
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
