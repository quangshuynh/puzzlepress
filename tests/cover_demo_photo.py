"""Regenerate books/cover-demo's stand-in photograph (not a test module).

The demo needs a photograph, but PuzzlePress ships none of its authors'
photography, so this draws a synthetic seascape with Pillow from a fixed seed.
It is a placeholder for your own photograph. Run from the repository root:

    python tests/cover_demo_photo.py

The output is deterministic for a given Pillow version.
"""

import io
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

WIDTH, HEIGHT = 5600, 3600
HORIZON = 0.56


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def seascape(seed: int = 2026) -> Image.Image:
    rng = random.Random(seed)
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    horizon = int(HEIGHT * HORIZON)
    sky = [(28, 46, 74), (88, 104, 132), (214, 160, 128), (244, 206, 160)]
    for y in range(horizon):
        t = y / horizon
        index = min(int(t * 3), 2)
        draw.line([(0, y), (WIDTH, y)], fill=_lerp(sky[index], sky[index + 1], t * 3 - index))
    sea = [(196, 150, 126), (70, 92, 112), (22, 38, 52)]
    for y in range(horizon, HEIGHT):
        t = (y - horizon) / (HEIGHT - horizon)
        color = _lerp(sea[0], sea[1], t * 2) if t < 0.5 else _lerp(sea[1], sea[2], t * 2 - 1)
        draw.line([(0, y), (WIDTH, y)], fill=color)
    sun_x, sun_y = int(WIDTH * 0.68), horizon - 140
    glow = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(glow).ellipse((sun_x - 900, sun_y - 700, sun_x + 900, sun_y + 700), fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(320))
    image = Image.composite(Image.new("RGB", image.size, (255, 222, 176)), image, glow)
    draw = ImageDraw.Draw(image)
    draw.ellipse((sun_x - 110, sun_y - 110, sun_x + 110, sun_y + 110), fill=(255, 238, 206))
    # Distant headland and a lighthouse, then reflections and ripples on the water.
    points = [(0, horizon)]
    for x in range(0, int(WIDTH * 0.42), 40):
        points.append((x, horizon - 120 - int(90 * (1 - x / (WIDTH * 0.42))) - rng.randint(0, 18)))
    points.append((int(WIDTH * 0.46), horizon))
    draw.polygon(points, fill=(38, 44, 56))
    tower = int(WIDTH * 0.3)
    draw.rectangle((tower, horizon - 330, tower + 34, horizon - 150), fill=(226, 220, 210))
    draw.polygon(
        [(tower - 8, horizon - 330), (tower + 42, horizon - 330), (tower + 17, horizon - 372)],
        fill=(60, 52, 54),
    )
    for _ in range(2600):
        y = rng.randint(horizon + 4, HEIGHT - 1)
        depth = (y - horizon) / (HEIGHT - horizon)
        length = int(rng.randint(30, 260) * (0.3 + depth))
        x = rng.randint(-length, WIDTH)
        near_sun = abs(x - sun_x) < 600 * (0.4 + depth)
        shade = (255, 214, 168) if near_sun and rng.random() < 0.7 else (110, 132, 150)
        draw.line([(x, y), (x + length, y)], fill=shade, width=max(1, int(6 * depth)))
    image = image.filter(ImageFilter.GaussianBlur(1.2))
    # Foreground rocks at the lower left for depth.
    rocks = ImageDraw.Draw(image)
    rocks.polygon(
        [(0, HEIGHT), (0, HEIGHT - 520), (520, HEIGHT - 640), (1100, HEIGHT - 380), (1500, HEIGHT)],
        fill=(18, 22, 26),
    )
    return image


def main() -> int:
    target = Path("books/cover-demo/cover-assets")
    buffer = io.BytesIO()
    seascape().save(buffer, "JPEG", quality=88, subsampling=0, optimize=False)
    data = buffer.getvalue()
    sys.stdout.write(f"{len(data)} bytes\n")
    target.mkdir(parents=True, exist_ok=True)
    from puzzlepress.cover.assets import import_photo

    imported = import_photo(target.parent, data, "harbour-dusk.jpg")
    sys.stdout.write(f"{imported.path} {imported.info.sha256}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
