"""Trusted simulator supervisor. This process must never run in the API or generated sandbox."""

import asyncio
import os
import signal
from contextlib import suppress
from pathlib import Path

from lunaris_live.session import SupabaseSessionStore
from lunaris_live.sims.claude_model import ClaudeSimModel
from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.factory import SimFactory
from lunaris_live.sims.registry.supabase_asset_store import SupabaseSimAssetStore
from lunaris_live.sims.runtime.models.services import SimWorkerServices
from lunaris_live.sims.runtime.models.worker_context import SimWorkerContext
from lunaris_live.sims.runtime.supabase_queue import SupabaseSimQueue
from lunaris_live.sims.runtime.worker import SimWorker
from lunaris_runtime.logging import configure_logging

from ..config import get_settings
from ..dependencies import get_cost_event_store, get_subject_cost_store
from .dependencies import get_live_credential_resolver, resolve_strong_model
from .verify_sim_worker import verify_worker_environment


async def _run() -> None:
    settings = get_settings()
    image = os.environ["LUNARIS_SIM_VERIFIER_IMAGE"]
    if "@sha256:" not in image:
        raise ValueError("Pin the verifier image by digest")
    verifier = ContainerSimVerifier(
        image=image, seccomp=Path(os.environ["LUNARIS_SIM_SECCOMP_PATH"])
    )
    await verify_worker_environment(verifier)
    worker = SimWorker(
        SimWorkerServices(
            SupabaseSimQueue(),
            SupabaseSimAssetStore(),
            SimFactory(
                ClaudeSimModel(resolve_strong_model()),
                verifier,
            ),
        ),
        context=SimWorkerContext(
            sessions=SupabaseSessionStore(),
            credential_resolver=get_live_credential_resolver(settings),
            cost_events=get_cost_event_store(settings),
            subject_costs=get_subject_cost_store(settings),
            session_budget_s=settings.live_session_budget_s,
            session_budget_usd=settings.live_session_budget_usd,
        ),
    )
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    await asyncio.to_thread(Path("/tmp/lunaris-sim-ready").touch)
    while not stop.is_set():
        # Finish each bounded admitted build before shutdown.
        await worker.run_once()
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=2)


def main() -> None:
    configure_logging(json_output=True)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
