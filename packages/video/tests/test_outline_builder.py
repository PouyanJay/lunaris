from lunaris_video.assembly.outline_builder import build_video_outline
from lunaris_video.schemas.beat import Beat
from lunaris_video.schemas.scene_contract import SceneContract
from lunaris_video.schemas.scene_contracts import SceneContracts
from lunaris_video.schemas.timing_manifest import BeatTiming, SceneTiming, TimingManifest
from lunaris_video.style import video_global_style


def _contracts() -> SceneContracts:
    return SceneContracts(
        topic="Binary search",
        audience="intermediate",
        visual_archetypes_used=["number_line"],
        asset_strategy="tier-a procedural",
        global_style=video_global_style(),
        scenes=[
            SceneContract(
                id="S1_the_coastline",
                archetype="number_line",
                narration="A coastline has no single length.",
                objects=["line"],
                beats=[
                    Beat(id="b1", action="draw", narration="A coastline has no single length."),
                ],
                sources=["framing only - no empirical claims"],
                duration_s=3.0,
            ),
            SceneContract(
                id="S2_self_similarity",
                archetype="fractal",
                narration="Parts resemble the whole.",
                objects=["koch"],
                beats=[
                    Beat(id="b1", action="zoom", narration="Parts resemble the whole."),
                    Beat(id="b2", action="pause", narration="", min_visual_s=0.5),
                ],
                sources=["framing only - no empirical claims"],
                duration_s=4.0,
            ),
        ],
    )


def _timing(*, voiced: bool) -> TimingManifest:
    clip = "x.mp3" if voiced else None
    return TimingManifest(
        {
            "S1_the_coastline": SceneTiming(
                beats=[
                    BeatTiming(id="b1", audio_s=2.0, anim_s=2.0, audio=clip, estimated=not voiced)
                ],
                total_s=2.0,
            ),
            "S2_self_similarity": SceneTiming(
                beats=[
                    BeatTiming(id="b1", audio_s=3.0, anim_s=3.0, audio=clip, estimated=not voiced),
                    BeatTiming(id="b2", audio_s=0.0, anim_s=0.5, audio=None, estimated=not voiced),
                ],
                total_s=3.5,
            ),
        }
    )


def test_chapters_span_contiguous_scene_windows() -> None:
    # Arrange / Act
    outline = build_video_outline(_contracts(), _timing(voiced=True))

    # Assert — one chapter per scene, contiguous on the concatenated timeline (scene window +
    # its closing fade), with derived titles from the scene slug.
    assert [c.id for c in outline.chapters] == ["S1_the_coastline", "S2_self_similarity"]
    assert outline.chapters[0].title == "The coastline"
    assert outline.chapters[0].start_s == 0.0
    # Scene 1: one 2.0s beat + the close fade → chapter 2 begins where chapter 1 ends.
    assert outline.chapters[1].start_s == outline.chapters[0].end_s
    assert outline.chapters[0].end_s > 2.0  # includes the fade


def test_transcript_has_one_cue_per_spoken_beat_when_voiced() -> None:
    # Arrange / Act
    outline = build_video_outline(_contracts(), _timing(voiced=True))

    # Assert — the silent b2 beat contributes no cue; timings are on the global timeline.
    assert [cue.text for cue in outline.transcript] == [
        "A coastline has no single length.",
        "Parts resemble the whole.",
    ]
    assert outline.transcript[0].start_s == 0.0
    assert outline.transcript[0].end_s == 2.0


def test_a_silent_video_has_chapters_but_no_transcript() -> None:
    # Arrange / Act — an estimate (silent) manifest carries no audio clips.
    outline = build_video_outline(_contracts(), _timing(voiced=False))

    # Assert — navigation still works; there are just no spoken cues to sync.
    assert len(outline.chapters) == 2
    assert outline.transcript == []


def test_an_authored_scene_title_wins_over_the_derived_one() -> None:
    # Arrange — a scene carries an explicit title (planner-authored, C3).
    contracts = _contracts()
    contracts.scenes[0].title = "Why length is slippery"

    # Act
    outline = build_video_outline(contracts, _timing(voiced=True))

    # Assert
    assert outline.chapters[0].title == "Why length is slippery"
