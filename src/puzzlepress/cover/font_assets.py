"""Imported cover fonts: validation, content-addressed import and registration.

A deliberately bounded first implementation. Accepted: one static font with
TrueType (glyf) outlines in a .ttf or .otf file. Refused with a reason: CFF
(PostScript-outline) OpenType, variable fonts, collections, web fonts, damaged
files and fonts whose OS/2 embedding permissions forbid embedding in a PDF or
forbid subsetting (every cover font is subset). Fonts are read only from the
bytes given or from `cover-assets/fonts` inside the project; ReportLab parses
them from memory, so no system font directory or search path is consulted.
Nothing in a font is executed by PuzzlePress; PDFium's rasterizer (FreeType)
interprets TrueType hinting for previews only.

Originals are kept byte-for-byte under content-addressed names and never
rewritten. License and source are what the author records in the cover
configuration, never inferred from the file; embedding permission is read
from the font's OS/2 `fsType`.
"""

import hashlib
import io
import os
import re
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont

from ..cover_config import ASSET_DIRECTORY, FONT_DIRECTORY, CoverConfig, CoverFont
from .issues import CoverError, cover_error

MAX_FONT_BYTES = 10 * 1024 * 1024
MAX_TABLES = 64
EXTENSIONS = ("ttf", "otf")
_FONT_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.(?:ttf|otf)")
_TRUETYPE = (b"\x00\x01\x00\x00", b"true")
REQUIRED_TABLES = ("cmap", "glyf", "head", "hhea", "hmtx", "loca", "maxp", "name", "post", "OS/2")
VARIABLE_TABLES = ("fvar", "gvar", "avar", "HVAR", "MVAR")
# OS/2 fsType: the low four bits are the usage permission (least restrictive wins).
FS_RESTRICTED = 0x0002
FS_PREVIEW_PRINT = 0x0004
FS_EDITABLE = 0x0008
FS_NO_SUBSETTING = 0x0100
FS_BITMAP_ONLY = 0x0200


@dataclass(frozen=True)
class FontInfo:
    sha256: str
    bytes: int
    container: str  # "ttf" or "otf" (the file extension it was imported with).
    postscript_name: str
    family: str
    style: str
    full_name: str
    weight: int  # OS/2 usWeightClass.
    italic: bool
    glyphs: int  # Characters mapped in the cmap.
    fs_type: int
    embedding: str  # "installable", "editable" or "preview_print": all allow PDF embedding.

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "bytes": self.bytes,
            "container": self.container,
            "postscript_name": self.postscript_name,
            "family": self.family,
            "style": self.style,
            "full_name": self.full_name,
            "weight": self.weight,
            "italic": self.italic,
            "glyphs": self.glyphs,
            "fs_type": self.fs_type,
            "embedding": self.embedding,
        }


@dataclass(frozen=True, eq=False)
class LoadedFont:
    info: FontInfo
    key: str  # The registered ReportLab font name; the layout's face key.
    ttf: TTFont


def _font_error(code: str, message: str, **detail: str) -> CoverError:
    return cover_error("asset", code, message, region="cover.fonts", **detail)


def _tables(data: bytes) -> dict[str, tuple[int, int]]:
    """The sfnt table directory: tag -> (offset, length), bounds-checked."""
    if len(data) < 12:
        raise _font_error("font_corrupt", "The font file is too short to be a font.")
    signature = data[:4]
    if signature == b"OTTO":
        raise _font_error(
            "font_unsupported_outlines",
            "This OpenType font uses PostScript (CFF) outlines; only TrueType-outline "
            "fonts are supported for covers.",
            required="TrueType (glyf) outlines",
        )
    if signature == b"ttcf":
        raise _font_error(
            "font_collection_unsupported",
            "Font collections (.ttc) are not supported; import one static font file.",
        )
    if signature in (b"wOFF", b"wOF2"):
        raise _font_error(
            "font_unsupported", "Web fonts (WOFF) are not supported; import a .ttf or .otf file."
        )
    if signature not in _TRUETYPE:
        raise _font_error("font_corrupt", "The file is not a TrueType or OpenType font.")
    (count,) = struct.unpack(">H", data[4:6])
    if not 1 <= count <= MAX_TABLES or 12 + 16 * count > len(data):
        raise _font_error("font_corrupt", "The font's table directory is damaged.")
    tables: dict[str, tuple[int, int]] = {}
    for index in range(count):
        record = data[12 + 16 * index : 28 + 16 * index]
        tag = record[:4].decode("latin-1")
        offset, length = struct.unpack(">II", record[8:16])
        if offset + length > len(data):
            raise _font_error("font_corrupt", f"The font's {tag.strip()} table is truncated.")
        tables[tag] = (offset, length)
    return tables


