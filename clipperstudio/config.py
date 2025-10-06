"""Configuration helpers for ClipperStudio.

This module centralises defaults and constants that are shared between the
user interface and the processing pipeline.  The goal is to keep every
magic number in a single location so that the behaviour of the application is
self documenting and easy to tweak or test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Application wide defaults -------------------------------------------------

DEFAULT_CLIP_DURATION_SECONDS: int = 120
DEFAULT_CLIP_OVERLAP_SECONDS: int = 0
DEFAULT_FINAL_CLIP_MIN_SECONDS: int = 120
DEFAULT_FINAL_CLIP_MAX_SECONDS: int = 240
DEFAULT_INTERVAL_MINUTES: int = 20
DEFAULT_RANDOMIZATION_RANGE_SECONDS: int = 120
DEFAULT_CRF: int = 18
DEFAULT_X264_PRESET: str = "medium"
DEFAULT_FONT_PATH: Optional[str] = None
DEFAULT_PART_PREFIX: str = "Parte"
DEFAULT_WORKSPACE_ROOT: Path = Path("workspace_data")


@dataclass(slots=True)
class PublishInterval:
    """Represents the base interval between two clips.

    The interval is stored in seconds but can be created using a duration in
    minutes to make the UI more intuitive.  The class provides a helper for
    rendering a human readable representation that is used in the GUI.
    """

    seconds: int = field(default=DEFAULT_INTERVAL_MINUTES * 60)

    @classmethod
    def from_minutes(cls, minutes: float) -> "PublishInterval":
        return cls(int(max(0, minutes * 60)))

    def as_minutes(self) -> float:
        return self.seconds / 60

    def __str__(self) -> str:  # pragma: no cover - trivial
        minutes = self.as_minutes()
        if minutes.is_integer():
            return f"{int(minutes)} min"
        return f"{minutes:.1f} min"


@dataclass(slots=True)
class RenderingSettings:
    """Settings that control how clips are rendered."""

    title: str = ""
    font_path: Optional[str] = DEFAULT_FONT_PATH
    clip_duration: int = DEFAULT_CLIP_DURATION_SECONDS
    clip_overlap: int = DEFAULT_CLIP_OVERLAP_SECONDS
    final_clip_min: int = DEFAULT_FINAL_CLIP_MIN_SECONDS
    final_clip_max: int = DEFAULT_FINAL_CLIP_MAX_SECONDS
    crf: int = DEFAULT_CRF
    x264_preset: str = DEFAULT_X264_PRESET
    show_part_label: bool = True


@dataclass(slots=True)
class PublicationSettings:
    """Settings related to publication on TikTok."""

    publish_interval: PublishInterval = field(default_factory=PublishInterval)
    randomize_interval: bool = False
    randomization_range_seconds: int = DEFAULT_RANDOMIZATION_RANGE_SECONDS
    part_label_prefix: str = DEFAULT_PART_PREFIX
    part_label_enabled: bool = True
    part_label_spacing: int = 0
    tiktok_access_token: str = ""


@dataclass(slots=True)
class WorkspaceSettings:
    """Container that groups rendering and publication settings."""

    rendering: RenderingSettings = field(default_factory=RenderingSettings)
    publication: PublicationSettings = field(default_factory=PublicationSettings)
    download_directory: Path = field(
        default_factory=lambda: DEFAULT_WORKSPACE_ROOT / "downloads"
    )
    clips_directory: Path = field(
        default_factory=lambda: DEFAULT_WORKSPACE_ROOT / "clips"
    )

    def ensure_directories(self) -> None:
        self.download_directory.mkdir(parents=True, exist_ok=True)
        self.clips_directory.mkdir(parents=True, exist_ok=True)
