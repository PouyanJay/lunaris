from typing import Annotated

from pydantic import Field

from .example_block import ExampleBlock
from .hint_block import HintBlock
from .practice_block import PracticeBlock
from .prose_block import ProseBlock
from .stack_block import StackBlock
from .surface_block import SurfaceBlock

#: One block of a Tier 2 layout, discriminated by ``component``.
#:
#: This union **is** R6's allow-list. A component outside the catalog is unrepresentable rather than
#: merely rejected, so "the tutor composes from a fixed catalog, never free-form markup" is a
#: property of the type instead of a check somebody has to remember to run — and anything that ever
#: composes a layout, here or over the wire, is validated by parsing rather than by inspection.
type LayoutBlock = Annotated[
    StackBlock | ProseBlock | SurfaceBlock | ExampleBlock | HintBlock | PracticeBlock,
    Field(discriminator="component"),
]