def _embedding(fs_type: int) -> str:
    """Refuse fonts that may not be embedded in a PDF or subset; name what is allowed."""
    if fs_type & FS_BITMAP_ONLY:
        raise _font_error(
            "font_embedding_restricted",
            "The font's license flags allow only bitmap embedding; it cannot be embedded "
            "as a font in a print PDF.",
            actual=f"fsType 0x{fs_type:04X}",
        )
    if fs_type & FS_NO_SUBSETTING:
        raise _font_error(
            "font_embedding_restricted",
            "The font's license flags forbid subsetting; PuzzlePress embeds subsets only.",
            actual=f"fsType 0x{fs_type:04X}",
        )
    usage = fs_type & 0x000F
    if usage == 0:
        return "installable"
    if usage & FS_EDITABLE:
        return "editable"
    if usage & FS_PREVIEW_PRINT:
        return "preview_print"
    if usage & FS_RESTRICTED:
        raise _font_error(
            "font_embedding_restricted",
            "The font's license flags forbid embedding (Restricted License embedding).",
            actual=f"fsType 0x{fs_type:04X}",
        )
    raise _font_error(
        "font_embedding_restricted",
        "The font's embedding permissions are not recognized.",
        actual=f"fsType 0x{fs_type:04X}",
    )


def _text(value: bytes | str) -> str:
    return value.decode("latin-1") if isinstance(value, bytes) else str(value)


def _register_name(sha256: str) -> str:
    return f"PuzzlePressFont-{sha256[:16]}"


def inspect_font(data: bytes, container: str = "ttf") -> tuple[FontInfo, TTFont]:
    """Validate a font completely, from memory. Raises CoverError(stage 'asset')."""
    if not data:
        raise _font_error("font_corrupt", "The font file is empty.")
    if len(data) > MAX_FONT_BYTES:
        raise _font_error(
            "font_unsupported",
            "The font file is too large.",
            actual=f"{len(data)} bytes",
            required=f"at most {MAX_FONT_BYTES} bytes",
        )
    tables = _tables(data)
    variable = [tag for tag in VARIABLE_TABLES if tag in tables]
    if variable:
        raise _font_error(
            "font_variable_unsupported",
            "Variable fonts are not supported yet; import a static instance (one weight).",
            actual=", ".join(variable),
        )
    missing = [tag for tag in REQUIRED_TABLES if tag not in tables]
    if missing:
        raise _font_error(
            "font_corrupt",
            f"The font lacks required tables: {', '.join(missing)}.",
            actual=", ".join(missing),
        )
    offset, length = tables["OS/2"]
    if length < 10:
        raise _font_error("font_corrupt", "The font's OS/2 table is truncated.")
    weight, fs_type = struct.unpack(">H2xH", data[offset + 4 : offset + 10])
    embedding = _embedding(fs_type)
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        # validate=1 checks every table checksum; parsing is pure Python, from memory.
        ttf = TTFont(_register_name(sha256), io.BytesIO(data), validate=1)
    except TTFError as error:
        raise _font_error("font_corrupt", f"The font cannot be read: {error}") from error
    except (struct.error, ValueError, KeyError, IndexError, TypeError, OverflowError) as error:
        raise _font_error("font_corrupt", f"The font is damaged: {error}") from error
    face = ttf.face
    if not face.charToGlyph:
        raise _font_error("font_corrupt", "The font maps no characters.")
    info = FontInfo(
        sha256,
        len(data),
        container,
        _text(face.name),
        _text(face.familyName),
        _text(face.styleName),
        _text(face.fullName),
        weight,
        bool(face.italicAngle),
        len(face.charToGlyph),
        fs_type,
        embedding,
    )
    return info, ttf


