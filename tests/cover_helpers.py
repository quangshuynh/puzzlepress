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


def cover_project(
    root,
    data: bytes | None = None,
    cover: dict | None = None,
    mutate=None,
    puzzles: int | None = None,
    profile: str = "paperback-8.5x11",
    build_interior: bool = True,
):
    """A disposable composed project with an imported photo and a cover section.

    Returns (source directory, output directory). The interior is built into the
    output directory unless `build_interior` is false.
    """
    from pathlib import Path

    from puzzlepress.cover.assets import import_photo
    from puzzlepress.interior import build_interior as build
    from puzzlepress.interior import print_profile, write_interior
    from puzzlepress.validation import validate_project
    from puzzlepress.yaml_io import dump_project
    from tests.helpers import demo_variant

    source = Path(root) / "book"
    output = Path(root) / "out"
    source.mkdir(parents=True)
    imported = import_photo(source, data or photo_bytes(5400, 3600), "harbour.jpg")
    project = demo_variant(puzzles=puzzles).to_dict()
    project["output"] = {"directory": "../out"}
    project["book"]["imprint"] = "Harbour Press"
    project["cover"] = {
        "version": 1,
        "image": {"path": imported.path, "sha256": imported.info.sha256},
        "back_text": "Quiet seaside puzzles.",
        **(cover or {}),
    }
    if mutate is not None:
        mutate(project)
    valid = validate_project(project).require_project()
    (source / "book.yaml").write_text(dump_project(valid), encoding="utf-8")
    if build_interior:
        spec = print_profile(profile)
        write_interior(build(valid, spec), output, source)  # type: ignore[arg-type]
    return source, output
