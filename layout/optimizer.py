"""Wrap/size optimizers. Pure logic; Manim is injected via an aspect callback.

Two cases (see geometry.is_parallel):

  PARALLEL  — flow runs ALONG the constrained edge. Each part is scaled so its
              along-edge extent == edge_len; parts tile across the FREE axis.
              We choose the WRAP that balances the parts' cross-thicknesses.

  PERPENDICULAR — flow stacks ACROSS the edge. All parts share a free-axis size
              `band` chosen so the stack (bands + gaps) == edge_len; each part
              extends freely outward. We choose the WRAP minimising depth
              variance (block stays roughly square).

The only Manim dependency — measuring a string's rendered aspect ratio — is
passed in as `aspect_of: Callable[[str], float]` (Dependency Inversion), so this
module is unit-testable with a fake metric.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

AspectFn = Callable[[str], float]

GAP_BASE = 0.10          # base gap between parts (Manim units)


@dataclass(frozen=True)
class SplitResult:
    parts: list[str]     # the wrapped sub-phrases, in reading order
    gap: float           # gap to place between parts
    band: float          # free-axis size per part (0 for parallel: see filler)


def _all_wraps(n: int):
    """Yield every contiguous wrap of n items as a list of (start, end) ranges."""
    for mask in range(1 << (n - 1)):
        parts, start = [], 0
        for i in range(1, n):
            if mask & (1 << (i - 1)):
                parts.append((start, i))
                start = i
        parts.append((start, n))
        yield parts


def optimize_parallel(words: list[str], edge_len: float,
                      aspect_of: AspectFn) -> SplitResult:
    """PARALLEL: each part fills edge_len; tile across free axis.

    A part scaled so its along-edge extent == edge_len has cross-thickness
    edge_len / aspect. We pick the wrap whose cross-thicknesses are most balanced
    (similar-width columns/rows), gently preferring 2-4 parts.
    """
    n = len(words)
    best, best_score = None, float("inf")

    for parts in _all_wraps(n):
        crosses = [edge_len / aspect_of(" ".join(words[i:j])) for (i, j) in parts]
        k = len(parts)
        mean_c = sum(crosses) / k
        variance = sum((c - mean_c) ** 2 for c in crosses) / k
        count_pen = 0.0 if 2 <= k <= 4 else 0.6
        score = variance + count_pen + 0.04 * k
        if score < best_score:
            best, best_score = parts, score

    chosen = best if best is not None else [(0, n)]
    return SplitResult(
        parts=[" ".join(words[i:j]) for (i, j) in chosen],
        gap=GAP_BASE,
        band=0.0,
    )


def optimize_perpendicular(words: list[str], edge_len: float,
                           aspect_of: AspectFn) -> SplitResult:
    """PERPENDICULAR: parts stack across the edge; total stack == edge_len.

    For a wrap of k parts, the shared free-axis size is
        band = (edge_len - GAP_BASE*(k-1)) / k
    and each part's outward depth = band * aspect. We pick the wrap that keeps
    depths balanced and the block roughly square (max depth ≈ edge_len).
    """
    n = len(words)
    best, best_band, best_score = None, edge_len, float("inf")

    for parts in _all_wraps(n):
        k = len(parts)
        band = (edge_len - GAP_BASE * (k - 1)) / k
        if band <= 0.05:
            continue
        depths = [band * aspect_of(" ".join(words[i:j])) for (i, j) in parts]
        mean_d = sum(depths) / k
        variance = sum((d - mean_d) ** 2 for d in depths) / k
        squareness = abs(max(depths) - edge_len) / edge_len
        score = variance + 0.5 * squareness + 0.05 * k
        if score < best_score:
            best, best_band, best_score = parts, band, score

    if best is None:
        return SplitResult([" ".join(words)], GAP_BASE, edge_len)
    return SplitResult(
        parts=[" ".join(words[i:j]) for (i, j) in best],
        gap=GAP_BASE,
        band=best_band,
    )
