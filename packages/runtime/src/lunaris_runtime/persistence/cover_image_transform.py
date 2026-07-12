from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CoverImageTransform:
    """A server-side resize applied when a cover's signed URL is minted (Supabase Storage image
    transformations).

    A cover master is 2048x1152 — several megabytes of PNG. Handing that master to a 260px card and
    letting the browser shrink it is what makes a card cover look soft: a browser downscales with a
    cheap filter, and at a 3x reduction the fine typography and hairline callouts a composed cover
    carries alias into mush. Storage resamples once, properly (libvips/Lanczos), and re-encodes to
    WebP, so a display surface is sent an image already at its display size — sharper AND ~20x
    smaller on the wire.

    ``resize="cover"`` fills the box and crops the overflow, which is exactly what the CSS
    ``object-fit: cover`` on the cover frames does — so the server-side crop and the browser's agree
    rather than framing the artwork two different ways.

    The transform is SIGNED into the URL (storage-api reads it from the token payload and ignores
    query params on a signed URL), so it is chosen here at mint time, never appended by the reader.
    """

    width: int
    height: int
    # Covers carry rendered typography, and WebP's default quality visibly softens letterforms;
    # 90 keeps them crisp while still landing an order of magnitude under the PNG master.
    quality: int = 90
    resize: str = "cover"

    def as_options(self) -> dict[str, int | str]:
        """The ``transform`` payload supabase-py signs into the URL."""
        return {
            "width": self.width,
            "height": self.height,
            "quality": self.quality,
            "resize": self.resize,
        }
