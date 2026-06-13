"""Live acceptance for the V0 job spine — the real infrastructure, end to end.

The hermetic suites prove every seam against doubles; this one proves the spine on the actual
stack: a job enqueued into the real ``video_jobs`` table is claimed through the real
``claim_video_job`` RPC, the stub artifacts land in the real private ``course-videos`` bucket, the
signed URL actually serves playable MP4 bytes over HTTP, and the lifecycle trail sits in the real
``run_events`` table under ``run_id = job_id`` — one id across queue → worker → storage → log.

Gated like the other live suites (eval mark; needs ``SUPABASE_DB_URL`` + ``SUPABASE_URL`` +
``SUPABASE_SERVICE_ROLE_KEY`` — the local stack provides all three). Fixtures are committed
(cross-connection visibility) and reaped in ``finally``: deleting the auth user cascades the job
rows; event rows and storage objects are removed explicitly.
"""

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

psycopg = pytest.importorskip("psycopg")

from lunaris_runtime.persistence import (  # noqa: E402
    SupabaseRunEventStore,
    SupabaseVideoJobQueue,
    SupabaseVideoStorage,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind  # noqa: E402
from lunaris_video import StubVideoPipeline, VideoWorker  # noqa: E402

_DB_URL = os.environ.get("SUPABASE_DB_URL", "")
_API_URL = os.environ.get("SUPABASE_URL", "")
_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not (_DB_URL and _API_URL and _SERVICE_KEY),
        reason="SUPABASE_DB_URL / SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not all set",
    ),
]


@pytest.fixture
async def live_owner() -> AsyncIterator[str]:
    """A real auth user, committed, reaped afterwards (the cascade reaps their jobs too)."""
    owner = str(uuid.uuid4())
    setup = psycopg.connect(_DB_URL, autocommit=True)
    try:
        setup.execute("insert into auth.users (id) values (%s)", (owner,))
        yield owner
    finally:
        setup.execute("delete from auth.users where id = %s", (owner,))
        setup.close()


async def test_the_job_spine_end_to_end_on_the_real_stack(live_owner: str) -> None:
    # Arrange — the real stores, exactly as the API process composes them.
    queue = SupabaseVideoJobQueue()
    storage = SupabaseVideoStorage()
    events = SupabaseRunEventStore()
    worker = VideoWorker(
        queue=queue,
        pipeline=StubVideoPipeline(),
        storage=storage,
        events=events,
        worker_id="acceptance-worker",
    )
    job = VideoJob(
        id=uuid.uuid4().hex,
        user_id=live_owner,
        course_id="acceptance-course",
        lesson_id="acceptance-lesson",
        kind=VideoKind.LESSON,
        input_hash="acceptance",
    )
    paths = VideoArtifactPaths.for_job(job)
    cleanup = psycopg.connect(_DB_URL, autocommit=True)
    try:
        # Act — enqueue → claim+produce+upload+settle (one real worker pass).
        await queue.enqueue(job)
        assert await worker.run_once() is True

        # Assert — the job settled READY in the real table.
        settled = await queue.get(job_id=job.id, owner_id=live_owner)
        assert settled is not None and settled.status == VideoJobStatus.READY

        # The signed URL serves real, playable MP4 bytes from the private bucket.
        video_url = await storage.signed_url(path=paths.mp4)
        async with httpx.AsyncClient() as http:
            response = await http.get(video_url)
        assert response.status_code == 200, response.text
        assert response.content[4:8] == b"ftyp"
        assert len(response.content) > 1000

        # The lifecycle trail is in the real run_events table under run_id = job_id.
        trail = await events.list_for_run(run_id=job.id, owner_id=live_owner)
        assert [event.payload.get("status") for event in trail] == ["planning", "ready"]
        assert all(event.payload.get("jobId") == job.id for event in trail)
    finally:
        # Each cleanup tier is guarded independently — a DB hiccup must not strand bucket objects.
        try:
            cleanup.execute("delete from public.run_events where run_id = %s", (job.id,))
        finally:
            cleanup.close()
            # Storage rows are trigger-protected against direct SQL deletes — reap via the API.
            from supabase import create_client

            create_client(_API_URL, _SERVICE_KEY).storage.from_("course-videos").remove(
                [paths.mp4, paths.poster]
            )
