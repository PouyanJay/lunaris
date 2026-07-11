"""The Lunaris cover house style — the dark disciplines plus their LIGHT-theme twins.

Split into a package (one-public-export-per-file): the per-preset ``HouseStyle`` + ``house_style``
factory live in ``house_style``; the GENERAL preset's full structured template (the operator's
course-cover prompt system, assembled deterministically) lives in ``general_prompt``; the
light-variant look (re-theme instruction, native-light rebuild, QA rubric — one per-preset palette)
lives in ``light``. Importers use this package's surface.
"""

from .general_prompt import GENERAL_DARK_THEME, GENERAL_LIGHT_THEME, build_general_prompt
from .house_style import EDITORIAL_PRESETS, HouseStyle, house_style
from .light import light_retheme_instruction, light_style_block, native_light_prompt

__all__ = [
    "EDITORIAL_PRESETS",
    "GENERAL_DARK_THEME",
    "GENERAL_LIGHT_THEME",
    "HouseStyle",
    "build_general_prompt",
    "house_style",
    "light_retheme_instruction",
    "light_style_block",
    "native_light_prompt",
]
