"""A stuck external Docker client cannot turn a verifier deadline into an endless wait."""

import os
from pathlib import Path
from time import monotonic

from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.reference_app import reference_app
from lunaris_live.sims.schema.candidate import SimCandidate
from lunaris_live.sims.schema.teaching_spec import TeachingCase, TeachingSpec


async def test_a_stalled_daemon_is_bounded_and_never_approves(tmp_path, monkeypatch):
    # Exercise real subprocess timeout/termination against an unavailable Docker-compatible
    # command. This is an external dependency fixture, not a replacement of the verifier.
    executable = tmp_path / "docker"
    executable.write_text("#!/usr/bin/env python3\nimport signal\nsignal.pause()\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    policy = tmp_path / "policy.json"
    policy.write_text("{}")
    verifier = ContainerSimVerifier(image="unavailable", seccomp=Path(policy), timeout_s=0.1)
    spec = TeachingSpec(
        contract=reference_app().contract,
        source="reference",
        source_version="1",
        cases=[TeachingCase(state={"x": x}, outputs={"y": str(2 * x)}) for x in (0, 4, 10)],
    )
    started = monotonic()
    report = await verifier.verify(SimCandidate(html="<html></html>"), spec)
    assert monotonic() - started < 6
    assert not report.approved
    assert "timed out" in report.reasons[0]
