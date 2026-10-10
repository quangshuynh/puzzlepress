"""Synthetic font variants for cover font tests.

Every variant derives from a bundled SIL OFL font, edited at the byte level with
table and whole-file checksums recomputed, so validation sees well-formed sfnt
files that differ only in the property under test.
"""

import struct
from importlib.resources import files
from pathlib import Path

FONT = "Newsreader16pt-Regular.ttf"
ITALIC = "Newsreader16pt-Italic.ttf"


def bundled(name: str = FONT) -> bytes:
    return Path(str(files("puzzlepress.cover").joinpath("fonts", name))).read_bytes()


def _tables(data: bytes) -> dict[bytes, tuple[int, int, int]]:
    """tag -> (directory record offset, table offset, length)."""
    (count,) = struct.unpack(">H", data[4:6])
    tables = {}
    for index in range(count):
        record = 12 + 16 * index
        tag = data[record : record + 4]
        offset, length = struct.unpack(">II", data[record + 8 : record + 16])
        tables[tag] = (record, offset, length)
    return tables


def _checksum(data: bytes) -> int:
    padded = data + b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(padded) // 4}I", padded)) & 0xFFFFFFFF


def _resum(data: bytearray) -> bytes:
    tables = _tables(bytes(data))
    _, head, _ = tables[b"head"]
    data[head + 8 : head + 12] = b"\0\0\0\0"
    for record, offset, length in tables.values():
        data[record + 4 : record + 8] = struct.pack(
            ">I", _checksum(bytes(data[offset : offset + length]))
        )
    adjustment = (0xB1B0AFBA - _checksum(bytes(data))) & 0xFFFFFFFF
    data[head + 8 : head + 12] = struct.pack(">I", adjustment)
    return bytes(data)


def with_fs_type(value: int, base: bytes | None = None) -> bytes:
    data = bytearray(base or bundled())
    _, offset, _ = _tables(bytes(data))[b"OS/2"]
    data[offset + 8 : offset + 10] = struct.pack(">H", value)
    return _resum(data)


def renamed_table(old: bytes, new: bytes) -> bytes:
    """Rename one table in the directory (e.g. DSIG -> fvar to look variable)."""
    data = bytearray(bundled())
    record, _, _ = _tables(bytes(data))[old]
    data[record : record + 4] = new
    return _resum(data)


def cff_signature() -> bytes:
    return b"OTTO" + bundled()[4:]


def collection() -> bytes:
    return b"ttcf" + bundled()[4:]
