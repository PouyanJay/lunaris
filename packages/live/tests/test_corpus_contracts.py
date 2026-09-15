import pytest
from lunaris_live.graph.schema import ConceptGraph
from pydantic import ValidationError


def test_source_identity_is_validated_in_persisted_graphs() -> None:
    with pytest.raises(ValidationError):
        ConceptGraph.model_validate(
            {
                "graphId": "fixture",
                "topic": "Fractions",
                "corpus": {
                    "courseId": "fixture",
                    "title": "Fractions",
                    "digest": "invalid",
                    "runId": "run",
                },
            }
        )


def test_old_graphs_have_no_source_and_empty_asset_index() -> None:
    graph = ConceptGraph.model_validate(
        {
            "graphId": "fixture",
            "topic": "Fractions",
            "nodes": [{"id": "fraction", "name": "Fraction", "definition": "A part of a whole."}],
        }
    )
    assert graph.corpus is None
    assert graph.nodes[0].assets == []


def test_snapshot_bounds_and_unique_locators_protect_compiler_input() -> None:
    from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot

    source = {"courseId": "fixture", "title": "Fractions", "digest": "a" * 64, "runId": "run"}
    section = {"locator": "lesson:1", "text": "A part of a whole.", "kind": "lesson"}
    snapshot = CorpusSnapshot(source=source, sections=[section])
    assert isinstance(snapshot.sections, tuple)
    with pytest.raises(ValidationError, match="unique"):
        CorpusSnapshot(source=source, sections=[section, section])
    with pytest.raises(ValidationError, match="source budget"):
        CorpusSnapshot(
            source=source,
            sections=[
                {**section, "locator": f"lesson:{i}", "text": "x" * 20000} for i in range(11)
            ],
        )
    with pytest.raises(ValidationError):
        snapshot.source.title = "Changed"


def test_public_assets_cannot_carry_private_answers_or_signed_urls() -> None:
    from lunaris_live.corpus.schemas.asset import NodeAsset

    asset = {
        "assetId": "a",
        "kind": "lesson",
        "origin": "ingested",
        "locator": "lesson:1",
        "sourceDigest": "a" * 64,
    }
    for secret in [{"answerKey": "private"}, {"url": "https://example.test/?token=secret"}]:
        with pytest.raises(ValidationError):
            NodeAsset.model_validate({**asset, **secret})


@pytest.mark.parametrize(
    "locator", ["https://example.test/file?token=private", "lesson:1?key=private"]
)
def test_asset_locators_reject_urls_and_query_parameters(locator: str) -> None:
    from lunaris_live.corpus.schemas.asset import NodeAsset

    with pytest.raises(ValidationError):
        NodeAsset(
            asset_id="a", kind="lesson", origin="ingested", locator=locator, source_digest="a" * 64
        )
