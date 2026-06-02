"""Tolerant JSON loader: repairs the common live-model malformations so one delimiter slip in a
large structured response doesn't crash a course build (the real failure seen in production)."""

import json

import pytest
from lunaris_agent.subagents.json_tolerant import loads_tolerant


def test_passes_valid_json_through_unchanged() -> None:
    # Arrange / Act / Assert — well-formed JSON parses exactly as json.loads would.
    assert loads_tolerant('{"a": [1, 2], "b": "x"}') == {"a": [1, 2], "b": "x"}


def test_repairs_a_missing_comma() -> None:
    # Arrange — the exact failure class seen live: "Expecting ',' delimiter" between two members.
    malformed = '{"a": 1 "b": 2}'

    # Act / Assert — the loader repairs the slip rather than crashing the build.
    assert loads_tolerant(malformed) == {"a": 1, "b": 2}


def test_repairs_a_truncated_object() -> None:
    # Arrange — a response cut off mid-object.
    truncated = '{"modules": [{"title": "M"'

    # Act / Assert — the part the model did emit is recovered.
    assert loads_tolerant(truncated) == {"modules": [{"title": "M"}]}


def test_reraises_on_unsalvageable_text() -> None:
    # Act / Assert — prose with no JSON is a real failure; surface it for the caller's no-JSON path.
    with pytest.raises(json.JSONDecodeError):
        loads_tolerant("sorry, I can't help with that")
