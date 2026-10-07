"""Small deterministic photographs for cover tests.

`quadrants` draws an upright image whose four quadrants have distinct colors, so
orientation handling is checked by sampling, not by trusting metadata.
"""

import io

from PIL import Image

RED, GREEN, BLUE, WHITE = (220, 30, 30), (30, 200, 60), (30, 60, 220), (250, 250, 250)
# EXIF orientation -> transpose that stores an upright image so that applying the
# orientation (as viewers and ImageOps.exif_transpose do) restores it.
STORE = {
    1: None,
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_90,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_270,
}
LEAKS = (b"LEAKCAM", b"LEAKMODEL", b"LEAKCOMMENT", b"LEAKARTIST")


def quadrants(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), WHITE)
    half_w, half_h = width // 2, height // 2
    image.paste(RED, (0, 0, half_w, half_h))
    image.paste(GREEN, (half_w, 0, width, half_h))
    image.paste(BLUE, (0, half_h, half_w, height))
    return image


def photo_bytes(
    width: int = 120,
    height: int = 80,
    *,
    fmt: str = "JPEG",
    orientation: int = 1,
    private: bool = False,
    image: Image.Image | None = None,
    icc: bytes | None = None,
) -> bytes:
    """Encode an upright image as stored with the given EXIF orientation.

    `private` adds camera, artist, GPS and comment metadata that must never leak.
    """
    upright = image if image is not None else quadrants(width, height)
    transpose = STORE[orientation]
    stored = upright.transpose(transpose) if transpose is not None else upright.copy()
    exif = Image.Exif()
    if orientation != 1:
        exif[0x0112] = orientation
    params: dict[str, object] = {}
    if private:
        exif[0x010F] = "LEAKCAM"
        exif[0x0110] = "LEAKMODEL"
        exif[0x013B] = "LEAKARTIST"
        gps = exif.get_ifd(0x8825)
        gps[1] = "N"
        gps[2] = (40.0, 26.0, 46.0)
        if fmt == "JPEG":
            params["comment"] = b"LEAKCOMMENT"
    if len(exif):
        params["exif"] = exif.tobytes()
    if icc is not None:
        params["icc_profile"] = icc
    if fmt == "JPEG":
        params.update(quality=92, subsampling=0)
    buffer = io.BytesIO()
    stored.save(buffer, fmt, **params)
    return buffer.getvalue()
