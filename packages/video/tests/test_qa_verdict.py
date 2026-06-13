"""QaVerdict schema tests: passed and defects are kept consistent by construction, so a
malformed vision completion can never become a silently-shipped broken scene."""

import pytest
from lunaris_video.schemas import QaDefect, QaVerdict
from pydantic import ValidationError


def test_clean_verdict_has_no_defects() -> None:
    # Arrange / Act
    verdict = QaVerdict(passed=True)

    # Assert
    assert verdict.passed
    assert verdict.defects == []


def test_failing_verdict_carries_defects() -> None:
    # Arrange / Act
    verdict = QaVerdict(
        passed=False,
        defects=[QaDefect(issue="turbine blades detached from nacelle", fix_hint="add a pivot")],
    )

    # Assert
    assert not verdict.passed
    assert verdict.defects[0].issue.startswith("turbine")


def test_passed_with_defects_is_rejected() -> None:
    # Arrange / Act / Assert — the contradiction the vision model must never smuggle through.
    with pytest.raises(ValidationError):
        QaVerdict(passed=True, defects=[QaDefect(issue="overlap", fix_hint="space them")])


def test_failed_with_no_defects_is_rejected() -> None:
    # Arrange / Act / Assert — a failing verdict must name what is wrong, else repair is blind.
    with pytest.raises(ValidationError):
        QaVerdict(passed=False)


def test_verdict_round_trips_through_json() -> None:
    # Arrange
    verdict = QaVerdict(
        passed=False, defects=[QaDefect(issue="text clipped at edge", fix_hint="add margin")]
    )

    # Act
    restored = QaVerdict.model_validate_json(verdict.model_dump_json())

    # Assert
    assert restored == verdict
