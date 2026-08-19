from typing import ClassVar, Self

from pydantic import Field, model_validator

from ...graph.schema.base import LiveModel
from .layout_block import LayoutBlock

#: The id every layout's outermost block must carry, which is A2UI v0.9's own rule. Fixed rather
#: than named per layout so a renderer knows where to start without being told.
_ROOT = "root"

#: Which catalog these component names belong to. Versioned, because the browser and the API are
#: deployed separately: a build that has never heard of ``lunaris.live.layout/v2`` must be able to
#: say so rather than render half a lesson.
_CATALOG = "lunaris.live.layout/v1"


class LayoutSpec(LiveModel):
    """A Tier 2 lesson layout: flat, catalog-bound blocks and the order they are read in.

    A2UI v0.9's grammar rather than a tree — components are a flat list, children are id references,
    and the root is the block called ``root``. That shape is what makes a layout streamable, what
    keeps a renderer from recursing through a structure it did not build, and what lets a future
    composition arrive a block at a time.

    Nothing here is free-form. ``LayoutBlock`` is the allow-list (R6), and the validators below
    close the gaps the type cannot: a layout that names a child it does not contain, or reuses an
    id, or strands a block nothing points at, describes something no renderer can draw — and the
    honest moment to find that out is when it is built, not when a learner is looking at the hole.
    """

    #: A2UI's root convention, exposed so composers and tests name the same thing.
    ROOT: ClassVar[str] = _ROOT
    CATALOG: ClassVar[str] = _CATALOG

    catalog_id: str = Field(default=_CATALOG, min_length=1, max_length=100)
    blocks: list[LayoutBlock] = Field(min_length=1)

    @model_validator(mode="after")
    def _is_drawable(self) -> Self:
        by_id: dict[str, LayoutBlock] = {}
        for block in self.blocks:
            if block.id in by_id:
                raise ValueError(f"block id {block.id!r} appears twice in one layout")
            by_id[block.id] = block

        if _ROOT not in by_id:
            raise ValueError(f"a layout needs a block with id {_ROOT!r}")

        reachable = _reachable_from(by_id)
        # Checked in both directions on purpose. A missing child is a hole the renderer would draw
        # nothing into; an unreachable block is material the composer meant to show and nobody will
        # ever see. The second is the quieter failure, which is why it is not left to inspection.
        stranded = set(by_id) - reachable
        if stranded:
            raise ValueError(f"nothing points at {sorted(stranded)}")
        return self


def _reachable_from(by_id: dict[str, LayoutBlock]) -> set[str]:
    """Every block the root can reach, refusing any reference that does not resolve.

    Iterative and visited-guarded rather than recursive: ids come off the wire, so a layout naming
    itself as its own child is a shape this has to survive rather than one it can assume away.
    """
    seen: set[str] = set()
    pending = [_ROOT]
    while pending:
        block_id = pending.pop()
        if block_id in seen:
            continue
        seen.add(block_id)
        block = by_id.get(block_id)
        if block is None:
            raise ValueError(f"layout names a child it does not contain: {block_id!r}")
        pending.extend(getattr(block, "children", ()))
    return seen
