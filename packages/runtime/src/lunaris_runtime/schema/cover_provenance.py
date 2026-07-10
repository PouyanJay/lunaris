from .base import CourseModel
from .enums import CoverStylePreset


class CoverProvenance(CourseModel):
    """Where a generated course cover came from — provenance is structural (CLAUDE.md contract).

    Built at the source (the cover pipeline, once the image has rendered and passed the Claude
    vision-QA gate) and carried untouched through worker → storage → API. ``source`` and ``model``
    say which image model drew it; ``art_director_model`` and ``qa_model`` name the Claude models
    that wrote the house-style prompt and inspected the result (the anti-slop loop); ``prompt`` is
    the exact art-direction prompt sent to the image model; ``qa_attempts`` counts how many
    render → QA rounds it took to pass; ``input_hash`` fingerprints the generation inputs; and
    ``generated_at`` is when the pipeline produced the image. An integration test asserts these are
    populated, not just that an image exists.
    """

    job_id: str
    course_id: str
    # The image provider that drew the cover — literal, not model recall (only OpenAI today).
    source: str = "openai"
    model: str  # e.g. "gpt-image-2"
    art_director_model: str  # the Claude model that wrote the house-style prompt
    qa_model: str  # the Claude model that vision-QA'd the result
    style_preset: CoverStylePreset
    prompt: str  # the final art-direction prompt sent to the image model
    qa_attempts: int = 1  # render → QA rounds until the image passed (>=1)
    input_hash: str
    # ISO-8601 instant, stamped when the pipeline produced the image — a string to match the sibling
    # provenance timestamp convention (Citation.fetched_at / VideoProvenance.generated_at).
    generated_at: str
