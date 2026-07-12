from lunaris_runtime.persistence import CoverImageTransform

# The derivative every DISPLAY surface is served — the library cards and the Overview hero. The
# lightbox is the one surface that gets the untouched 2048x1152 master, because it is the one
# surface actually big enough to want it.
#
# 1280x720 is sized from the frames, not from taste: the widest frame is a library card, whose grid
# track is ``minmax(260px, 1fr)`` and tops out around 420 CSS px; the Overview hero is 360 CSS px.
# At a 3x device-pixel ratio the largest of those needs ~1260 device px, so 1280 out-resolves every
# surface at every DPR — the browser only ever scales DOWN a little, never up. It keeps the cover's
# native 16:9, so the ``resize="cover"`` crop is a no-op on a correct render, and it lands ~20x
# lighter on the wire than the PNG master (~150KB of WebP vs ~3.5MB).
COVER_DISPLAY_TRANSFORM = CoverImageTransform(width=1280, height=720)
