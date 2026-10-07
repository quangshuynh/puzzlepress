"""Non-authoritative page previews rasterized from the actual interior.pdf bytes.

PDFium (pypdfium2) draws the same bytes KDP would receive; nothing is recreated
from the layout. Images are cached in memory by (PDF SHA-256, page, size), so a
new PDF digest can never be served an old image. PDFium is not thread-safe:
one lock serializes every call into it.
"""

import io
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any

# Power-of-two scales keep 8.5 x 11 in pages at exact pixel sizes (36/144/288 DPI).
SCALES = {"thumb": 0.5, "page": 2.0, "detail": 4.0}
CACHE_BUDGET = 96 * 1024 * 1024


class PreviewUnavailable(Exception):
    """pypdfium2 is not installed (it ships with the `studio` extra)."""


class PageOutOfRange(Exception):
    pass


@dataclass
class _Document:
    sha256: str
    pages: int
    handle: Any  # pypdfium2.PdfDocument; it also keeps the PDF bytes alive.


class PageRasterizer:
    def __init__(self, budget: int = CACHE_BUDGET) -> None:
        self._lock = Lock()
        self._budget = budget
        self._cache: OrderedDict[tuple[str, int, str], bytes] = OrderedDict()
        self._size = 0
        self._document: _Document | None = None
        self.renders = 0  # Cache misses, for tests and diagnostics.

    def png(self, pdf: bytes, sha256: str, page: int, size: str) -> bytes:
        """PNG of 1-based `page` of `pdf`, whose digest the caller has verified."""
        key = (sha256, page, size)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
            document = self._open(pdf, sha256)
            if not 1 <= page <= document.pages:
                raise PageOutOfRange(page)
            data = _encode(document.handle[page - 1].render(scale=SCALES[size]).to_pil())
            self.renders += 1
            self._cache[key] = data
            self._size += len(data)
            while self._size > self._budget and len(self._cache) > 1:
                _, evicted = self._cache.popitem(last=False)
                self._size -= len(evicted)
            return data

    def _open(self, pdf: bytes, sha256: str) -> _Document:
        if self._document is not None and self._document.sha256 == sha256:
            return self._document
        try:
            import pypdfium2
        except ImportError as error:
            raise PreviewUnavailable from error
        if self._document is not None:
            self._document.handle.close()
            self._document = None
        handle = pypdfium2.PdfDocument(pdf)
        self._document = _Document(sha256, len(handle), handle)
        return self._document


def _encode(image: Any) -> bytes:
    """Lossless PNG; stored as grayscale only when every pixel is already neutral."""
    from PIL import ImageChops

    if image.mode == "RGB":
        red, green, blue = image.split()
        if (
            ImageChops.difference(red, green).getbbox() is None
            and ImageChops.difference(red, blue).getbbox() is None
        ):
            image = red
    buffer = io.BytesIO()
    image.save(buffer, "PNG", compress_level=6)
    return buffer.getvalue()
