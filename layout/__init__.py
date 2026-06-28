"""Build-up layout engine: chain lyric lines into a growing typographic shape."""

from .filler import fill_side, make_aspect_fn
from .geometry import BBox, Flow, Side, is_parallel
from .growth import (
    PlacedBlock,
    PosterBuilder,
    RangeFractionPicker,
    WeightedFlowPicker,
)

__all__ = [
    "BBox", "Flow", "Side", "is_parallel",
    "fill_side", "make_aspect_fn",
    "PosterBuilder", "PlacedBlock",
    "WeightedFlowPicker", "RangeFractionPicker",
]
