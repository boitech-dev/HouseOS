"""Pictures from outside (a person's photo, an image on the web) made safe to keep and to show a
model: decoded, turned upright, downscaled and re-encoded as JPEG, so no metadata (location,
camera) and nothing but pixels survive."""

import io
import threading

# Decoding a large picture takes memory (a 16 MP photo ≈ 50–200 MB for a moment): two at a time.
DECODING = threading.BoundedSemaphore(2)
MAX_PIXELS = 16_000_000


def downscale(content: bytes, side: int) -> tuple[bytes, int, int]:
    """JPEG bytes no larger than `side` on either edge, with the width and height."""
    with DECODING:
        return _downscale(content, side)


def _downscale(content: bytes, side: int) -> tuple[bytes, int, int]:
    from PIL import Image, ImageOps

    try:
        image = Image.open(io.BytesIO(content))
        if image.format not in {"JPEG", "PNG", "WEBP", "GIF"} or image.width * image.height > MAX_PIXELS:
            raise ValueError("IMAGE_UNSUPPORTED")
        if image.format == "JPEG":
            image.draft("RGB", (side, side))  # decode at a reduced size straight away
        image = ImageOps.exif_transpose(image)
        image.thumbnail((side, side))
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=85)
    except (OSError, SyntaxError, Image.DecompressionBombError):
        raise ValueError("IMAGE_UNSUPPORTED") from None
    return output.getvalue(), image.width, image.height
