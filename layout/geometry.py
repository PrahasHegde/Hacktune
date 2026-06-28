"""Pure geometry + enums for the build-up layout. No Manim, no I/O.

Defines the vocabulary every other layout module shares:

  Side  — which edge of the current shape a line attaches to.
  Flow  — how the words run (upright rows vs rotated columns).
  Case  — the (Side orientation x Flow) combination, which selects the optimizer
          path: PARALLEL (flow runs along the constrained edge) or
          PERPENDICULAR (flow stacks across it).

Keeping this Manim-free means the optimizer and growth logic are unit-testable
without rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Side(Enum):
    RIGHT = "right"
    DOWN = "down"
    LEFT = "left"
    UP = "up"

    @property
    def is_vertical_edge(self) -> bool:
        """True if attaching here constrains HEIGHT (a vertical edge: L/R)."""
        return self in (Side.RIGHT, Side.LEFT)


class Flow(Enum):
    HORIZONTAL = "horizontal"   # upright text, wraps into rows
    VERTICAL = "vertical"       # rotated 90°, wraps into columns


def is_parallel(side: Side, flow: Flow) -> bool:
    """Does the text FLOW run ALONG the constrained edge?

    Parallel cases (each part stretched to fill the edge length, tile across):
        vertical edge (L/R) + VERTICAL flow      -> columns fill the height
        horizontal edge (U/D) + HORIZONTAL flow  -> rows fill the width
    Perpendicular cases (parts stack across; total stack == edge length):
        vertical edge (L/R) + HORIZONTAL flow
        horizontal edge (U/D) + VERTICAL flow
    """
    if side.is_vertical_edge:
        return flow is Flow.VERTICAL
    return flow is Flow.HORIZONTAL


@dataclass(frozen=True)
class BBox:
    """An axis-aligned bounding box in Manim coords (origin centre, +x/+y)."""

    x0: float  # left
    y0: float  # bottom
    x1: float  # right
    y1: float  # top

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def edge_length(self, side: Side) -> float:
        """Length of the edge a block on `side` must fill."""
        return self.height if side.is_vertical_edge else self.width

    def union(self, other: "BBox") -> "BBox":
        return BBox(
            min(self.x0, other.x0), min(self.y0, other.y0),
            max(self.x1, other.x1), max(self.y1, other.y1),
        )
