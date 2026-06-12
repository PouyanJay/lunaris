"""DeviceBridge failure semantics (device-build-bridge T1).

The bridge is the contract between a build and the learner's tab: completions must be served
while the tab polls, and must FAIL — promptly and with a clear error — when the tab goes silent
(closed / laptop asleep), when a claimed completion is never answered, or when the run is torn
down. A hung build is the one unacceptable outcome.
"""

import asyncio

import pytest
from lunaris_runtime.device_bridge import (
    BridgeLimits,
    DeviceBridge,
    DeviceBridgeDisconnectedError,
)

_MESSAGES = [{"role": "user", "content": "ping"}]


async def test_completion_roundtrip_serves_the_tabs_text() -> None:
    # Arrange — a bridge with relaxed limits and a "tab" serving one completion.
    bridge = DeviceBridge(run_id="run-1")

    async def tab() -> None:
        claimed = await bridge.claim(wait_s=1.0)
        bridge.resolve(claimed[0].request_id, "pong")

    tab_task = asyncio.create_task(tab())

    # Act — the model side parks a completion and awaits the tab's answer.
    text = await bridge.complete(_MESSAGES)

    # Assert
    assert text == "pong"
    await tab_task


async def test_silent_tab_fails_the_completion() -> None:
    # Arrange — a tab that NEVER polls (closed before the build's first completion).
    bridge = DeviceBridge(run_id="run-1", limits=BridgeLimits(liveness_s=0.05))

    # Act / Assert — the completion fails with the disconnect error instead of hanging.
    with pytest.raises(DeviceBridgeDisconnectedError):
        await bridge.complete(_MESSAGES)


async def test_polling_keeps_the_completion_alive_past_the_liveness_window() -> None:
    # Arrange — liveness shorter than the answer time, but the tab keeps polling while its
    # (slow) on-device model works, so the bridge must NOT count it as disconnected.
    bridge = DeviceBridge(run_id="run-1", limits=BridgeLimits(liveness_s=0.15))
    answered = asyncio.Event()

    async def tab() -> None:
        claimed = await bridge.claim(wait_s=1.0)
        for _ in range(6):  # keep polling (empty claims) well past the liveness window
            await bridge.claim(wait_s=0.05)
        bridge.resolve(claimed[0].request_id, "slow but alive")
        answered.set()

    tab_task = asyncio.create_task(tab())

    # Act
    text = await bridge.complete(_MESSAGES)

    # Assert — the answer landed after ~0.3s of polling, double the 0.15s liveness window.
    assert text == "slow but alive"
    assert answered.is_set()
    await tab_task


async def test_claimed_but_never_answered_completion_times_out() -> None:
    # Arrange — the tab claims the request and keeps polling (alive) but never posts a result
    # (a wedged on-device engine). The completion bound, not liveness, must end the wait.
    bridge = DeviceBridge(
        run_id="run-1", limits=BridgeLimits(liveness_s=10.0, completion_timeout_s=0.05)
    )

    async def tab() -> None:
        await bridge.claim(wait_s=1.0)  # claims, never answers

    tab_task = asyncio.create_task(tab())

    # Act / Assert
    with pytest.raises(DeviceBridgeDisconnectedError):
        await bridge.complete(_MESSAGES)
    await tab_task


async def test_fail_pending_unblocks_the_model_side() -> None:
    # Arrange — a completion in flight when the run is torn down.
    bridge = DeviceBridge(run_id="run-1")
    completion = asyncio.create_task(bridge.complete(_MESSAGES))
    claimed = await bridge.claim(wait_s=1.0)

    # Act — teardown fails whatever is pending.
    bridge.fail_pending("the build ended")

    # Assert — the model side is unblocked with the disconnect error, and a late tab answer
    # is rejected (the request is no longer pending).
    with pytest.raises(DeviceBridgeDisconnectedError):
        await completion
    assert bridge.resolve(claimed[0].request_id, "too late") is False


async def test_resolving_an_unknown_request_is_rejected() -> None:
    # Arrange — a bridge with nothing pending.
    bridge = DeviceBridge(run_id="run-1")

    # Act / Assert — an unknown request id is rejected, never silently swallowed.
    assert bridge.resolve("no-such-request", "text") is False


async def test_one_polling_tab_serves_concurrent_completions() -> None:
    # Arrange — the scripted runner can park several completions at once (parallel subagents);
    # a single tab serves them from one poll loop, matching results to ids.
    bridge = DeviceBridge(run_id="run-1")

    async def tab() -> None:
        answered = 0
        while answered < 3:
            for request in await bridge.claim(wait_s=1.0):
                content = request.messages[0]["content"]
                bridge.resolve(request.request_id, f"echo:{content}")
                answered += 1

    tab_task = asyncio.create_task(tab())

    # Act — three completions in flight together. (gather schedules all three complete() calls —
    # and their synchronous put_nowait enqueues — before the tab task first runs, so the tab's
    # claim drains a non-empty queue; no timing involved, just cooperative scheduling.)
    replies = await asyncio.gather(
        bridge.complete([{"role": "user", "content": "a"}]),
        bridge.complete([{"role": "user", "content": "b"}]),
        bridge.complete([{"role": "user", "content": "c"}]),
    )

    # Assert — every completion got ITS OWN answer (ids matched, no cross-wiring).
    assert replies == ["echo:a", "echo:b", "echo:c"]
    await tab_task
