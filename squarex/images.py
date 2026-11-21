import io

from PIL import Image

from squarex.config import IMAGE_LONG_SIDE, IMAGE_QUALITY


def resize(jpeg: bytes) -> bytes:
    with Image.open(io.BytesIO(jpeg)) as image:
        image.thumbnail((IMAGE_LONG_SIDE, IMAGE_LONG_SIDE), Image.Resampling.BOX)
        output = io.BytesIO()
        image.convert("RGB").save(output, "JPEG", quality=IMAGE_QUALITY)
    return output.getvalue()
