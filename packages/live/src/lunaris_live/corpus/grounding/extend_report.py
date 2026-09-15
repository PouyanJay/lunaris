from ..schemas.grounding_report import GroundingReport, NodeGrounding


def extend_report(
    report: GroundingReport | None, added: list[str], *, run_id: str
) -> GroundingReport | None:
    if report is None:
        return None
    return report.model_copy(
        update={
            "run_id": run_id,
            "status": "failed",
            "nodes": (
                *report.nodes,
                *(
                    NodeGrounding(node_id=node_id, classification="unsupported")
                    for node_id in added
                ),
            ),
            "issues": tuple(dict.fromkeys((*report.issues, "extension_unverified"))),
        }
    )
