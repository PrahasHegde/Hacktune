"""Render the whole song as a build-up canvas with a moving camera.

Every lyric line is chained onto a growing shape via the `layout` engine (edge
tree). Words pop in at their per-word timestamps, and the CAMERA glides+zooms to
frame the whole current lyric line as it is sung, with eased (non-linear) motion.

Render:
    uv run manim -ql   song_poster_scene.py SongPoster         # the video
    uv run manim -ql -s song_poster_scene.py SongPoster        # final frame

Env:
    HACKATUNE_SONG   song JSON     (default data/songs/song_666407.json)
    HACKATUNE_SEED   RNG seed      (default 7)
    HACKATUNE_END    stop after N lyric seconds; 0 = full song (default 0)
    HACKATUNE_NLINES lines to lay out; 0 = whole song          (default 0)
    HACKATUNE_DEBUG  1 = draw block outlines                   (default 0)
"""

from __future__ import annotations

import os
import random

import numpy as np
from manim import (
    DOWN,
    ORIGIN,
    PI,
    RIGHT,
    MovingCameraScene,
    Rectangle,
    Text,
    ValueTracker,
    VGroup,
    smooth,
)

from layout import (
    Flow,
    PosterBuilder,
    RangeFractionPicker,
    Side,
    WeightedFlowPicker,
    fill_side,
    make_aspect_fn,
)
from song_data import Song

SONG_PATH = os.environ.get("HACKATUNE_SONG", "lyric_video_songs_and_data\song_667784.json")
SEED = int(os.environ.get("HACKATUNE_SEED", "7"))
# render window: only emit frames for [START_TIME, END_TIME]. Before START_TIME
# the build-up is fast-forwarded (state applied instantly, no frames) so you can
# preview just a slice (e.g. the last 30s) without waiting for the whole render.
START_TIME = float(os.environ.get("HACKATUNE_START", "0"))
END_TIME = float(os.environ.get("HACKATUNE_END", "0"))
# how many lyric lines to lay out (anchor + this many). 0 = whole song (default).
N_LINES = int(os.environ.get("HACKATUNE_NLINES", "0"))
SHOW_DEBUG = os.environ.get("HACKATUNE_DEBUG", "0") == "1"

ANCHOR_H = 2.2
DIM = "#3a3a44"
ACTIVE = "#ffffff"
ANCHOR_BOX = "#ff4488"
# per-side outline colors for debug
SIDE_COLOR = {
    Side.RIGHT: "#44aaff",
    Side.DOWN: "#44ff88",
    Side.LEFT: "#ffaa44",
    Side.UP: "#cc66ff",
}

# Camera framing
# Margin is MULTIPLICATIVE (a fraction of the line size), not a fixed number of
# world-units — a fixed margin dwarfs small lines and acts as a hidden zoom-in
# floor. PAD=0.18 means the line fills ~1/(1.18) ≈ 85% of the frame on its
# tight axis, at every scale.
CAM_PAD = 0.18       # frame = line * (1 + CAM_PAD), so the line dominates always
CAM_MAX_GLIDE = 1.1  # longest a single camera glide takes (seconds)
CAM_MIN_GLIDE = 0.35 # shortest glide, so motion always reads as eased


