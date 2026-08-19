"""Every image this repo ships is built where a break is cheap and promoted where it was built.

Two rules, both learned the expensive way in Lunaris Live's Phase 2b (T0: ``cd-dev`` failed at an
image build for two merges running, and nothing before the deploy had built that image):

1. **Every root ``Dockerfile.*`` is built and vulnerability-*gated* by ``ci.yml``.** CI is where an
   image break costs a red check on a pull request; ``cd-dev`` is where it costs a broken deploy of
   ``main``, hours later, with the code already merged. An image that only ``cd-*`` builds is an
   image whose first build of a change happens after review. "Gated" means the Trivy step in the
   *same job* runs with ``--exit-code 1``: a scan that logs and never fails is not a gate.

2. **Every image ``cd-dev.yml`` pushes, ``cd-prod.yml`` promotes** (``az acr import`` of the same
   repository name), build-once-promote. An image dev builds and prod does not import is a service
   that silently never reaches production, or that prod rebuilds from source, which is the one thing
   the promotion design exists to prevent. And every root Dockerfile is one ``cd-dev`` pushes: a
   file CI builds but CD never ships is a service that passes review and runs nowhere (the state
   ``apps/copilot`` was in from T1 to T7).

Read from the workflow files as data (their ``uses:``/``with:``/``run:`` blocks), not from
comments, so a step commented out still fails here.

**What this does not catch.** A workflow that builds the right file with the wrong context; a
``cd-*`` step whose ``if:`` gate is never true in any environment; and a Dockerfile under a
subdirectory (``infra/inference/``) is out of scope: those images have their own workflow
(``cd-inference.yml``) and cadence.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# The images this repo ships from its root, spelled out so the sweep is proven to *find* them: every
# other assertion here is of the form "nothing missing", which a sweep that found no Dockerfiles
# satisfies trivially. Adding an image means adding it here as well as wiring it, deliberately.
ROOT_IMAGES = {"Dockerfile.api", "Dockerfile.copilot", "Dockerfile.cover", "Dockerfile.worker"}

# `echo "name=value" >> "$GITHUB_OUTPUT"`: how a step publishes an output another step reads back
# as `${{ steps.<id>.outputs.<name> }}`; cd-dev computes the API image reference this way.
_STEP_OUTPUT_ECHO = re.compile(r'echo\s+"?(\w+)=([^"\n]+?)"?\s*>>\s*"?\$GITHUB_OUTPUT')
# `az acr import … --source "<repository>:<tag>"`: cd-prod's promotion of a dev-built image.
_ACR_IMPORT_SOURCE = re.compile(r'az\s+acr\s+import\b[^;&|]*?--source\s+"?([\w-]+):')


def _workflow(name: str) -> dict:
    with (WORKFLOWS / name).open("rb") as handle:
        return yaml.safe_load(handle)


def _jobs(workflow: dict) -> dict[str, list[dict]]:
    """Job name → its steps."""
    return {name: job.get("steps", []) for name, job in workflow["jobs"].items()}


def _steps(workflow: dict) -> list[dict]:
    return [step for steps in _jobs(workflow).values() for step in steps]


def _root_dockerfiles() -> set[str]:
    return {path.name for path in REPO_ROOT.glob("Dockerfile.*")}


def _flattened_run(step: dict) -> str:
    """A ``run:`` block as one line (backslash continuations joined), or ``""``."""
    run = step.get("run") or ""
    return " ".join(line.rstrip("\\").strip() for line in run.splitlines())


def _docker_builds(steps: list[dict]) -> list[dict]:
    """The ``with:`` blocks of ``docker/build-push-action`` steps."""
    return [
        step["with"]
        for step in steps
        if str(step.get("uses", "")).startswith("docker/build-push-action") and "with" in step
    ]


def _tags_of(build: dict) -> set[str]:
    """Every tag a build step applies (``tags:`` may be a multi-line block)."""
    return {tag.strip() for tag in str(build.get("tags", "")).splitlines() if tag.strip()}


def _trivy_gated_tags(steps: list[dict]) -> set[str]:
    """Image tags the job's Trivy steps scan *and fail on*.

    The scanned image is the command's final argument. A step whose scan cannot fail the job
    (no ``--exit-code 1``) is not counted: it reports vulnerabilities and gates nothing."""
    tags: set[str] = set()
    for step in steps:
        command = _flattened_run(step)
        if "trivy" in command and "--exit-code 1" in command:
            tags.add(command.split()[-1])
    return tags


def _step_outputs(workflow: dict) -> dict[str, str]:
    """``steps.<id>.outputs.<name>`` → the value a ``run:`` step echoes into ``$GITHUB_OUTPUT``."""
    outputs: dict[str, str] = {}
    for step in _steps(workflow):
        if step_id := step.get("id"):
            for match in _STEP_OUTPUT_ECHO.finditer(step.get("run") or ""):
                outputs[f"steps.{step_id}.outputs.{match.group(1)}"] = match.group(2)
    return outputs


def _repository_of(reference: str) -> str:
    """``lunaris-api`` from ``<acr>/lunaris-api:<sha>`` (host and tag may be expressions)."""
    return reference.rsplit("/", 1)[-1].split(":", 1)[0]


def _pushed_builds(workflow: dict) -> list[dict]:
    return [
        build
        for build in _docker_builds(_steps(workflow))
        if str(build.get("push", "false")).lower() == "true"
    ]


def _pushed_repositories(workflow: dict) -> set[str]:
    """Repository names (``lunaris-api`` in ``<acr>/lunaris-api:<sha>``) cd-dev pushes."""
    outputs = _step_outputs(workflow)
    repositories: set[str] = set()
    for build in _pushed_builds(workflow):
        for tag in _tags_of(build):
            for expression, value in outputs.items():
                tag = tag.replace("${{ " + expression + " }}", value)
            repositories.add(_repository_of(tag))
    return repositories


def _promoted_repositories(workflow: dict) -> set[str]:
    """Repository names cd-prod imports with ``az acr import --source <repo>:<tag>``."""
    return {
        match.group(1)
        for step in _steps(workflow)
        for match in _ACR_IMPORT_SOURCE.finditer(_flattened_run(step))
    }


def test_the_sweep_actually_finds_the_root_dockerfiles() -> None:
    # Guards the guard: every other test asserts an empty "missing" list, which a glob that matched
    # nothing would satisfy. Naming the images makes adding one a deliberate act, here and in CI.
    assert _root_dockerfiles() == ROOT_IMAGES


def test_every_root_dockerfile_is_built_by_ci() -> None:
    built = {str(build["file"]) for build in _docker_builds(_steps(_workflow("ci.yml")))}

    unbuilt = sorted(_root_dockerfiles() - built)
    assert unbuilt == [], f"Dockerfiles ci.yml never builds: {unbuilt}"


def test_every_image_ci_builds_is_trivy_gated_in_the_same_job() -> None:
    # Per job, not per workflow: a tag string scanned in one job must not vouch for an unscanned
    # build of the same string in another.
    ungated: list[str] = []
    for job, steps in _jobs(_workflow("ci.yml")).items():
        gated = _trivy_gated_tags(steps)
        ungated.extend(
            f"{build['file']} (job {job})"
            for build in _docker_builds(steps)
            if not _tags_of(build) & gated
        )

    assert ungated == [], f"images ci.yml builds without a failing Trivy scan: {ungated}"


def test_every_root_dockerfile_is_pushed_by_cd_dev() -> None:
    shipped = {str(build["file"]) for build in _pushed_builds(_workflow("cd-dev.yml"))}

    unshipped = sorted(_root_dockerfiles() - shipped)
    assert unshipped == [], f"Dockerfiles cd-dev.yml never pushes: {unshipped}"


def test_every_image_cd_dev_pushes_is_promoted_by_cd_prod() -> None:
    pushed = _pushed_repositories(_workflow("cd-dev.yml"))
    promoted = _promoted_repositories(_workflow("cd-prod.yml"))

    assert pushed, "cd-dev.yml pushes no images: the workflow shape this guard reads has changed"
    unpromoted = sorted(pushed - promoted)
    assert unpromoted == [], f"images cd-dev pushes that cd-prod never imports: {unpromoted}"
