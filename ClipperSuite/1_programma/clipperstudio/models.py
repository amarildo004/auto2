"""Data structures used by the ClipperStudio UI and pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, List, Optional


class JobStage(Enum):
    """Represents the different stages a job can be in."""

    QUEUED = auto()
    DOWNLOADING = auto()
    PROCESSING = auto()
    PUBLISHING = auto()
    COMPLETED = auto()
    FAILED = auto()

    def label(self) -> str:  # pragma: no cover - trivial mapping
        mapping = {
            JobStage.QUEUED: "⏳ In coda",
            JobStage.DOWNLOADING: "⬇️ Download",
            JobStage.PROCESSING: "⚙️ Elaborazione",
            JobStage.PUBLISHING: "⬆️ Pubblicazione",
            JobStage.COMPLETED: "✅ Completato",
            JobStage.FAILED: "❌ Errore",
        }
        return mapping[self]


@dataclass
class ClipTiming:
    """Represents information about a single clip publication."""

    index: int
    start: float
    end: float
    duration: float
    publish_after_seconds: int


@dataclass
class SubtitleBundle:
    """Container for subtitle artefacts generated during transcription."""

    srt_path: Path
    ass_path: Path
    font_name: str


@dataclass
class VideoJob:
    """Represents a single video URL to process."""

    url: str
    workspace_id: int
    identifier: str
    download_path: Path
    processing_directory: Path
    clips_directory: Path
    published_directory: Path
    logs_directory: Path
    estimated_duration: Optional[float] = None
    clip_plan: List[ClipTiming] = field(default_factory=list)
    status: JobStage = JobStage.QUEUED
    error: Optional[str] = None

    def update_status(self, status: JobStage, error: Optional[str] = None) -> None:
        self.status = status
        self.error = error


ProgressCallback = Callable[[VideoJob, JobStage, str], None]
