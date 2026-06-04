from lunaris_runtime.schema import CourseBrief, Module, ResourceKind


def build_resource_queries(
    module: Module, brief: CourseBrief | None = None
) -> list[tuple[ResourceKind, str]]:
    """Narrow per-kind searches for a module's lesson, each tagged with the kind it targets (P7.4).

    Deterministic — query *planning* needs no model call, only the relevance judge does (cheaper +
    testable, and the searches stay narrow rather than open-ended). Anchored on the module's
    researched competency when present, else its title; the subject biases the topic. The kind tag
    routes a ``VIDEO`` query to the ``IVideoSource`` and the rest to the shared search.
    """
    topic = module.competency or module.title
    subject = f" {brief.subject}" if brief is not None and brief.subject else ""
    return [
        (ResourceKind.VIDEO, f"{topic} video tutorial"),
        (ResourceKind.ARTICLE, f"{topic}{subject} explained"),
        (ResourceKind.PRACTICE, f"{topic} practice exercises"),
        (ResourceKind.DOCS, f"{topic} reference documentation"),
    ]
