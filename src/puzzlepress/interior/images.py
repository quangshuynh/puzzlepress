"""Grayscale photographs in the interior: placement, encoding and asset reads.

A styled title page (photo_feature) or theme divider may print one of the
project's photographs. The interior is black ink, so Python converts the photo
to grayscale itself (ITU-R 601 luma of the sRGB-normalized pixels) and embeds
exactly those pixels as a DeviceGray baseline JPEG without metadata: what Studio
previews is what prints, and a colored photograph is never assumed to look good
once printed in black. Crops reuse the cover's crop window: whole source pixels,
uniform scale, never stretched or upscaled. Effective DPI is measured the same
way, and the 300 DPI KDP minimum is a preflight finding, not a build failure.
"""

import io
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from ..cover_config import CoverImage, Crop
from .design import StyleImages
from .issues import InteriorError, LayoutIssue
from .model import Box, ImageBlock

if TYPE_CHECKING:  # The cover modules import the interior package; import them lazily.
    from ..cover.assets import Photo, PhotoInfo

JPEG_QUALITY = 95


@dataclass(frozen=True)
class InteriorPhotos:
    """Where a style prints photographs, and each photograph's decoded facts."""

    images: StyleImages = field(default_factory=StyleImages)
    info: "Mapping[str, PhotoInfo]" = field(default_factory=dict)


NO_PHOTOS = InteriorPhotos()


def place_photo(role: str, box: Box, info: "PhotoInfo", crop: Crop) -> ImageBlock:
    from ..cover.crop import crop_window, image_placement

    window = crop_window(info.width, info.height, box, crop)
    return ImageBlock(
        role,
        box,
        info.sha256,
        image_placement(window, box),
        window.pixel_bounds(),
        window.effective_dpi,
        window.max_dpi,
    )


def encode_gray(photo: "Photo", block: ImageBlock) -> tuple[bytes, tuple[int, int]]:
    """DeviceGray JPEG bytes of exactly the pixels `block` prints, and their size."""
    if photo.info.sha256 != block.sha256:
        raise ValueError("The decoded photo is not the one the layout was made for")
    gray = photo.image.crop(block.pixels).convert("L")
    bare = Image.frombytes("L", gray.size, gray.tobytes())  # No info dictionary at all.
    buffer = io.BytesIO()
    bare.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=False, progressive=False)
    return buffer.getvalue(), bare.size


def load_photos(
    source_directory: Path | None, images: tuple[CoverImage, ...]
) -> "dict[str, Photo]":
    """Read, verify and decode the photographs a style prints. Raises InteriorError."""
    from ..cover.assets import decode_photo, read_asset
    from ..cover.issues import CoverError

    if not images:
        return {}
    if source_directory is None:
        raise InteriorError(
            "asset",
            (
                LayoutIssue(
                    "interior_photo_unavailable",
                    "This interior style prints photographs; build it from its project folder.",
                    region="interior",
                ),
            ),
        )
    photos: dict[str, Photo] = {}
    for image in images:
        if image.sha256 in photos:
            continue
        try:
            photos[image.sha256] = decode_photo(read_asset(source_directory, image))
        except CoverError as error:
            issues = tuple(
                LayoutIssue(
                    issue.code,
                    issue.message,
                    region="interior.photo",
                    actual=issue.actual,
                    required=issue.required,
                )
                for issue in error.issues
            )
            raise InteriorError("asset", issues) from error
    return photos
