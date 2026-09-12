import asyncio
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

import structlog

from .content_hash import content_hash
from .sandbox_policy import SIM_CSP
from .schema.candidate import SimCandidate
from .schema.teaching_spec import TeachingSpec
from .schema.verification_report import VerificationReport


class ContainerSimVerifier:
    """Run only candidate data in a disposable, credential-free, networkless container."""

    def __init__(self, *, image: str, seccomp: Path, timeout_s: float = 30) -> None:
        self._image = image
        self._seccomp = seccomp.resolve(strict=True)
        self._timeout = timeout_s

    async def verify(self, candidate: SimCandidate, spec: TeachingSpec) -> VerificationReport:
        started = monotonic()
        payload = {"html": candidate.html, "spec": spec.model_dump(by_alias=True), "csp": SIM_CSP}
        result = await self._run(json.dumps(payload, ensure_ascii=False).encode())
        report = VerificationReport(
            content_hash=content_hash(candidate.html),
            spec_hash=content_hash(spec.model_dump_json(by_alias=True)),
            approved=result.get("approved") is True,
            checks_passed=result.get("checks_passed", 0),
            reasons=result.get("reasons", ["Verifier returned no evidence."]),
            elapsed_ms=int((monotonic() - started) * 1000),
            screenshots=result.get("screenshots", []),
        )
        structlog.get_logger().info(
            "live.sim.verified",
            content_hash=report.content_hash,
            approved=report.approved,
            checks_passed=report.checks_passed,
            elapsed_ms=report.elapsed_ms,
        )
        return report

    def _command(self, name: str) -> list[str]:
        return [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--init",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--security-opt=seccomp={self._seccomp}",
            "--user=1000:1000",
            "--memory=768m",
            "--cpus=1",
            "--pids-limit=128",
            "--shm-size=128m",
            "--tmpfs=/tmp:rw,nosuid,nodev,size=128m,mode=1777",
            "--log-driver=none",
            "-i",
            self._image,
        ]

    async def _run(self, payload: bytes) -> dict:
        if len(payload) > 500_000:
            return {"reasons": ["Candidate payload exceeds the byte limit."]}
        name = f"lunaris-sim-verify-{uuid4().hex}"
        process = await asyncio.create_subprocess_exec(
            *self._command(name),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(self._timeout):
                stdout, _ = await process.communicate(payload)
            if process.returncode != 0:
                return {"reasons": ["Verifier process failed."]}
            result = json.loads(stdout)
            return result if isinstance(result, dict) else {"reasons": ["Invalid verifier report."]}
        except (TimeoutError, ValueError):
            return {"reasons": ["Verifier timed out or returned an invalid report."]}
        finally:
            try:
                await self._remove(name)
            finally:
                await self._stop(process)

    async def _remove(self, name: str) -> None:
        cleanup = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(3):
                await cleanup.wait()
        except TimeoutError:
            structlog.get_logger().error("live.sim.cleanup_failed", container_name=name)
        finally:
            await self._stop(cleanup)

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.kill()
        try:
            async with asyncio.timeout(1):
                await process.wait()
        except TimeoutError:
            structlog.get_logger().error("live.sim.process_reap_failed", pid=process.pid)
