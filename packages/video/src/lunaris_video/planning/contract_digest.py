from lunaris_video.models.sibling_contract_digest import SiblingContractDigest
from lunaris_video.schemas import ChapteredSceneContracts, SceneContracts

# Notable on-screen objects are capped so an upstream's digest stays compact in the prompt; the
# first few carry the terms a downstream lesson should reuse, the long tail is noise, not signal.
_MAX_KEY_TERMS = 8


def digest_of(
    lesson_title: str, contract: SceneContracts | ChapteredSceneContracts
) -> SiblingContractDigest:
    """Compact an upstream video's scene contract into a ``SiblingContractDigest`` for the planner.

    Pulls the topic (what the video covers), its visual archetypes (so the downstream stays visually
    consistent), and the notable on-screen objects it introduced (so the downstream reuses the same
    terms instead of re-defining them) — not the whole storyboard. Works for a flat lesson contract
    or a chaptered overview (both expose ``topic``, ``visual_archetypes_used``, and flattened
    ``scenes``).
    """
    used = (archetype.strip() for archetype in contract.visual_archetypes_used if archetype.strip())
    archetypes = tuple(dict.fromkeys(used))
    key_terms: list[str] = []
    for scene in contract.scenes:
        for obj in scene.objects:
            term = obj.strip()
            if term and term not in key_terms:
                key_terms.append(term)
            if len(key_terms) >= _MAX_KEY_TERMS:
                break
        if len(key_terms) >= _MAX_KEY_TERMS:
            break
    return SiblingContractDigest(
        lesson_title=lesson_title,
        covers=contract.topic,
        archetypes=archetypes,
        key_terms=tuple(key_terms),
    )
