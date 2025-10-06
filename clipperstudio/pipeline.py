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
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional

from .config import WorkspaceSettings
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

    def __init__(self, settings: WorkspaceSettings, callback: ProgressCallback) -> None:
        self.settings = settings
        self.logger = PipelineLogger(callback)

    # ------------------------------------------------------------------ utils
    def _check_dependency(self, name: str) -> None:
        if shutil.which(name) is None:
            raise DependencyError(
                f"Il comando '{name}' non è disponibile. Installalo prima di procedere."
            )

    def _run(self, args: List[str], cwd: Optional[Path] = None) -> None:
        subprocess.run(args, cwd=cwd, check=True)

    # ---------------------------------------------------------------- download
    def download(self, job: VideoJob) -> Path:
        self.logger.emit(job, JobStage.DOWNLOADING, "Download del video in corso…")
        self._check_dependency("yt-dlp")
        output_template = job.download_path / "%(title)s.%(ext)s"
        args = [
            "yt-dlp",
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
        self._check_dependency("ffprobe")
        args = [
            "ffprobe",
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
    def render_clips(
        self, video_file: Path, job: VideoJob, clip_plan: Iterable[ClipTiming]
    ) -> List[Path]:
        self._check_dependency("ffmpeg")
        output_files: List[Path] = []
        render_settings = self.settings.rendering
        job.clips_directory.mkdir(parents=True, exist_ok=True)
        for clip in clip_plan:
            output_file = job.clips_directory / f"clip_{clip.index:03d}.mp4"
            blur_filter = (
                "[0:v]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,gaussianblur=30[bg];"
                "[0:v]scale=1080:-2[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2"
            )
            vf_parts = [
                f"{blur_filter}",
            ]
            fontfile = None
            if render_settings.font_path:
                fontfile = render_settings.font_path.replace("'", "\\'")
            if render_settings.title:
                title = render_settings.title.replace("'", "\\'")
                drawtext = (
                    "drawtext=text='{}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=60".format(
                        title
                    )
                )
                if fontfile:
                    drawtext += f":fontfile='{fontfile}'"
                vf_parts.append(drawtext)
            if render_settings.show_part_label:
                prefix = self.settings.publication.part_label_prefix.replace(
                    "'", "\\'"
                )
                drawtext = (
                    "drawtext=text='{} {}':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=h-120".format(
                        prefix,
                        clip.index + 1,
                    )
                )
                if fontfile:
                    drawtext += f":fontfile='{fontfile}'"
                vf_parts.append(drawtext)
            vf = ",".join(vf_parts)
            args = [
                "ffmpeg",
                "-y",
                "-ss",
                str(clip.start),
                "-to",
                str(clip.end),
                "-i",
                str(video_file),
                "-vf",
                vf,
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
