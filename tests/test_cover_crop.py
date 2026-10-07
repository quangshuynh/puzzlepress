"""Cover-fit crop math: uniform scale, focal clamping, zoom, DPI and placement."""

import pytest

from puzzlepress.cover.crop import crop_window, image_placement
from puzzlepress.cover_config import Crop
from puzzlepress.interior.model import Box

TOL = 1e-9
# A front panel with bleed on three sides: 8.625 x 11.25 in.
FRONT = Box(630.0, 0.0, 621.0, 810.0)


def uniform(window, region):
    """Window maps onto the region with one scale on both axes: no stretching."""
    return (
        abs(window.width * window.scale - region.width) < 1e-6
        and abs(window.height * window.scale - region.height) < 1e-6
    )


def test_landscape_photo_fits_portrait_region_by_height_and_centers():
    window = crop_window(6000, 4000, FRONT, Crop())
    assert window.scale == pytest.approx(810 / 4000, abs=TOL)
    assert window.height == pytest.approx(4000) and window.width == pytest.approx(3066.6667, 1e-4)
    assert window.left == pytest.approx((6000 - window.width) / 2)
    assert window.top == pytest.approx(0)
    assert window.center == pytest.approx((0.5, 0.5))
    assert uniform(window, FRONT)


def test_portrait_photo_fits_landscape_region_by_width():
    region = Box(0, 0, 1260, 810)
    window = crop_window(3000, 4500, region, Crop())
    assert window.scale == pytest.approx(1260 / 3000)
    assert window.width == pytest.approx(3000) and window.left == pytest.approx(0)
    assert window.top == pytest.approx((4500 - window.height) / 2)
    assert uniform(window, region)


def test_square_and_exact_aspect_photos():
    square = crop_window(2000, 2000, FRONT, Crop())
    assert square.height == pytest.approx(2000) and uniform(square, FRONT)
    exact = crop_window(2070, 2700, FRONT, Crop(0.0, 1.0))  # Same 621:810 aspect.
    assert (exact.left, exact.top, exact.width, exact.height) == pytest.approx((0, 0, 2070, 2700))
    assert exact.normalized() == pytest.approx((0, 0, 1, 1))
    assert exact.pixel_bounds() == (0, 0, 2070, 2700)


@pytest.mark.parametrize(
    ("x", "y", "left", "top"),
    [(0.0, 0.0, 0.0, 0.0), (1.0, 1.0, "max", "max"), (0.5, 0.0, "mid", 0.0)],
)
def test_extreme_focal_points_clamp_inside_the_photo(x, y, left, top):
    window = crop_window(6000, 4000, FRONT, Crop(x, y, 2.0))
    max_left, max_top = 6000 - window.width, 4000 - window.height
    expected_left = {"max": max_left, "mid": max_left / 2}.get(left, left)
    expected_top = {"max": max_top}.get(top, top)
    assert window.left == pytest.approx(expected_left)
    assert window.top == pytest.approx(expected_top)
    x0, y0, x1, y1 = window.pixel_bounds()
    assert 0 <= x0 and 0 <= y0 and x1 <= 6000 and y1 <= 4000


def test_zoom_shrinks_the_window_and_lowers_effective_dpi():
    base = crop_window(6000, 4000, FRONT, Crop())
    zoomed = crop_window(6000, 4000, FRONT, Crop(zoom=2.0))
    assert zoomed.width == pytest.approx(base.width / 2)
    assert zoomed.height == pytest.approx(base.height / 2)
    assert zoomed.effective_dpi == pytest.approx(base.effective_dpi / 2)
    assert zoomed.max_dpi == pytest.approx(base.effective_dpi)
    assert uniform(zoomed, FRONT)


def test_effective_dpi_is_source_pixels_used_per_printed_inch():
    window = crop_window(6000, 4000, FRONT, Crop(zoom=1.25))
    printed_inches = FRONT.height / 72
    assert window.effective_dpi == pytest.approx(window.height / printed_inches)
    assert window.effective_dpi == pytest.approx(window.width / (FRONT.width / 72))
    # 4000 px over 11.25 in.
    assert crop_window(6000, 4000, FRONT, Crop()).effective_dpi == pytest.approx(4000 / 11.25)


def test_placement_maps_the_window_exactly_onto_the_region():
    window = crop_window(6000, 4000, FRONT, Crop(0.37, 0.61, 1.7))
    x0, y0, x1, y1 = window.pixel_bounds()
    box = image_placement(window, FRONT)
    s = window.scale
    assert box.width == pytest.approx((x1 - x0) * s) and box.height == pytest.approx((y1 - y0) * s)
    # The window's own edges land exactly on the region's edges.
    assert box.x + (window.left - x0) * s == pytest.approx(FRONT.x)
    assert box.top - (window.top - y0) * s == pytest.approx(FRONT.top)
    assert box.x + (window.left + window.width - x0) * s == pytest.approx(FRONT.right)
    assert box.top - (window.top + window.height - y0) * s == pytest.approx(FRONT.y)
    # The drawn image covers the region and overhangs by less than one source pixel.
    assert box.contains(FRONT, 1e-6)
    assert FRONT.x - box.x < s and box.right - FRONT.right < s


def test_crop_is_deterministic_and_rejects_empty_extent():
    crop = Crop(0.1234, 0.9876, 3.3)
    assert crop_window(4032, 3024, FRONT, crop) == crop_window(4032, 3024, FRONT, crop)
    with pytest.raises(ValueError):
        crop_window(0, 10, FRONT, crop)
    with pytest.raises(ValueError):
        crop_window(10, 10, Box(0, 0, 0, 10), crop)
