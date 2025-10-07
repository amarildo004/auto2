"""Workspace management for ClipperStudio."""
from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import WorkspaceSettings
from .models import JobStage, ProgressCallback, VideoJob
from .pipeline import ClipperPipeline, DependencyError
from .utils import format_timedelta


@dataclass(slots=True)
class QueueItem:
    job: VideoJob
    created_at: float = field(default_factory=time.time)


class WorkspaceController:
    """Serial controller responsible for handling jobs in a workspace."""

    def __init__(
        self,
        workspace_id: int,
        settings: WorkspaceSettings,
        callback: ProgressCallback,
    ) -> None:
        self.workspace_id = workspace_id
        self.settings = settings
        self.callback = callback
        self._queue: "queue.Queue[QueueItem]" = queue.Queue()
        self._stop_event = threading.Event()
        self.pipeline = ClipperPipeline(settings, self._emit, workspace_id)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        self.active_job: Optional[VideoJob] = None

    # ----------------------------------------------------------------- helpers
    def _emit(self, job: VideoJob, stage: JobStage, message: str) -> None:
        self.callback(job, stage, message)

    def submit(self, url: str) -> VideoJob:
        identifier = uuid.uuid4().hex[:8]
        self.settings.ensure_directories()
        download_dir = self.settings.download_directory / f"job_{identifier}"
        processing_dir = self.settings.processing_directory / f"job_{identifier}"
        clips_dir = self.settings.clips_directory / f"job_{identifier}"
        published_dir = self.settings.published_directory / f"job_{identifier}"
        logs_dir = self.settings.logs_directory / f"job_{identifier}"
        for path in (download_dir, processing_dir, clips_dir, published_dir, logs_dir):
            path.mkdir(parents=True, exist_ok=True)
        job = VideoJob(
            url=url,
            workspace_id=self.workspace_id,
            identifier=identifier,
            download_path=download_dir,
            processing_directory=processing_dir,
            clips_directory=clips_dir,
            published_directory=published_dir,
            logs_directory=logs_dir,
        )
        self._queue.put(QueueItem(job))
        self._emit(job, JobStage.QUEUED, "In coda")
        return job

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1)

    # ------------------------------------------------------------------- worker
    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                queue_item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            job = queue_item.job
            self.active_job = job
            try:
                self.pipeline.process_job(job)
            except DependencyError as exc:
                job.update_status(JobStage.FAILED, str(exc))
                self._emit(job, JobStage.FAILED, str(exc))
            except Exception as exc:  # pragma: no cover - safety net
                job.update_status(JobStage.FAILED, str(exc))
                self._emit(job, JobStage.FAILED, f"Errore inatteso: {exc}")
            finally:
                self.active_job = None
                self._queue.task_done()

    # --------------------------------------------------------------- estimation
    def estimate_completion(self, job: VideoJob) -> Optional[str]:
        if not job.clip_plan:
            return None
        base = self.settings.publication.publish_interval.seconds
        intervals = [
            clip.publish_after_seconds if clip.publish_after_seconds else max(0, base)
            for clip in job.clip_plan
        ]
        estimate_seconds = sum(intervals)
        if estimate_seconds <= 0:
            return None
        return format_timedelta(estimate_seconds)


class WorkspaceRegistry:
    """Keeps track of the controllers for each workspace tab."""

    def __init__(self) -> None:
        self._controllers: Dict[int, WorkspaceController] = {}

    def get_or_create(
        self, workspace_id: int, settings: WorkspaceSettings, callback: ProgressCallback
    ) -> WorkspaceController:
        if workspace_id not in self._controllers:
            self._controllers[workspace_id] = WorkspaceController(
                workspace_id, settings, callback
            )
        return self._controllers[workspace_id]

    def stop_all(self) -> None:
        for controller in self._controllers.values():
            controller.stop()

    def remove(self, workspace_id: int) -> None:
        controller = self._controllers.pop(workspace_id, None)
        if controller:
            controller.stop()
