"""Sandbox tests (real subprocesses, no manim): the hardening contract of principle 6 —
wall-clock kill, minimal env, bounded output, bounded file writes — proven by running actual
children, not by asserting on argv strings."""

import resource
import sys
from pathlib import Path

import pytest
from lunaris_video.rendering import run_sandboxed
from lunaris_video.rendering.sandbox import _apply_rlimits, _nproc_limit


def _python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_nproc_cap_is_off_in_process_and_on_in_the_dedicated_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # In-process (no dedicated-worker flag): RLIMIT_NPROC is per-UID, so capping it would throttle
    # the API the worker shares a UID with — the resolver must return None (no cap) there.
    monkeypatch.delenv("LUNARIS_VIDEO_DEDICATED_WORKER", raising=False)
    assert _nproc_limit() is None

    # The dedicated worker container (its own UID) sets the flag — the cap turns on, with a sane
    # default and an env override; a bogus override falls back to the default rather than disabling.
    monkeypatch.setenv("LUNARIS_VIDEO_DEDICATED_WORKER", "1")
    assert _nproc_limit() == 512
    monkeypatch.setenv("LUNARIS_VIDEO_NPROC_LIMIT", "64")
    assert _nproc_limit() == 64
    monkeypatch.setenv("LUNARIS_VIDEO_NPROC_LIMIT", "not-a-number")
    assert _nproc_limit() == 512


def test_apply_rlimits_caps_nproc_only_when_a_limit_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # White-box: record setrlimit calls instead of mutating the test process's real limits.
    calls: list[int] = []
    monkeypatch.setattr(resource, "setrlimit", lambda which, limits: calls.append(which))

    # In-process mode (nproc_limit=None): the fork-bomb cap must NOT be applied (protects the API).
    _apply_rlimits(mem_limit_bytes=1, cpu_seconds=1, nproc_limit=None)
    assert resource.RLIMIT_NPROC not in calls

    # Dedicated worker (a concrete cap): RLIMIT_NPROC is set, alongside the existing limits.
    calls.clear()
    _apply_rlimits(mem_limit_bytes=1, cpu_seconds=1, nproc_limit=128)
    assert resource.RLIMIT_NPROC in calls


async def test_a_hanging_child_is_killed_at_the_wall_clock(tmp_path: Path) -> None:
    # Arrange / Act — a 30s sleep against a 0.5s budget; wait_for would hang if the kill failed.
    result = await run_sandboxed(
        _python("import time; time.sleep(30)"), cwd=tmp_path, timeout_s=0.5
    )

    # Assert — killed and reported as a timeout (a hang repairs differently to a crash). The
    # call returning at all proves the process-group kill fired; no wall-clock assertion needed.
    assert result.timed_out
    assert not result.succeeded


async def test_parent_secrets_never_reach_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a secret in the worker's environment, like a tenant key would be.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-never-forward")

    # Act
    result = await run_sandboxed(
        _python("import os; print(sorted(os.environ))"), cwd=tmp_path, timeout_s=10
    )

    # Assert — env is built from scratch: PATH crosses (ffmpeg discovery), secrets do not.
    assert result.succeeded
    assert "ANTHROPIC_API_KEY" not in result.stdout_tail
    assert "PATH" in result.stdout_tail


async def test_sandbox_home_is_remapped_into_the_workdir(tmp_path: Path) -> None:
    # Arrange / Act — HOME must point INSIDE the sandbox so font/config caches never touch the
    # real user profile.
    result = await run_sandboxed(
        _python("import os; print(os.environ['HOME'])"), cwd=tmp_path, timeout_s=10
    )

    # Assert
    assert result.stdout_tail.strip() == str(tmp_path)


async def test_child_output_is_truncated_to_a_tail(tmp_path: Path) -> None:
    # Arrange / Act — 200k of stdout from a print loop.
    result = await run_sandboxed(_python("print('x' * 200_000)"), cwd=tmp_path, timeout_s=10)

    # Assert — bounded: a chatty render can't balloon worker memory or run_events payloads.
    assert result.succeeded
    assert len(result.stdout_tail) <= 4_000


async def test_runaway_file_writes_are_limited(tmp_path: Path) -> None:
    # Arrange — a child that tries to write 600MB (over the 512MB rlimit).
    code = (
        "f = open('big.bin', 'wb')\n"
        "block = b'0' * (1024 * 1024)\n"
        "for _ in range(600):\n"
        "    f.write(block)\n"
        "f.close()\n"
        "print('wrote it all')\n"
    )

    # Act
    result = await run_sandboxed(_python(code), cwd=tmp_path, timeout_s=60)

    # Assert — SIGXFSZ (or the resulting OSError) stops it; the file never reaches 600MB. The
    # RLIMIT_FSIZE enforcement is POSIX (Linux worker + macOS dev both honor it); a future
    # non-POSIX CI runner would need a skipif guard here.
    assert not result.succeeded
    assert "wrote it all" not in result.stdout_tail
    big = tmp_path / "big.bin"
    assert not big.exists() or big.stat().st_size <= 512 * 1024 * 1024


async def test_nonzero_exit_is_reported_with_stderr_tail(tmp_path: Path) -> None:
    # Arrange / Act
    result = await run_sandboxed(
        _python("raise RuntimeError('scene exploded')"), cwd=tmp_path, timeout_s=10
    )

    # Assert — the stack trace tail is what Gate A's repair prompt feeds the model.
    assert not result.succeeded
    assert not result.timed_out
    assert "scene exploded" in result.stderr_tail


@pytest.mark.skipif(
    sys.platform != "linux", reason="RLIMIT_AS is enforced on Linux; macOS ignores it"
)
async def test_a_memory_bomb_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — a low cap so the test allocates little; the real default is 3 GiB. A whole-API OOM
    # (the worker runs in-process with the API) must become a single-job MemoryError instead.
    monkeypatch.setenv("LUNARIS_VIDEO_MEM_LIMIT_BYTES", str(256 * 1024 * 1024))

    # Act — try to allocate 1 GiB against a 256 MiB cap.
    result = await run_sandboxed(
        _python("x = bytearray(1024 * 1024 * 1024); print(len(x))"), cwd=tmp_path, timeout_s=30
    )

    # Assert — the cap fires (MemoryError), not a timeout or other error; the parent is untouched.
    assert not result.succeeded
    assert not result.timed_out
    assert "MemoryError" in result.stderr_tail
    assert "1073741824" not in result.stdout_tail
