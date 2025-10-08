"""Configuration helpers for ClipperStudio.

This module centralises defaults, filesystem layout helpers and constants shared
between the GUI and the processing pipeline."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
import re

# ---------------------------------------------------------------- filesystem
PROGRAM_ROOT: Path = Path(__file__).resolve().parents[1]
CLIPPERSUITE_ROOT: Path = PROGRAM_ROOT.parent
CONFIG_DIR: Path = PROGRAM_ROOT / "config"
DOCS_DIR: Path = PROGRAM_ROOT / "docs"
DEFAULT_WORKSPACE_ROOT: Path = CLIPPERSUITE_ROOT / "2_spaziatura"
DEPENDENCIES_ROOT: Path = CLIPPERSUITE_ROOT / "3_programmi_necessari"
FFMPEG_BIN_DIR: Path = DEPENDENCIES_ROOT / "ffmpeg" / "bin"
YTDLP_DIR: Path = DEPENDENCIES_ROOT / "yt-dlp"
LAYOUTS_DIR: Path = CONFIG_DIR / "layouts"
WORKSPACE_METADATA_FILE: Path = CONFIG_DIR / "workspaces.json"

DEFAULT_SETTINGS_PAYLOAD = {
    "rendering": {
        "clip_duration_seconds": 120,
        "clip_overlap_seconds": 0,
        "final_clip_min_seconds": 120,
        "final_clip_max_seconds": 240,
        "title": "",
        "show_part_label": True,
        "font_path": None,
        "crf": 18,
        "x264_preset": "medium",
    },
    "publication": {
        "publish_interval_minutes": 20,
        "randomize_interval": False,
        "randomization_range_seconds": 120,
        "part_label_prefix": "Parte",
        "part_label_enabled": True,
        "part_label_spacing": 0,
    },
}

DEFAULT_SECRETS_EXAMPLE = {
    "tiktok_access_token": "INSERISCI_IL_TOKEN_TIKTOK",
}

DEFAULT_DOC_CONTENT = """# Documentazione ClipperStudio\n\nQuesto file viene creato automaticamente la prima volta che avvii l'applicazione.\nSostituiscilo con la documentazione definitiva del tuo progetto quando pronta.\n"""

DEFAULT_CANVAS_WIDTH = 1080
DEFAULT_CANVAS_HEIGHT = 1920

DEFAULT_LAYOUT_STATE: Dict[str, Dict[str, object]] = {
    "canvas": {
        "width": DEFAULT_CANVAS_WIDTH,
        "height": DEFAULT_CANVAS_HEIGHT,
        "safe_zones": False,
    },
    "layers": {
        "video_main": {
            "x": DEFAULT_CANVAS_WIDTH / 2,
            "y": DEFAULT_CANVAS_HEIGHT / 2,
            "w": DEFAULT_CANVAS_WIDTH,
            "h": round(DEFAULT_CANVAS_WIDTH * 9 / 16),
            "scale": 1.12,
            "fit": "width",
            "anchor": "center",
            "locked": False,
            "visible": True,
        },
        "title": {
            "x": DEFAULT_CANVAS_WIDTH / 2,
            "y": 140,
            "anchor": "center",
            "locked": False,
            "visible": True,
        },
        "subtitles": {
            "x": DEFAULT_CANVAS_WIDTH / 2,
            "y": 1180,
            "anchor": "center",
            "locked": False,
            "visible": True,
        },
        "part_label": {
            "x": DEFAULT_CANVAS_WIDTH / 2,
            "y": 1820,
            "anchor": "center",
            "locked": False,
            "visible": True,
        },
        "link_label": {
            "x": 60,
            "y": 1740,
            "anchor": "topleft",
            "locked": False,
            "visible": True,
        },
        "queue_label": {
            "x": 60,
            "y": 1780,
            "anchor": "topleft",
            "locked": False,
            "visible": True,
        },
    },
}

DEPENDENCY_HINTS = {
    "ffmpeg": FFMPEG_BIN_DIR,
    "ffprobe": FFMPEG_BIN_DIR,
    "yt-dlp": YTDLP_DIR,
}


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


@dataclass(frozen=True)
class WorkspaceDirectories:
    """Paths that belong to a single workspace instance."""

    root: Path
    downloads: Path
    processing: Path
    clips: Path
    published: Path
    logs: Path


@dataclass
class PublishInterval:
    """Represents the base interval between two clips."""

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


@dataclass
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


@dataclass
class PublicationSettings:
    """Settings related to publication on TikTok."""

    publish_interval: PublishInterval = field(default_factory=PublishInterval)
    randomize_interval: bool = False
    randomization_range_seconds: int = DEFAULT_RANDOMIZATION_RANGE_SECONDS
    part_label_prefix: str = DEFAULT_PART_PREFIX
    part_label_enabled: bool = True
    part_label_spacing: int = 0
    tiktok_access_token: str = ""


