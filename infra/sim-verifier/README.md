# Simulator verification appliance

Build with `docker build -f infra/sim-verifier/Dockerfile -t lunaris-sim-verifier:test .`.
Run the real safety/relationship fixtures with
`uv run pytest tests/browser/test_sim_verifier.py -m browser -q`.

`ContainerSimVerifier` launches a fresh non-root container per candidate. It has no
network, host mounts, credentials, Linux capabilities, writable root filesystem,
or shared browser profile. CPU, memory, process count, temporary storage and wall
time are bounded. Cancellation kills the container. Do not mount the Docker socket
inside an application or browser container; this adapter belongs in a dedicated
trusted execution supervisor. Production deployment is wired by the integration
ticket, not this appliance slice.

Chromium's sandbox stays enabled. The seccomp profile comes from
[Playwright v1.62.0](https://github.com/microsoft/playwright/blob/v1.62.0/utils/docker/seccomp_profile.json),
under its Apache 2.0 license. It permits user namespace setup; we additionally
allow the `chroot` syscall, which Chromium needs inside its own user namespace.
The container has no `SYS_CHROOT` capability in its outer namespace.

The trusted runner serves candidate bytes only to an opaque iframe under the
same CSP used for approved runtime bundles. Routes block all external requests;
CSP blocks scripts/assets from external origins, connections, nested frames,
workers, forms and base URLs. Browser storage is unavailable in the opaque origin.
The host never evaluates generated JavaScript directly.

Teaching cases are supplied independently of the bundle. Each declares parameter
states and exact visible output text. Bundles expose controls through
`data-sim-param`, outputs through `data-sim-output`, and the discussion action
through `data-sim-action="discuss"`. The verifier changes controls, inspects visible
consequences, checks learner events, and verifies a tutor command updates controls.
Cases need three distinct states; this is evidence for the specified relationships,
not a proof of every possible behavior. Reports bind the candidate and teaching
specification hashes to verifier version, checks, rejection reasons and latency.
Only matching passing evidence crosses the `VerifiedBundle` publication boundary.

There is deliberately no credential-bearing fallback to host-side Playwright when
the container runtime is unavailable. Generation must fall back to the ordinary
teaching surface when verification cannot run.