class SongPoster(MovingCameraScene):
    def construct(self) -> None:
        song = Song.load(SONG_PATH)
        end = END_TIME if END_TIME > 0 else song.duration
        rng = random.Random(SEED)

        # ---- anchor = first lyric line, horizontal (per-word) ------------ #
        first = song.lyrics[0]
        anchor_words = [Text(w.text, color=ACTIVE) for w in first.words]
        space = anchor_words[0].height * 0.32
        anchor = VGroup(*anchor_words).arrange(RIGHT, buff=space, aligned_edge=DOWN)
        anchor.scale(ANCHOR_H / anchor.height)
        anchor.move_to([0, 0, 0])

        # ---- build the rest around it ------------------------------------ #
        builder = PosterBuilder(
            fill=fill_side,
            aspect_of=make_aspect_fn(),
            flow_picker=WeightedFlowPicker(),
            fraction_picker=RangeFractionPicker(0.70, 1.00),
            color=DIM,
        )
        upto = len(song.lyrics) if N_LINES <= 0 else min(N_LINES, len(song.lyrics))
        rest = [line.text.split() for line in song.lyrics[1:upto]]
        placed = builder.build(anchor, rest, rng)

        # ---- centre the whole composition (positions are final now) ------ #
        # We compute the full layout up front so geometry is fixed, but reveal
        # each WORD over time. `whole` is added to the scene ONCE so its rotation
        # updater works; every word starts INVISIBLE (opacity 0) and is revealed
        # by setting opacity to 1 at its timestamp — so words don't all show at
        # once, and rotating `whole` doesn't force-add unrevealed words.
        whole = VGroup(anchor, *[p.block for p in placed])
        whole.move_to([0, 0, 0])
        all_words = list(anchor_words)
        for p in placed:
            p.block.set_color(ACTIVE)
            all_words.extend(p.word_mobjs)
        for wmob in all_words:
            wmob.set_opacity(0.0)
        self.add(whole)

        # ---- timed build-up with moving camera --------------------------- #
        # Per line: glide the camera to frame the whole line (eased), then pop in
        # its words at their timestamps. The camera glide consumes real timeline
        # time, tracked by the clock so word reveals stay in sync.
        clock = 0.0

        def rendering() -> bool:
            return clock >= START_TIME

        def advance_to(t: float) -> None:
            nonlocal clock
            dt = t - clock
            if dt > 1e-3:
                if rendering():
                    self.wait(dt)        # real time, emits frames
                # else: fast-forward, just advance the clock (no frames)
                clock = t

        # Camera can't rotate in v0.20.1, so we ROTATE THE WORLD instead: spin
        # `whole` so the target line becomes horizontal, then pan/zoom to it.
        # `world_angle` is the current accumulated rotation of the composition.
        world_angle = 0.0

        def glide_to(target, target_text_angle: float, line_start: float) -> None:
            """Rotate world so the line is upright + pan/zoom to it (eased).

            IMPORTANT: we must NOT do `whole.animate.rotate(...)` — animating the
            big group forces Manim to add ALL its members (every unrevealed word)
            to the scene at once. Instead we rotate `whole` via a ValueTracker +
            updater: the group's geometry (and thus its already-added word
            children) rotates, while unrevealed words stay off-screen.
            """
            nonlocal clock, world_angle
            delta = -(target_text_angle + world_angle)
            new_world_angle = world_angle + delta

            lead = max(0.0, line_start - clock)
            run = min(run_glide(lead), lead) if lead > 1e-3 else CAM_MIN_GLIDE
            run = max(run, 1e-2)

            cx, cy, w, _ = self._frame_for_rotated(target, delta)

            if not rendering():
                # fast-forward: apply the END state of the glide instantly.
                if abs(delta) > 1e-4:
                    whole.rotate(delta, about_point=ORIGIN)
                self.camera.frame.move_to([cx, cy, 0]).set(width=w)
                clock += run
                world_angle = new_world_angle
                return

            if abs(delta) > 1e-4:
                # incremental rotation driven by a tracker (no group add)
                tracker = ValueTracker(0.0)
                applied = {"a": 0.0}

                def _rot(_m):
                    step = tracker.get_value() - applied["a"]
                    if abs(step) > 1e-9:
                        whole.rotate(step, about_point=ORIGIN)
                        applied["a"] = tracker.get_value()

                whole.add_updater(_rot)
                self.play(
                    tracker.animate.set_value(delta),
                    self.camera.frame.animate.move_to([cx, cy, 0]).set(width=w),
                    run_time=run, rate_func=smooth,
                )
                whole.remove_updater(_rot)
            else:
                self.play(
                    self.camera.frame.animate.move_to([cx, cy, 0]).set(width=w),
                    run_time=run, rate_func=smooth,
                )
            clock += run
            world_angle = new_world_angle

        def run_glide(lead: float) -> float:
            return min(CAM_MAX_GLIDE, max(CAM_MIN_GLIDE, lead))

        # Start framed on the anchor (always horizontal), then reveal it.
        cx, cy, w, _ = self._frame_for(anchor)
        self.camera.frame.move_to([cx, cy, 0]).set(width=w)
        advance_to(first.start)
        self._reveal_words(first, anchor_words, end, advance_to)
        if SHOW_DEBUG:
            self._outline(anchor, ANCHOR_BOX)

        # Then every other line: rotate-world + glide to it, then reveal words.
        for line, p in zip(song.lyrics[1:upto], placed):
            if line.start >= end:
                break
            text_angle = (PI / 2) if p.flow is Flow.VERTICAL else 0.0
            glide_to(p.block, text_angle, line.start)
            advance_to(line.start)
            self._reveal_words(line, p.word_mobjs, end, advance_to)
            if SHOW_DEBUG:
                self._outline(p.block, SIDE_COLOR[p.side])

        advance_to(min(end, song.duration))
        self.wait(1.0)

    # ------------------------------------------------------------------- #
    def _reveal_words(self, line, word_mobjs, end, advance_to) -> None:
        """Add each word's mobject at the word's start time (per-word build-up).

        `line.words` carries per-word start times; `word_mobjs` is the matching
        list in reading order. If counts differ (rare wrap edge case), we fall
        back to spreading words evenly across the line's span.
        """
        words = line.words
        n = min(len(words), len(word_mobjs))
        for i in range(n):
            t = words[i].start
            if t >= end:
                break
            advance_to(t)
            word_mobjs[i].set_opacity(1.0)        # reveal this word
        # reveal any leftover mobjs (count mismatch) so nothing is dropped
        for j in range(n, len(word_mobjs)):
            word_mobjs[j].set_opacity(1.0)

    # ------------------------------------------------------------------- #
    def _frame_for(self, mob) -> tuple[float, float, float, float]:
        """Camera (cx, cy, width, height) that frames `mob` with margin.

        Respects the frame's aspect ratio (so the line fits on BOTH axes) and a
        minimum width so tiny lines don't zoom in absurdly far.
        """
        return self._frame_dims(mob.width, mob.height, mob.get_center())

    def _frame_for_rotated(self, mob, delta: float
                           ) -> tuple[float, float, float, float]:
        """Frame `mob` as it will appear AFTER the world rotates by `delta`.

        The world rotates about ORIGIN, so the line's center moves; its on-screen
        size after rotation is the line's own width/height rotated upright. Since
        we only ever rotate to make the line axis-aligned, the post-rotation
        footprint is the line's current (pre-rotation) extent along its own axes.
        """
        c = mob.get_center()
        # rotate the center about ORIGIN by delta
        cos, sin = np.cos(delta), np.sin(delta)
        rx = c[0] * cos - c[1] * sin
        ry = c[0] * sin + c[1] * cos
        # after rotation the line is axis-aligned; use its bounding extent.
        w_axis = max(mob.width, mob.height)   # the long (reading) axis
        h_axis = min(mob.width, mob.height)
        return self._frame_dims(w_axis, h_axis, [rx, ry, 0])

    def _frame_dims(self, content_w: float, content_h: float, center
                    ) -> tuple[float, float, float, float]:
        aspect = self.camera.frame.width / self.camera.frame.height
        # Multiplicative padding so the line always fills the same fraction of
        # the frame, regardless of its absolute size (no hidden zoom floor).
        need_w = content_w * (1 + CAM_PAD)
        need_h = content_h * (1 + CAM_PAD)
        w = max(need_w, need_h * aspect)   # fit on both axes
        h = w / aspect
        return center[0], center[1], w, h

    # ------------------------------------------------------------------- #
    def _outline(self, mob, color: str) -> None:
        """Outline a mobject's bounding box (call AFTER all transforms)."""
        b = Rectangle(width=max(mob.width, 0.01), height=max(mob.height, 0.01))
        b.set_stroke(color, width=1.5, opacity=0.8).set_fill(opacity=0)
        b.move_to(mob.get_center())
        self.add(b)
