from __future__ import annotations

import pytest
from PIL import Image

from app.services.image_pipeline import crop_center_region


def test_crop_center_region_keeps_the_middle_of_the_image() -> None:
    image = Image.new("RGB", (12, 8))
    for x in range(image.width):
        for y in range(image.height):
            image.putpixel((x, y), (x, y, 0))

    cropped = crop_center_region(image, fraction=0.5)

    assert (cropped.width, cropped.height) == (6, 4)
    assert cropped.image.getpixel((0, 0)) == (3, 2, 0)
    assert cropped.image.getpixel((5, 3)) == (8, 5, 0)


@pytest.mark.parametrize("fraction", [0, -0.1, 1.01])
def test_crop_center_region_rejects_invalid_fraction(fraction: float) -> None:
    with pytest.raises(ValueError, match="crop fraction"):
        crop_center_region(Image.new("RGB", (10, 10)), fraction=fraction)