@dataclass
class WorkspaceSettings:
    """Container that groups rendering and publication settings."""

    rendering: RenderingSettings = field(default_factory=RenderingSettings)
    publication: PublicationSettings = field(default_factory=PublicationSettings)
    download_directory: Path = field(
        default_factory=lambda: DEFAULT_WORKSPACE_ROOT / "downloads"
    )
    processing_directory: Path = field(
        default_factory=lambda: DEFAULT_WORKSPACE_ROOT / "processing"
    )
    clips_directory: Path = field(
        default_factory=lambda: DEFAULT_WORKSPACE_ROOT / "clips"
    )
    published_directory: Path = field(
        default_factory=lambda: DEFAULT_WORKSPACE_ROOT / "published"
    )
    logs_directory: Path = field(
        default_factory=lambda: DEFAULT_WORKSPACE_ROOT / "logs"
    )

    def ensure_directories(self) -> None:
        for path in (
            self.download_directory,
            self.processing_directory,
            self.clips_directory,
            self.published_directory,
            self.logs_directory,
        ):
            path.mkdir(parents=True, exist_ok=True)


def ensure_project_structure() -> None:
    """Create the ClipperSuite directory layout if missing."""

    CLIPPERSUITE_ROOT.mkdir(parents=True, exist_ok=True)
    PROGRAM_ROOT.mkdir(parents=True, exist_ok=True)
    DEFAULT_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    DEPENDENCIES_ROOT.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)

    settings_path = CONFIG_DIR / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(
            json.dumps(DEFAULT_SETTINGS_PAYLOAD, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    secrets_example_path = CONFIG_DIR / "secrets.example.json"
    if not secrets_example_path.exists():
        secrets_example_path.write_text(
            json.dumps(DEFAULT_SECRETS_EXAMPLE, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    docs_readme = DOCS_DIR / "README_IT.md"
    if not docs_readme.exists():
        docs_readme.write_text(DEFAULT_DOC_CONTENT, encoding="utf-8")


def create_workspace_directories(workspace_id: int) -> WorkspaceDirectories:
    """Create a new workspace folder structure inside ``2_spaziatura``."""

    ensure_project_structure()
    root = DEFAULT_WORKSPACE_ROOT / f"workspace_{workspace_id}"

    if not root.exists():
        # Support legacy timestamped directories by migrating the newest one
        legacy_candidates = sorted(
            DEFAULT_WORKSPACE_ROOT.glob(f"workspace_{workspace_id}__*"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if legacy_candidates:
            legacy_candidates[0].rename(root)

    root.mkdir(parents=True, exist_ok=True)

    downloads = root / "downloads"
    processing = root / "processing"
    clips = root / "clips"
    published = root / "published"
    logs = root / "logs"

    for path in (root, downloads, processing, clips, published, logs):
        path.mkdir(parents=True, exist_ok=True)

    return WorkspaceDirectories(
        root=root,
        downloads=downloads,
        processing=processing,
        clips=clips,
        published=published,
        logs=logs,
    )


def workspace_layout_path(workspace_id: int) -> Path:
    ensure_project_structure()
    return LAYOUTS_DIR / f"workspace_{workspace_id}.json"


def load_workspace_layout(workspace_id: int) -> Dict[str, Dict[str, object]]:
    ensure_project_structure()
    path = workspace_layout_path(workspace_id)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "layers" in payload and "canvas" in payload:
                return payload
        except json.JSONDecodeError:
            pass
    layout = deepcopy(DEFAULT_LAYOUT_STATE)
    save_workspace_layout(workspace_id, layout)
    return layout


def save_workspace_layout(workspace_id: int, layout: Dict[str, Dict[str, object]]) -> None:
    ensure_project_structure()
    path = workspace_layout_path(workspace_id)
    path.write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding="utf-8")


def reset_workspace_layout(workspace_id: int) -> Dict[str, Dict[str, object]]:
    layout = deepcopy(DEFAULT_LAYOUT_STATE)
    save_workspace_layout(workspace_id, layout)
    return layout


def duplicate_workspace_layout(
    source_workspace_id: int, target_workspace_id: int
) -> Dict[str, Dict[str, object]]:
    source = load_workspace_layout(source_workspace_id)
    layout = deepcopy(source)
    save_workspace_layout(target_workspace_id, layout)
    return layout


def list_workspace_ids() -> List[int]:
    ensure_project_structure()
    ids: Set[int] = set()
    pattern = re.compile(r"workspace_(\d+)")
    for path in DEFAULT_WORKSPACE_ROOT.iterdir():
        if not path.is_dir():
            continue
        match = pattern.match(path.name)
        if match:
            ids.add(int(match.group(1)))
    for path in LAYOUTS_DIR.glob("workspace_*.json"):
        match = pattern.match(path.stem)
        if match:
            ids.add(int(match.group(1)))
    return sorted(ids)


def next_workspace_id(existing: Optional[Set[int]] = None) -> int:
    ensure_project_structure()
    if existing is None:
        existing = set(list_workspace_ids())
    candidate = 1
    while candidate in existing:
        candidate += 1
    return candidate


def locate_dependency(name: str) -> Optional[Path]:
    """Search for an executable either in PATH or inside 3_programmi_necessari."""

    found = shutil.which(name)
    if found:
        return Path(found)

    candidates = []
    hint_dir = DEPENDENCY_HINTS.get(name, DEPENDENCIES_ROOT)
    if name == "yt-dlp":
        candidates.append(hint_dir / "yt-dlp")
        candidates.append(hint_dir / "yt-dlp.exe")
    else:
        candidates.append(hint_dir / name)
        candidates.append(hint_dir / f"{name}.exe")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None
