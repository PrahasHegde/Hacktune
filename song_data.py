"""Typed loader for the song analysis JSON.

This module is deliberately decoupled from Manim: it just turns a
`song_<id>.json` file into typed Python objects covering *all* fields in the
format (see `data/songs/README.md`). Rendering code consumes these objects.

Usage:
    from song_data import Song
    song = Song.load("data/songs/song_666407.json")
    for line in song.lyrics:
        print(line.start, line.text)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# Lyrics
# --------------------------------------------------------------------------- #
@dataclass
class Word:
    """A single time-aligned token (timestamps in seconds)."""

    text: str
    start: float
    end: float
    type: str = "word"
    speaker_id: str = "speaker_0"

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        return cls(
            text=d.get("text", d.get("word", "")),
            start=float(d["start"]),
            end=float(d["end"]),
            type=d.get("type", "word"),
            speaker_id=d.get("speaker_id", "speaker_0"),
        )

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class LyricLine:
    """One lyric line with per-word timing (timestamps in seconds)."""

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "LyricLine":
        return cls(
            start=float(d["start"]),
            end=float(d["end"]),
            text=d.get("text", ""),
            words=[Word.from_dict(w) for w in d.get("words", [])],
        )

    @property
    def duration(self) -> float:
        return self.end - self.start


# --------------------------------------------------------------------------- #
# Structure / rhythm / energy
# --------------------------------------------------------------------------- #
@dataclass
class Segment:
    """A structural section of the song (timestamps in seconds)."""

    label: str
    start: float
    end: float

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(label=d["label"], start=float(d["start"]), end=float(d["end"]))


@dataclass
class BeatData:
    """Rhythm analysis. NOTE: all positions are in **milliseconds**."""

    beat_positions: list[int] = field(default_factory=list)
    beat_strengths: list[float] = field(default_factory=list)
    confidence: float = 0.0
    detection_method: str = ""
    grid_beat_positions: list[int] = field(default_factory=list)
    grid_beat_strengths: list[float] = field(default_factory=list)
    grid_confidence: float = 0.0
    onset_positions: list[int] = field(default_factory=list)
    onset_strengths: list[float] = field(default_factory=list)
    first_downbeat_ms: int = 0
    bpm: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "BeatData":
        return cls(
            beat_positions=d.get("beat_positions", []),
            beat_strengths=d.get("beat_strengths", []),
            confidence=d.get("confidence", 0.0),
            detection_method=d.get("detection_method", ""),
            grid_beat_positions=d.get("grid_beat_positions", []),
            grid_beat_strengths=d.get("grid_beat_strengths", []),
            grid_confidence=d.get("grid_confidence", 0.0),
            onset_positions=d.get("onset_positions", []),
            onset_strengths=d.get("onset_strengths", []),
            first_downbeat_ms=d.get("first_downbeat_ms", 0),
            bpm=d.get("bpm", 0.0),
        )

    @property
    def beats_seconds(self) -> list[float]:
        """Beat positions converted to seconds for syncing with lyrics."""
        return [ms / 1000.0 for ms in self.beat_positions]


@dataclass
class IntensitySample:
    """One evenly-spaced sample of the energy envelope (time in seconds)."""

    time_s: float
    energy_score: float
    rms_volume: float
    spectral_flux: float
    brightness: float
    harmonicity: float
    percussiveness: float
    dynamic_range: float

    @classmethod
    def from_dict(cls, d: dict) -> "IntensitySample":
        return cls(
            time_s=d["time_s"],
            energy_score=d.get("energy_score", 0.0),
            rms_volume=d.get("rms_volume", 0.0),
            spectral_flux=d.get("spectral_flux", 0.0),
            brightness=d.get("brightness", 0.0),
            harmonicity=d.get("harmonicity", 0.0),
            percussiveness=d.get("percussiveness", 0.0),
            dynamic_range=d.get("dynamic_range", 0.0),
        )


@dataclass
class IntensitySections:
    """Energy envelope sampled every `interval` seconds."""

    interval: float
    data: list[IntensitySample] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "IntensitySections":
        return cls(
            interval=d.get("interval", 0.1),
            data=[IntensitySample.from_dict(s) for s in d.get("data", [])],
        )

    def at(self, t: float) -> IntensitySample | None:
        """Nearest energy sample at time `t` (seconds)."""
        if not self.data:
            return None
        idx = round(t / self.interval)
        idx = max(0, min(idx, len(self.data) - 1))
        return self.data[idx]


# --------------------------------------------------------------------------- #
# Audio analysis
# --------------------------------------------------------------------------- #
@dataclass
class AudioAnalysis:
    id: int = 0
    audio_id: int = 0
    owner_id: int = 0
    is_instrumental: bool = False
    bpm: float = 0.0
    duration: float = 0.0
    lyrics_text: str = ""
    is_aligned: bool = False
    key: str = ""
    scale: str = ""
    moods: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    beat_data: BeatData = field(default_factory=BeatData)
    segment_data: list[Segment] = field(default_factory=list)
    singer_gender: str = ""
    singer_ethnicity: str = ""
    song_description: str = ""
    video_idea: str = ""
    intensity_sections: IntensitySections = field(
        default_factory=lambda: IntensitySections(0.1, [])
    )
    beat_analysis_version: int = 0
    analysis_status: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "AudioAnalysis":
        return cls(
            id=d.get("id", 0),
            audio_id=d.get("audio_id", 0),
            owner_id=d.get("owner_id", 0),
            is_instrumental=d.get("is_instrumental", False),
            bpm=d.get("bpm", 0.0),
            duration=d.get("duration", 0.0),
            lyrics_text=d.get("lyrics_text", ""),
            is_aligned=d.get("is_aligned", False),
            key=d.get("key", ""),
            scale=d.get("scale", ""),
            moods=d.get("moods", []),
            genres=d.get("genres", []),
            beat_data=BeatData.from_dict(d.get("beat_data", {})),
            segment_data=[Segment.from_dict(s) for s in d.get("segment_data", [])],
            singer_gender=d.get("singer_gender", ""),
            singer_ethnicity=d.get("singer_ethnicity", ""),
            song_description=d.get("song_description", ""),
            video_idea=d.get("video_idea", ""),
            intensity_sections=IntensitySections.from_dict(
                d.get("intensity_sections", {})
            ),
            beat_analysis_version=d.get("beat_analysis_version", 0),
            analysis_status=d.get("analysis_status", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


# --------------------------------------------------------------------------- #
# Top-level song
# --------------------------------------------------------------------------- #
@dataclass
class Song:
    found: bool = False
    filename: str = ""
    is_song: bool = False
    mp3_url: str = ""
    lyrics: list[LyricLine] = field(default_factory=list)
    audio: AudioAnalysis = field(default_factory=AudioAnalysis)

    @classmethod
    def from_dict(cls, d: dict) -> "Song":
        return cls(
            found=d.get("found", False),
            filename=d.get("filename", ""),
            is_song=d.get("is_song", False),
            mp3_url=d.get("mp3_url", ""),
            lyrics=[LyricLine.from_dict(l) for l in d.get("lyrics_json", [])],
            audio=AudioAnalysis.from_dict(d.get("audio_analysis", {})),
        )

    @classmethod
    def load(cls, path: str | Path) -> "Song":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    # -- convenience accessors -------------------------------------------- #
    @property
    def duration(self) -> float:
        return self.audio.duration

    @property
    def all_words(self) -> list[Word]:
        """Flat list of every word across all lines, in time order."""
        return [w for line in self.lyrics for w in line.words]

    def segment_at(self, t: float) -> Segment | None:
        """The structural section active at time `t` (seconds)."""
        for seg in self.audio.segment_data:
            if seg.start <= t < seg.end:
                return seg
        return None


if __name__ == "__main__":
    # Quick sanity check / summary when run directly.
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "data/songs/song_666407.json"
    song = Song.load(path)
    a = song.audio
    print(f"file:      {song.filename}")
    print(f"duration:  {a.duration:.1f}s   {a.bpm:.0f} BPM   {a.key} {a.scale}")
    print(f"moods:     {', '.join(a.moods)}")
    print(f"genres:    {', '.join(a.genres)}")
    print(f"lines:     {len(song.lyrics)}   words: {len(song.all_words)}")
    print(f"segments:  {' -> '.join(s.label for s in a.segment_data)}")
    print(f"beats:     {len(a.beat_data.beat_positions)}")
    print(f"intensity: {len(a.intensity_sections.data)} samples "
          f"@ {a.intensity_sections.interval}s")
    print(f"\ndescription: {a.song_description}")
