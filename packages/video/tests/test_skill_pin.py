"""Skill-pin tests: the vendored explainer-video skill (v1.4) is verbatim and immutable.

The skill is a pinned dependency — its references are validated scar tissue (plan principle 1).
These fingerprints were taken when v1.4 was vendored; ANY edit to a pinned file turns this red.
An upstream skill update lands as an explicit version bump: re-vendor, re-fingerprint, one commit
that says so.

v1.2 → v1.3 (scene quality for the hard archetypes): the network/graph archetype + a complexity
budget in archetypes.md, the make_network recipe + pitfall P9 in manim-patterns.md, and the
hero_title / make_network helpers in assets/style_tokens.py — so the hook/title card and the
"web of nodes" render clean on the first pass, under the voiced narration.

v1.3 → v1.4 (codegen literal hardening): pitfalls P10 (malformed numeric literals — `2x` is the
real "invalid decimal literal", not `.5`/`5.`) and P11 (unterminated string literals — the #1
codegen parse failure) in manim-patterns.md, so the first render already parses instead of leaning
on a parse-repair turn.
"""

import hashlib

import pytest
from lunaris_video.skill import read_skill_asset, skill_asset_names

_REFERENCES_SHA256 = {
    "archetypes.md": "d4be1db0c79db4d3e06d6b0a89b48c28f75cc3984258a853481a51df01077d9a",
    "contract-schema.md": "a97dd8fe08edb4ea7ba46316c6513e13fced307b4b63833a62ddd41af2e60460",
    "manim-patterns.md": "d9b249522d7316f0b180fd3889e19a9455e18bc3bdabfae679c91540bb77ca1e",
    "narration-sync.md": "6c8e47d2f2e50a1b5a772463f4ce45f451dfabd28f6020c968dace3e61878f83",
    "qa-gates.md": "97bacc6dd96d8fe2050b25f5e9aa48aa7f48a3f5d83ebbde011d408a948cd789",
}

_PINNED_SHA256 = {
    "SKILL.md": "059f6959ac3766f7ecd10867caeb67f5d077df5828d008997c92ba7cb54e0b25",
    "assets/style_tokens.py": "3c42d3120c35d6d1d412b30f8c7778793348aac89b0044ed727178fd45984b75",
    **{f"references/{name}": sha for name, sha in _REFERENCES_SHA256.items()},
    "scripts/assemble.sh": "43129d3ea8cf75245bebadb7bd18830a5103b19171826d0a844ab3d5f090fcc8",
    "scripts/narration.py": "2b029aabdf862a12747940fda97d644ef56431b8ba80baa2d12e59d90f4e8d17",
    "scripts/render_and_qa.sh": "c578c9cdf8ccfb42f9da985b49c4c8f844da665994e41a0f629f96810fe14861",
    "scripts/setup_env.sh": "5646effa10883ff6b5f4f3f127cbdfebad3d8faed6774733fa37872e7818222d",
}


def test_vendored_skill_file_set_is_exactly_v1_4() -> None:
    # Arrange / Act
    names = skill_asset_names()

    # Assert — no file missing, no file smuggled in alongside the pin.
    assert sorted(names) == sorted(_PINNED_SHA256)


@pytest.mark.parametrize(("name", "expected"), sorted(_PINNED_SHA256.items()))
def test_vendored_skill_file_is_verbatim(name: str, expected: str) -> None:
    # Arrange / Act
    digest = hashlib.sha256(read_skill_asset(name).encode()).hexdigest()

    # Assert — byte-identical to the fingerprint taken at vendor time.
    assert digest == expected, f"pinned skill file edited: {name}"


def test_skill_assets_read_as_text() -> None:
    # Arrange / Act
    skill_md = read_skill_asset("SKILL.md")

    # Assert — the loader returns usable prompt-context text, not bytes or paths.
    assert "Explainer Video Pipeline" in skill_md
