"""Growth engine: build a lyric composition by an EDGE TREE.

Model (recursive sub-edges — no flat global sides, no marching outward):

  * Every placed block exposes its 3 OUTER free edges (all but the one touching
    its parent) as new candidate edges in a pool.
  * Each line picks an available edge (pseudo-random, biased toward right/down
    facing edges), is sized to fill 70-100% of THAT edge, and snaps flush to it.
  * Because a child is sized to the specific (smaller) edge it builds on, it
    never overflows and child edges only shrink — growth is bounded by design.

SOLID split:
  Edge / EdgePool      — the geometry of available build sites.
  *Picker strategies   — choose edge / flow / fill-fraction (swappable).
  PlacedBlock          — a built block + its bbox + provenance.
  PosterBuilder        — orchestration only; depends on `fill_side` + pickers
                         through interfaces, not concretions.

Only `_mobj_bbox` and the placement math touch Manim; the rest is pure.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Protocol

from manim import VGroup

from .geometry import BBox, Flow, Side

# fill_side signature: (words, side, flow, edge_len, color, aspect_of) -> VGroup
FillFn = Callable[..., VGroup]


# --------------------------------------------------------------------------- #
# Edge geometry
# --------------------------------------------------------------------------- #
@dataclass
class Edge:
    """A free edge a block can build on.

    `facing` is the outward direction (a block on this edge grows that way).
    The edge is a segment: for a vertical-facing edge (RIGHT/LEFT) it runs in y
    from `lo` (bottom) to `hi` (top) at x == `outer`; for a horizontal-facing
    edge (UP/DOWN) it runs in x from `lo` (left) to `hi` (right) at y == `outer`.
    """

    facing: Side
    outer: float        # the fixed coordinate of the edge (x for L/R, y for U/D)
    lo: float           # segment start (min along the edge axis)
    hi: float           # segment end   (max along the edge axis)

    @property
    def length(self) -> float:
        return self.hi - self.lo


class EdgePool:
    """Holds available edges; picks one (weighted by facing direction)."""

    def __init__(self, edges: list[Edge] | None = None) -> None:
        self._edges: list[Edge] = list(edges or [])

    def __len__(self) -> int:
        return len(self._edges)

    def add(self, *edges: Edge) -> None:
        self._edges.extend(e for e in edges if e.length > 1e-3)

    def pop_weighted(self, weights: dict[Side, float],
                     rng: random.Random) -> Edge:
        """Remove and return an edge, chosen by its facing-direction weight."""
        w = [weights.get(e.facing, 0.01) for e in self._edges]
        idx = rng.choices(range(len(self._edges)), weights=w)[0]
        return self._edges.pop(idx)


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #
class FlowPicker(Protocol):
    def __call__(self, rng: random.Random) -> Flow: ...


class FractionPicker(Protocol):
    def __call__(self, rng: random.Random) -> float: ...


@dataclass
class WeightedFlowPicker:
    """Pseudo-random flow; flow does not affect which edge is filled."""

    p_vertical: float = 0.5

    def __call__(self, rng: random.Random) -> Flow:
        return Flow.VERTICAL if rng.random() < self.p_vertical else Flow.HORIZONTAL


@dataclass
class RangeFractionPicker:
    """Fraction of the chosen edge a line fills, in [lo, hi]."""

    lo: float = 0.70
    hi: float = 1.00

    def __call__(self, rng: random.Random) -> float:
        return rng.uniform(self.lo, self.hi)


# Edge-facing bias: prefer building toward the right and down.
DEFAULT_SIDE_WEIGHTS: dict[Side, float] = {
    Side.RIGHT: 0.40, Side.DOWN: 0.35, Side.LEFT: 0.15, Side.UP: 0.10,
}


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #
@dataclass
class PlacedBlock:
    block: VGroup
    side: Side               # the facing direction of the edge it was built on
    flow: Flow
    bbox: BBox
    fraction: float          # how much of the chosen edge it filled
    word_mobjs: list         # each word's mobject, in reading order


class PosterBuilder:
    """Chains lines onto an edge tree. Pure orchestration; no Manim scene calls."""

    def __init__(
        self,
        fill: FillFn,
        aspect_of,
        flow_picker: FlowPicker,
        fraction_picker: FractionPicker,
        side_weights: dict[Side, float] | None = None,
        attach_buff: float = 0.16,
        color: str = "#46464f",
        shrink_step: float = 0.85,    # multiply fraction by this when it collides
        min_fraction: float = 0.12,   # don't shrink below this; try another edge
        max_edge_tries: int = 8,      # candidate edges to try before skipping line
    ) -> None:
        self._fill = fill
        self._aspect = aspect_of
        self._pick_flow = flow_picker
        self._pick_fraction = fraction_picker
        self._weights = side_weights or DEFAULT_SIDE_WEIGHTS
        self._buff = attach_buff
        self._color = color
        self._shrink_step = shrink_step
        self._min_fraction = min_fraction
        self._max_edge_tries = max_edge_tries

    def build(self, anchor: VGroup, lines: list[list[str]],
              rng: random.Random) -> list[PlacedBlock]:
        """Place each line onto the growing edge tree seeded by `anchor`.

        For each line we pick an edge and SHRINK its fill fraction until the
        resulting block clears every block placed so far (no overlaps). If it
        won't fit on that edge even at `min_fraction`, we try another edge.
        """
        abox = _mobj_bbox(anchor)
        pool = EdgePool(_edges_of(abox))
        placed: list[PlacedBlock] = []
        occupied: list[BBox] = [abox]      # everything already on the canvas

        for words in lines:
            result = self._place_one(words, pool, occupied, rng)
            if result is None:
                continue                   # couldn't fit anywhere this round
            block, edge, flow, bbox, fraction, word_mobjs = result
            pool.add(*_outer_edges(bbox, parent_facing=edge.facing))
            occupied.append(bbox)
            placed.append(PlacedBlock(block, edge.facing, flow, bbox,
                                      fraction, word_mobjs))

        return placed

    def _place_one(self, words, pool, occupied, rng):
        """Try edges, shrinking fraction to fit. Returns placement or None."""
        flow = self._pick_flow(rng)
        tried: list[Edge] = []

        for _ in range(self._max_edge_tries):
            if len(pool) == 0:
                break
            edge = pool.pop_weighted(self._weights, rng)
            fraction = self._pick_fraction(rng)

            # Shrink the fraction until the block clears all occupied boxes.
            while fraction >= self._min_fraction:
                block, word_mobjs = self._fill(
                    words, edge.facing, flow, fraction * edge.length,
                    self._color, self._aspect)
                bbox = _place_on_edge(block, edge, self._buff)
                if not _collides(bbox, occupied):
                    # success: put unused edges back so they remain available
                    for e in tried:
                        pool.add(e)
                    return block, edge, flow, bbox, fraction, word_mobjs
                fraction *= self._shrink_step

            tried.append(edge)             # this edge never fit; set aside

        for e in tried:                    # restore edges we set aside
            pool.add(e)
        return None


# --------------------------------------------------------------------------- #
# Geometry helpers (Manim-touching: _mobj_bbox, _place_on_edge)
# --------------------------------------------------------------------------- #
def _mobj_bbox(mob) -> BBox:
    c = mob.get_center()
    w, h = mob.width, mob.height
    return BBox(c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)


def _collides(box: BBox, others: list[BBox], eps: float = 0.02) -> bool:
    """True if `box` overlaps any box in `others` (with a small tolerance)."""
    for o in others:
        if (box.x0 < o.x1 - eps and o.x0 < box.x1 - eps and
                box.y0 < o.y1 - eps and o.y0 < box.y1 - eps):
            return True
    return False


def _edges_of(box: BBox) -> list[Edge]:
    """All 4 edges of a box (used to seed the anchor)."""
    return [
        Edge(Side.RIGHT, box.x1, box.y0, box.y1),
        Edge(Side.LEFT,  box.x0, box.y0, box.y1),
        Edge(Side.UP,    box.y1, box.x0, box.x1),
        Edge(Side.DOWN,  box.y0, box.x0, box.x1),
    ]


def _outer_edges(box: BBox, parent_facing: Side) -> list[Edge]:
    """The 3 outer edges of `box`, excluding the side facing back to the parent.

    A block built on a RIGHT-facing edge touches its parent on its LEFT, so its
    LEFT edge is not exposed; its RIGHT/UP/DOWN edges are.
    """
    opposite = {
        Side.RIGHT: Side.LEFT, Side.LEFT: Side.RIGHT,
        Side.UP: Side.DOWN, Side.DOWN: Side.UP,
    }[parent_facing]
    return [e for e in _edges_of(box) if e.facing is not opposite]


def _place_on_edge(block: VGroup, edge: Edge, buff: float) -> BBox:
    """Snap `block` flush OUTSIDE `edge`, aligned to the edge's start corner.

    The block was sized to `fraction * edge.length`, so it fits within the edge
    segment. It's placed just beyond `edge.outer` (by `buff`), anchored at the
    edge's start corner (top for vertical edges, left for horizontal), packing
    inward along the segment. Returns the block's resulting bbox.
    """
    bw, bh = block.width, block.height
    if edge.facing is Side.RIGHT:
        cx = edge.outer + buff + bw / 2
        cy = edge.hi - bh / 2                 # from the top corner, downward
    elif edge.facing is Side.LEFT:
        cx = edge.outer - buff - bw / 2
        cy = edge.hi - bh / 2
    elif edge.facing is Side.UP:
        cx = edge.lo + bw / 2                 # from the left corner, rightward
        cy = edge.outer + buff + bh / 2
    else:  # DOWN
        cx = edge.lo + bw / 2
        cy = edge.outer - buff - bh / 2
    block.move_to([cx, cy, 0])
    return _mobj_bbox(block)
