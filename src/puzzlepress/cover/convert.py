"""Explicit conversion to a version 3 region design, and named design presets.

Nothing here runs implicitly: opening, validating or saving a version 1 or 2
cover never converts it. `convert_to_regions` maps a full-wrap or front-photo
layout onto the equivalent regions and one photograph element; the converted
cover lays out and renders the same PDF bytes (tested), so the author can adopt
it without a visual change. Presets return authored values only; Python lays
them out like any other cover.
"""

from dataclasses import dataclass, replace

from ..cover_config import CoverConfig, CoverImage, CoverLayoutKind, Crop, Legibility
from ..cover_design import (
    CoverRegions,
    Element,
    ElementBox,
    ElementType,
    LineElement,
    PhotoElement,
    Point,
    Region,
    RegionStyle,
    ShapeElement,
)
from ..interior.spec import SUPPORTED_TRIMS, inches

PHOTO_ID = "photo"


def convert_to_regions(config: CoverConfig) -> CoverConfig:
    """The version 3 equivalent of a version 1 or 2 cover. Raises ValueError for v3."""
    if config.designed or config.image is None:
        raise ValueError("Only version 1 and 2 covers are converted")
    style = RegionStyle(config.background)
    region = Region.WRAP if config.layout is CoverLayoutKind.FULL_WRAP else Region.FRONT
    photo = PhotoElement(id=PHOTO_ID, region=region, image=config.image, crop=config.crop)
    return replace(
        config,
        version=3,
        image=None,
        layout=CoverLayoutKind.FULL_WRAP,
        crop=Crop(),
        background=CoverConfig.background,
        regions=CoverRegions(style, style, style),
        elements=(photo,),
    )


@dataclass(frozen=True)
class DesignPreset:
    id: str
    name: str
    description: str
    config: CoverConfig


def _photo(config: CoverConfig) -> tuple[CoverImage | None, Crop]:
    """The photograph and crop a preset starts from: the cover's first photograph."""
    if config.image is not None:
        return config.image, config.crop
    for element in config.elements:
        if isinstance(element, PhotoElement):
            return element.image, element.crop
    return None, Crop()


def _base(config: CoverConfig, color: str, elements: tuple[Element, ...]) -> CoverConfig:
    designed = config if config.designed else convert_to_regions(config)
    style = RegionStyle(color)
    return replace(designed, regions=CoverRegions(style, style, style), elements=elements)


def design_presets(config: CoverConfig) -> tuple[DesignPreset, ...]:
    """A few named starting points built from the cover's own photograph and colors.

    Coordinates use the supported trim (8.5 x 11 in): region coordinates are
    measured from each panel's trim corner, so they hold for any spine width.
    """
    trim = SUPPORTED_TRIMS[0]
    image, crop = _photo(config)
    color = config.background if config.regions is None else config.regions.back.color
    presets: list[DesignPreset] = []
    if image is not None:
        presets.append(
            DesignPreset(
                "front-photo-solid-back",
                "Front photograph, solid back",
                "The photograph fills the front to its bleed; spine and back are one color.",
                _base(
                    config,
                    color,
                    (PhotoElement(id=PHOTO_ID, region=Region.FRONT, image=image, crop=crop),),
                ),
            )
        )
        presets.append(
            DesignPreset(
                "full-wrap-photo",
                "Full-wrap photograph",
                "One photograph across back, spine and front, bleed to bleed.",
                _base(
                    config,
                    color,
                    (PhotoElement(id=PHOTO_ID, region=Region.WRAP, image=image, crop=crop),),
                ),
            )
        )
        inset = inches(0.75)
        frame = ElementBox(inset, inches(2.25), trim.width - 2 * inset, inches(5.5))
        presets.append(
            DesignPreset(
                "framed-photo",
                "Framed photograph",
                "A solid front with the photograph in an inset frame and a thin keyline.",
                replace(
                    _base(
                        config,
                        color,
                        (
                            PhotoElement(
                                id=PHOTO_ID,
                                region=Region.FRONT,
                                image=image,
                                crop=crop,
                                box=frame,
                            ),
                            ShapeElement(
                                id="keyline",
                                region=Region.FRONT,
                                kind=ElementType.RECT,
                                box=ElementBox(
                                    frame.x - 6, frame.y - 6, frame.width + 12, frame.height + 12
                                ),
                                fill=None,
                                stroke="#f4efe4",
                                stroke_width=1.0,
                            ),
                        ),
                    ),
                    legibility=Legibility.NONE,
                ),
            )
        )
    presets.append(
        DesignPreset(
            "solid-with-rules",
            "Solid color with rules",
            "No photograph: one background color with two thin rules on the front.",
            replace(
                _base(
                    config,
                    color,
                    (
                        LineElement(
                            id="rule-top",
                            region=Region.FRONT,
                            start=Point(inches(1), trim.height - inches(0.375)),
                            end=Point(trim.width - inches(1), trim.height - inches(0.375)),
                            color="#f4efe4",
                            width=1.0,
                        ),
                        LineElement(
                            id="rule-bottom",
                            region=Region.FRONT,
                            start=Point(inches(1), inches(0.375)),
                            end=Point(trim.width - inches(1), inches(0.375)),
                            color="#f4efe4",
                            width=1.0,
                        ),
                    ),
                ),
                legibility=Legibility.NONE,
            ),
        )
    )
    return tuple(presets)
