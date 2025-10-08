"""Processing pipeline for ClipperStudio.

The real application communicates with external binaries (``yt-dlp`` and
``ffmpeg``) as well as machine learning models (OpenAI Whisper).  The goal of
this module is to provide a thin orchestration layer that manages files and
keeps the GUI decoupled from long running tasks.  The concrete implementation
contains a number of guard rails so that the software remains usable even when
some optional dependencies are missing.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .config import (
    CLIPPERSUITE_ROOT,
    DEPENDENCIES_ROOT,
    DEPENDENCY_HINTS,
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    WorkspaceSettings,
    load_workspace_layout,
    locate_dependency,
)
from .models import ClipTiming, JobStage, ProgressCallback, VideoJob
from .utils import generate_clip_plan, randomise_interval


class DependencyError(RuntimeError):
    """Raised when an optional dependency is not available."""


class PipelineLogger:
    """Simple thread-safe logger used by the pipeline."""

    def __init__(self, callback: ProgressCallback) -> None:
        self._callback = callback
        self._lock = threading.Lock()

    def emit(self, job: VideoJob, stage: JobStage, message: str) -> None:
        with self._lock:
            self._callback(job, stage, message)


class ClipperPipeline:
    """High level façade that exposes the operations required by the GUI."""

    def __init__(
        self,
        settings: WorkspaceSettings,
        callback: ProgressCallback,
        workspace_id: int,
    ) -> None:
        self.settings = settings
        self.logger = PipelineLogger(callback)
        self._executables: Dict[str, str] = {}
        self.workspace_id = workspace_id

    # ------------------------------------------------------------------ utils
    def _resolve_executable(self, name: str) -> str:
        if name not in self._executables:
            executable = locate_dependency(name)
            if executable is None:
                hint_dir = DEPENDENCY_HINTS.get(name, DEPENDENCIES_ROOT)
                try:
                    display_hint = hint_dir.relative_to(CLIPPERSUITE_ROOT)
                except ValueError:
                    display_hint = hint_dir
                raise DependencyError(
                    (
                        f"Il comando '{name}' non è disponibile. "
                        f"Installa il programma oppure copialo in '{display_hint}'."
                    )
                )
            self._executables[name] = str(executable)
        return self._executables[name]

    def _run(self, args: List[str], cwd: Optional[Path] = None) -> None:
        subprocess.run(args, cwd=cwd, check=True)

    # ---------------------------------------------------------------- download
    def download(self, job: VideoJob) -> Path:
        self.logger.emit(job, JobStage.DOWNLOADING, "Download del video in corso…")
        yt_dlp = self._resolve_executable("yt-dlp")
        output_template = job.download_path / "%(title)s.%(ext)s"
        args = [
            yt_dlp,
            job.url,
            "-o",
            str(output_template),
            "--restrict-filenames",
        ]
        self._run(args)
        files = [file for file in job.download_path.iterdir() if file.is_file()]
        if not files:
            raise RuntimeError("Download fallito: nessun file creato")
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return files[0]

    # --------------------------------------------------------------- inspection
    def probe_duration(self, video_file: Path) -> float:
        ffprobe = self._resolve_executable("ffprobe")
        args = [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_file),
        ]
        completed = subprocess.run(args, capture_output=True, text=True, check=True)
        payload = json.loads(completed.stdout)
        duration = float(payload["format"]["duration"])
        return duration

    # ------------------------------------------------------------- clip render
    def _anchor_offset(self, anchor: str, width: int, height: int) -> Tuple[int, int]:
        anchor = anchor.lower()
        if anchor == "topleft":
            return (0, 0)
        if anchor == "topright":
            return (-width, 0)
        if anchor == "bottomleft":
            return (0, -height)
        if anchor == "bottomright":
            return (-width, -height)
        if anchor == "top":
            return (-width // 2, 0)
        if anchor == "bottom":
            return (-width // 2, -height)
        if anchor == "left":
            return (0, -height // 2)
        if anchor == "right":
            return (-width, -height // 2)
        return (-width // 2, -height // 2)

    def _text_position(self, anchor: str, axis: str, value: int) -> str:
        anchor = anchor.lower()
        if anchor == "topleft":
            return str(value)
        if anchor == "topright":
            return f"{value} - text_w"
        if anchor == "bottomleft":
            return f"{value} - text_h" if axis == "y" else str(value)
        if anchor == "bottomright":
            if axis == "x":
                return f"{value} - text_w"
            return f"{value} - text_h"
        if anchor == "top":
            if axis == "x":
                return f"{value} - text_w/2"
            return str(value)
        if anchor == "bottom":
            if axis == "x":
                return f"{value} - text_w/2"
            return f"{value} - text_h"
        if anchor == "left":
            if axis == "x":
                return str(value)
            return f"{value} - text_h/2"
        if anchor == "right":
            if axis == "x":
                return f"{value} - text_w"
            return f"{value} - text_h/2"
        # center default
        if axis == "x":
            return f"{value} - text_w/2"
        return f"{value} - text_h/2"

    def render_clips(
        self, video_file: Path, job: VideoJob, clip_plan: Iterable[ClipTiming]
    ) -> List[Path]:
        ffmpeg = self._resolve_executable("ffmpeg")
        output_files: List[Path] = []
        render_settings = self.settings.rendering
        job.clips_directory.mkdir(parents=True, exist_ok=True)
        layout = load_workspace_layout(job.workspace_id)
        canvas_config = layout.get("canvas", {})
        canvas_width = int(canvas_config.get("width", DEFAULT_CANVAS_WIDTH))
        canvas_height = int(canvas_config.get("height", DEFAULT_CANVAS_HEIGHT))
        layers = layout.get("layers", {})
        video_layer = layers.get("video_main", {})
        video_scale = float(video_layer.get("scale", 1.0))
        fit_mode = str(video_layer.get("fit", "width")).lower()
        if fit_mode == "height":
            target_height = max(1, int(round(canvas_height * video_scale)))
            target_width = max(1, int(round(target_height * 16 / 9)))
        else:
            target_width = max(1, int(round(canvas_width * video_scale)))
            target_height = max(1, int(round(target_width * 9 / 16)))
        anchor = str(video_layer.get("anchor", "center"))
        vx = float(video_layer.get("x", canvas_width / 2))
        vy = float(video_layer.get("y", canvas_height / 2))
        offset_x, offset_y = self._anchor_offset(anchor, target_width, target_height)
        overlay_x = int(round(vx + offset_x))
        overlay_y = int(round(vy + offset_y))

        def clamp_overlay(value: int, canvas_extent: int, target_extent: int) -> int:
            """Clamp overlay coordinate while preserving centring for zoomed layers."""

            lower = min(0, canvas_extent - target_extent)
            upper = max(0, canvas_extent - target_extent)
            if value < lower:
                return lower
            if value > upper:
                return upper
            return value

        overlay_x = clamp_overlay(overlay_x, canvas_width, target_width)
        overlay_y = clamp_overlay(overlay_y, canvas_height, target_height)

        for clip in clip_plan:
            output_file = job.clips_directory / f"clip_{clip.index:03d}.mp4"
            filter_statements = [
                f"[0:v]scale={canvas_width}:{canvas_height},gblur=sigma=30[bg]",
                f"[0:v]scale={target_width}:{target_height}[fg]",
                f"[bg][fg]overlay={overlay_x}:{overlay_y}[base]",
            ]
            current_label = "base"
            fontfile = None
            if render_settings.font_path:
                fontfile = render_settings.font_path.replace("'", "\\'")
            title_layer = layers.get("title", {})
            if render_settings.title and title_layer.get("visible", True):
                title = render_settings.title.replace("'", "\\'")
                tx = int(round(title_layer.get("x", canvas_width / 2)))
                ty = int(round(title_layer.get("y", 140)))
                x_expr = self._text_position(title_layer.get("anchor", "center"), "x", tx)
                y_expr = self._text_position(title_layer.get("anchor", "center"), "y", ty)
                drawtext = (
                    f"[{current_label}]drawtext=text='{title}':fontcolor=white:"
                    f"fontsize=56:x={x_expr}:y={y_expr}:line_spacing=6"
                )
                if fontfile:
                    drawtext += f":fontfile='{fontfile}'"
                next_label = f"v_title_{clip.index}"
                drawtext += f"[{next_label}]"
                filter_statements.append(drawtext)
                current_label = next_label
            if render_settings.show_part_label:
                part_layer = layers.get("part_label", {})
                if part_layer.get("visible", True):
                    prefix = self.settings.publication.part_label_prefix.replace(
                        "'", "\\'"
                    )
                    part_text = f"{prefix} {clip.index + 1}"
                    escaped_part = part_text.replace("'", "\\'")
                    px = int(round(part_layer.get("x", canvas_width / 2)))
                    py = int(round(part_layer.get("y", canvas_height - 120)))
                    x_expr = self._text_position(
                        part_layer.get("anchor", "center"), "x", px
                    )
                    y_expr = self._text_position(
                        part_layer.get("anchor", "center"), "y", py
                    )
                    drawtext = (
                        f"[{current_label}]drawtext=text='{escaped_part}':"
                        "fontcolor=white:fontsize=44:x="
                        f"{x_expr}:y={y_expr}:box=1:boxcolor=#00000066:boxborderw=18"
                    )
                    if fontfile:
                        drawtext += f":fontfile='{fontfile}'"
                    next_label = f"v_part_{clip.index}"
                    drawtext += f"[{next_label}]"
                    filter_statements.append(drawtext)
                    current_label = next_label
            link_layer = layers.get("link_label", {})
            if link_layer.get("visible", True):
                url_text = job.url.replace("'", "\\'")
                lx = int(round(link_layer.get("x", 60)))
                ly = int(round(link_layer.get("y", canvas_height - 160)))
                x_expr = self._text_position(link_layer.get("anchor", "topleft"), "x", lx)
                y_expr = self._text_position(link_layer.get("anchor", "topleft"), "y", ly)
                drawtext = (
                    f"[{current_label}]drawtext=text='{url_text}':fontcolor=#e2e8f0:"
                    f"fontsize=32:x={x_expr}:y={y_expr}:box=1:boxcolor=#020617aa:boxborderw=12"
                )
                if fontfile:
                    drawtext += f":fontfile='{fontfile}'"
                next_label = f"v_link_{clip.index}"
                drawtext += f"[{next_label}]"
                filter_statements.append(drawtext)
                current_label = next_label
            queue_layer = layers.get("queue_label", {})
            if queue_layer.get("visible", True) and job.clip_plan:
                queue_text = f"Clip {clip.index + 1}/{len(job.clip_plan)}"
                qx = int(round(queue_layer.get("x", 60)))
                qy = int(round(queue_layer.get("y", canvas_height - 120)))
                x_expr = self._text_position(queue_layer.get("anchor", "topleft"), "x", qx)
                y_expr = self._text_position(queue_layer.get("anchor", "topleft"), "y", qy)
                drawtext = (
                    f"[{current_label}]drawtext=text='{queue_text}':fontcolor=#94a3b8:"
                    f"fontsize=26:x={x_expr}:y={y_expr}:box=1:boxcolor=#020617aa:boxborderw=10"
                )
                if fontfile:
                    drawtext += f":fontfile='{fontfile}'"
                next_label = f"v_queue_{clip.index}"
                drawtext += f"[{next_label}]"
                filter_statements.append(drawtext)
                current_label = next_label

            filter_graph = ";".join(filter_statements)
            args = [
                ffmpeg,
                "-y",
                "-ss",
                str(clip.start),
                "-to",
                str(clip.end),
                "-i",
                str(video_file),
                "-filter_complex",
                filter_graph,
                "-map",
                f"[{current_label}]",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                render_settings.x264_preset,
                "-crf",
                str(render_settings.crf),
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(output_file),
            ]
            self._run(args)
            output_files.append(output_file)
        return output_files

    # ------------------------------------------------------------- transcription
    def transcribe(self, video_file: Path, job: VideoJob) -> Optional[Path]:
        try:
            import whisper  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            self.logger.emit(
                job,
                JobStage.PROCESSING,
                "Whisper non disponibile: sottotitoli disattivati",
            )
            return None

        model = whisper.load_model("small")
        result = model.transcribe(str(video_file))
        srt_path = job.clips_directory / f"{video_file.stem}.srt"
        with open(srt_path, "w", encoding="utf-8") as handle:
            for idx, segment in enumerate(result["segments"], start=1):
                start = time.strftime(
                    "%H:%M:%S,%f", time.gmtime(segment["start"])
                )[:-3]
                end = time.strftime("%H:%M:%S,%f", time.gmtime(segment["end"]))[:-3]
                handle.write(f"{idx}\n{start} --> {end}\n{segment['text'].strip()}\n\n")
        return srt_path

    # ------------------------------------------------------------- publication
    def publish_clips(self, clips: Iterable[Path], job: VideoJob) -> None:
        publication = self.settings.publication
        base_interval = publication.publish_interval.seconds
        variation = publication.randomization_range_seconds
        for index, (clip_meta, clip_file) in enumerate(zip(job.clip_plan, clips)):
            if publication.randomize_interval:
                publish_after = randomise_interval(base_interval, variation)
            else:
                publish_after = max(0, base_interval)
            self.logger.emit(
                job,
                JobStage.PUBLISHING,
                f"Clip {index + 1}: attesa {publish_after} secondi prima della pubblicazione",
            )
            clip_meta.publish_after_seconds = publish_after
            # Here we would interact with the TikTok API using the access token.
            # To keep the sample self contained, we only simulate a delay.
            simulated_wait = min(publish_after, 5)
            if simulated_wait:
                time.sleep(simulated_wait)
            log_path = job.published_directory / f"clip_{index + 1:03d}.txt"
            try:
                log_path.write_text(
                    (
                        f"clip: {clip_file.name}\n"
                        f"ritardo_secondi: {publish_after}\n"
                    ),
                    encoding="utf-8",
                )
            except OSError:
                pass
        # Simulate successful publication by removing files after loop in cleanup.

    # --------------------------------------------------------------- clean up
    def cleanup(self, job: VideoJob) -> None:
        if job.download_path.exists():
            for file in job.download_path.iterdir():
                if file.is_file():
                    file.unlink()
            try:
                job.download_path.rmdir()
            except OSError:  # pragma: no cover - best effort cleanup
                pass
        if job.processing_directory.exists():
            for file in job.processing_directory.iterdir():
                if file.is_file():
                    file.unlink()
            try:
                job.processing_directory.rmdir()
            except OSError:
                pass
        if job.clips_directory.exists() and job.status is JobStage.COMPLETED:
            for file in job.clips_directory.iterdir():
                if file.is_file():
                    file.unlink()
            try:
                job.clips_directory.rmdir()
            except OSError:  # pragma: no cover - best effort cleanup
                pass
        # clips are deleted only after publication has succeeded, therefore we
        # leave them on disk until the publish step returns without raising.

    # -------------------------------------------------------------------- main
    def process_job(self, job: VideoJob) -> None:
        self.settings.ensure_directories()
        job.update_status(JobStage.DOWNLOADING)
        self.logger.emit(job, JobStage.DOWNLOADING, "Download in corso…")
        video_file = self.download(job)
        job.update_status(JobStage.PROCESSING)
        duration = self.probe_duration(video_file)
        job.estimated_duration = duration
        clip_ranges = generate_clip_plan(
            duration,
            clip_duration=self.settings.rendering.clip_duration,
            overlap=self.settings.rendering.clip_overlap,
            final_min=self.settings.rendering.final_clip_min,
            final_max=self.settings.rendering.final_clip_max,
        )
        job.clip_plan = [
            ClipTiming(
                index=index,
                start=start,
                end=end,
                duration=end - start,
                publish_after_seconds=0,
            )
            for index, (start, end) in enumerate(clip_ranges)
        ]
        self.logger.emit(job, JobStage.PROCESSING, "Rendering clip…")
        clips = self.render_clips(video_file, job, job.clip_plan)
        self.logger.emit(job, JobStage.PROCESSING, "Trascrizione audio…")
        subtitle_path = self.transcribe(video_file, job)
        if subtitle_path:
            self.logger.emit(job, JobStage.PROCESSING, f"Sottotitoli: {subtitle_path.name}")
        job.update_status(JobStage.PUBLISHING)
        self.logger.emit(job, JobStage.PUBLISHING, "Pubblicazione delle clip…")
        self.publish_clips(clips, job)
        job.update_status(JobStage.COMPLETED)
        self.logger.emit(job, JobStage.COMPLETED, "Completato")
        self.cleanup(job)
