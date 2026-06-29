from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


class ImageValidationError(ValueError):
    """Raised when uploaded image input is invalid."""


@dataclass(slots=True)
class NormalizedImage:
    image: Image.Image
    width: int
    height: int


def crop_center_region(image: Image.Image, *, fraction: float) -> NormalizedImage:
    if not 0 < fraction <= 1:
        raise ValueError("Center crop fraction must be greater than 0 and at most 1.")

    crop_width = max(1, round(image.width * fraction))
    crop_height = max(1, round(image.height * fraction))
    left = max(0, (image.width - crop_width) // 2)
    top = max(0, (image.height - crop_height) // 2)
    cropped = image.crop((left, top, left + crop_width, top + crop_height))
    return NormalizedImage(image=cropped, width=cropped.width, height=cropped.height)


def normalize_uploaded_image(
    raw_bytes: bytes,
    *,
    content_type: str | None,
    max_upload_bytes: int,
    image_max_side: int,
) -> NormalizedImage:
    if not raw_bytes:
        raise ImageValidationError("Image upload is empty.")
    if len(raw_bytes) > max_upload_bytes:
        raise ImageValidationError(f"Image exceeds the {max_upload_bytes} byte upload limit.")
    if content_type and content_type.lower() not in ALLOWED_IMAGE_TYPES:
        raise ImageValidationError(f"Unsupported image content type: {content_type}")

    try:
        with Image.open(io.BytesIO(raw_bytes)) as incoming:
            image = ImageOps.exif_transpose(incoming).convert("RGB")
    except UnidentifiedImageError as exc:
        raise ImageValidationError("Uploaded file is not a valid image.") from exc

    if max(image.size) > image_max_side:
        image.thumbnail((image_max_side, image_max_side), Image.Resampling.LANCZOS)

    return NormalizedImage(image=image, width=image.width, height=image.height)