_REGISTERED: dict[str, LoadedFont] = {}
_REGISTRY_LOCK = Lock()


def load_font(data: bytes, container: str = "ttf") -> LoadedFont:
    """Validate and register a font with ReportLab under a digest-derived name."""
    sha256 = hashlib.sha256(data).hexdigest()
    with _REGISTRY_LOCK:
        loaded = _REGISTERED.get(sha256)
        if loaded is not None:
            return loaded
    info, ttf = inspect_font(data, container)
    with _REGISTRY_LOCK:
        loaded = _REGISTERED.get(sha256)
        if loaded is None:
            pdfmetrics.registerFont(ttf)
            loaded = LoadedFont(info, ttf.fontName, ttf)
            _REGISTERED[sha256] = loaded
    return loaded


def registered(key: str) -> TTFont:
    """The TTFont for a face key returned by `load_font` (programming error if absent)."""
    with _REGISTRY_LOCK:
        for loaded in _REGISTERED.values():
            if loaded.key == key:
                return loaded.ttf
    raise KeyError(f"Font {key!r} has not been loaded")


# ------------------------------------------------------------------ project files


def font_directory(project_directory: Path, create: bool = False) -> Path:
    """The real cover-assets/fonts directory inside the resolved project folder."""
    project = project_directory.resolve()
    assets = project / ASSET_DIRECTORY
    directory = project / FONT_DIRECTORY
    for path in (assets, directory):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise _font_error("asset_unsafe", f"{path.name} must be a real directory.")
        if create:
            path.mkdir(exist_ok=True)
    if directory.exists() and directory.resolve() != assets.resolve() / "fonts":
        raise _font_error("asset_unsafe", f"{FONT_DIRECTORY} resolves outside the project.")
    if assets.exists() and assets.resolve().parent != project:
        raise _font_error("asset_unsafe", f"{ASSET_DIRECTORY} resolves outside the project.")
    return directory


def read_font(project_directory: Path, font: CoverFont) -> bytes:
    """Read a configured font inside cover-assets/fonts and verify its pinned digest."""
    directory = font_directory(project_directory)
    name = font.path.removeprefix(f"{FONT_DIRECTORY}/")
    path = directory / name
    region = f"cover.fonts.{font.id}"
    if not _FONT_NAME.fullmatch(name) or path.is_symlink():
        raise cover_error("asset", "asset_unsafe", "The font is not a project asset.", region)
    try:
        if not path.is_file():
            raise cover_error(
                "asset",
                "font_missing",
                f"The font {font.path} is missing from the project.",
                region,
            )
        if path.stat().st_size > MAX_FONT_BYTES:
            raise cover_error("asset", "font_unsupported", "The font file is too large.", region)
        data = path.read_bytes()
    except OSError as error:
        message = f"Cannot read {font.path}: {error}"
        raise cover_error("asset", "font_missing", message, region) from error
    actual = hashlib.sha256(data).hexdigest()
    if actual != font.sha256:
        raise cover_error(
            "asset",
            "asset_digest_mismatch",
            f"{font.path} changed since it was chosen; import it again to accept the new file.",
            region,
            actual=actual,
            required=font.sha256,
        )
    return data


def read_font_file(project_directory: Path, reference: str) -> bytes:
    """Bytes of `cover-assets/fonts/<name>` (a listed font), boundary-checked."""
    name = reference.removeprefix(f"{FONT_DIRECTORY}/")
    if reference != f"{FONT_DIRECTORY}/{name}" or not _FONT_NAME.fullmatch(name):
        raise _font_error("asset_unsafe", "The font reference is not a project asset.")
    path = font_directory(project_directory) / name
    if path.is_symlink() or not path.is_file():
        raise _font_error("font_missing", f"{reference} is not in the project.")
    if path.stat().st_size > MAX_FONT_BYTES:
        raise _font_error("font_unsupported", "The font file is too large.")
    return path.read_bytes()


@dataclass(frozen=True)
class CoverFonts:
    """The imported fonts a cover configuration names, loaded and registered."""

    by_id: dict[str, LoadedFont]

    def key(self, font_id: str) -> str:
        return self.by_id[font_id].key


