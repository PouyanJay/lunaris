from lunaris_grounding.assessors.claude import _parse_support


def test_parse_support_reads_score_and_citation() -> None:
    # Act
    support = _parse_support('Here: {"score": 0.82, "citation_id": "c3"}')

    # Assert
    assert support.score == 0.82
    assert support.citation_id == "c3"


def test_parse_support_treats_null_citation_as_unsupported() -> None:
    # Act
    support = _parse_support('{"score": 0.1, "citation_id": null}')

    # Assert
    assert support.citation_id is None
