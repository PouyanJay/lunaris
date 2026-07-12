from pydantic import BaseModel, ConfigDict, Field


class GeneralCoverFields(BaseModel):
    """The variables Claude fills in the GENERAL cover-prompt template — nothing more.

    The operator's course-cover prompt system is explicit about the division of labor: the LLM
    generates ONLY the fields; the full structured prompt is assembled deterministically and sent to
    the image model verbatim. This schema is that contract — a pipeline-internal parse target
    (snake_case ``BaseModel``, like ``CoverQaVerdict``), parsed with bounded repair turns so a
    malformed completion never fails a cover outright.

    It carries two halves. The ARTWORK fields describe the scene to depict. The TYPOGRAPHY
    fields are the text the image model renders INTO the cover (general-cover-typography): the
    references are *composed* covers — an eyebrow label, the title broken across lines with one
    line accented, a subtitle, three captioned badges, and small scientific callouts. GPT Image 2
    typesets text reliably, and the vision-QA gate verifies the title's spelling, so a garbled
    render is re-rolled rather than shipped.
    """

    model_config = ConfigDict(extra="forbid")

    # ---- artwork ----
    subject: str = Field(min_length=1)
    # Domain guardrails so the cover is not confidently wrong — the thing a subject-matter expert
    # would catch (e.g. 'keep eosinophils visually distinct from generic blood cells', 'do not
    # imply antibodies accumulate inside the airway lumen'). A cover that misteaches is worse
    # than a plain one, so these ride in the prompt AND the QA rubric.
    accuracy_requirements: list[str] = Field(default_factory=list, max_length=4)
    primary_visual: str = Field(min_length=1)
    supporting_visuals: str = Field(min_length=1)
    process_visualization: str = Field(min_length=1)

    # ---- typography the image model renders into the cover ----
    eyebrow: str = Field(min_length=1, max_length=40)
    # The course title split for typesetting — 2-4 short stacked lines, large, upper-left.
    title_lines: list[str] = Field(min_length=1, max_length=4)
    # Exactly one of ``title_lines`` (verbatim) is accented in amber; the rest stay white/ivory.
    highlight_line: str = Field(min_length=1)
    subtitle: str = Field(min_length=1, max_length=90)
    # Three captioned badges along the lower-left — each a short ALL-CAPS caption.
    badges: list[str] = Field(min_length=3, max_length=3)
    # Small scientific callout labels beside the artwork (e.g. IL-5, TLS, O(log n)). Capped at TWO
    # (was four): a cover is a poster, not a lecture slide — the first render read as a dense
    # infographic because every concept demanded its own labelled callout.
    callouts: list[str] = Field(default_factory=list, max_length=2)