NO_FONTS = CoverFonts({})


def load_cover_fonts(project_directory: Path, config: CoverConfig) -> CoverFonts:
    """Read, verify, validate and register every font in `config.fonts`."""
    loaded: dict[str, LoadedFont] = {}
    for font in config.fonts:
        data = read_font(project_directory, font)
        try:
            loaded[font.id] = load_font(data, font.path.rsplit(".", 1)[-1])
        except CoverError as error:
            issue = error.issues[0]
            raise cover_error(
                "asset",
                issue.code,
                f"{font.path}: {issue.message}",
                f"cover.fonts.{font.id}",
                actual=issue.actual,
                required=issue.required,
            ) from error
    return CoverFonts(loaded)


def font_asset_name(original_name: str, sha256: str, extension: str) -> str:
    stem = Path(original_name.replace("\\", "/").rsplit("/", 1)[-1]).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:40].strip("-") or "font"
    return f"{stem}-{sha256[:12]}.{extension}"


@dataclass(frozen=True)
class ImportedFont:
    path: str
    info: FontInfo
    reused: bool


def import_font(project_directory: Path, data: bytes, original_name: str) -> ImportedFont:
    """Copy a validated font into cover-assets/fonts without overwriting anything."""
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if extension not in EXTENSIONS:
        raise _font_error("font_unsupported", "Import a .ttf or .otf font file.")
    info, _ = inspect_font(data, extension)  # Validate fully before anything is written.
    name = font_asset_name(original_name, info.sha256, extension)
    directory = font_directory(project_directory, create=True)
    target = directory / name
    reference = f"{FONT_DIRECTORY}/{name}"

    def existing() -> ImportedFont:
        if target.is_symlink() or not target.is_file() or target.read_bytes() != data:
            raise _font_error("asset_collision", f"{reference} already exists with other content.")
        return ImportedFont(reference, info, True)

    if target.exists() or target.is_symlink():
        return existing()
    suffix = name[name.rindex("-") :].rsplit(".", 1)[0]
    for candidate in sorted(directory.iterdir(), key=lambda p: p.name):
        # The same bytes imported earlier under another original name.
        if (
            _FONT_NAME.fullmatch(candidate.name)
            and suffix in candidate.name
            and not candidate.is_symlink()
            and candidate.is_file()
            and candidate.read_bytes() == data
        ):
            return ImportedFont(f"{FONT_DIRECTORY}/{candidate.name}", info, True)
    handle, staged_name = tempfile.mkstemp(prefix=".font-import-", suffix=".tmp", dir=directory)
    staged = Path(staged_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if staged.read_bytes() != data:
            raise _font_error("write_failed", "The staged font does not match.")
        try:
            os.link(staged, target)  # Atomic and never replaces an existing file.
        except FileExistsError:
            return existing()
    except OSError as error:
        raise _font_error("write_failed", f"Cannot import the font: {error}") from error
    finally:
        staged.unlink(missing_ok=True)
    return ImportedFont(reference, info, False)


@dataclass(frozen=True)
class FontEntry:
    path: str
    info: FontInfo | None
    problem: str | None = None
    message: str | None = None


def list_fonts(project_directory: Path) -> tuple[FontEntry, ...]:
    """Fonts in cover-assets/fonts with their facts; unusable files say why."""
    directory = font_directory(project_directory)
    if not directory.is_dir():
        return ()
    entries: list[FontEntry] = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if not _FONT_NAME.fullmatch(path.name) or path.is_symlink() or not path.is_file():
            continue
        reference = f"{FONT_DIRECTORY}/{path.name}"
        try:
            if path.stat().st_size > MAX_FONT_BYTES:
                raise _font_error("font_unsupported", "The font file is too large.")
            info, _ = inspect_font(path.read_bytes(), path.suffix[1:])
            entries.append(FontEntry(reference, info))
        except CoverError as error:
            entries.append(
                FontEntry(reference, None, error.issues[0].code, error.issues[0].message)
            )
        except OSError as error:
            entries.append(FontEntry(reference, None, "font_missing", str(error)))
    return tuple(entries)
