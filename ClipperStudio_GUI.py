"""Main GUI module for ClipperStudio."""
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from clipperstudio.config import (
    DEFAULT_RANDOMIZATION_RANGE_SECONDS,
    DEFAULT_WORKSPACE_ROOT,
    PublishInterval,
    WorkspaceSettings,
)
from clipperstudio.models import JobStage, VideoJob
from clipperstudio.workspace import WorkspaceRegistry


class WorkspaceFrame(ttk.Frame):
    """A single workspace tab containing all controls and queue state."""

    def __init__(
        self, master: tk.Misc, workspace_id: int, registry: WorkspaceRegistry
    ) -> None:
        super().__init__(master)
        root = DEFAULT_WORKSPACE_ROOT / f"workspace_{workspace_id}"
        settings = WorkspaceSettings(
            download_directory=root / "downloads",
            clips_directory=root / "clips",
        )
        self.settings = settings
        self.workspace_id = workspace_id
        self.registry = registry
        self._ui_queue: "queue.Queue[tuple[VideoJob, JobStage, str]]" = queue.Queue()
        self.controller = registry.get_or_create(
            workspace_id, self.settings, self._on_progress
        )
        self._build_ui()
        self.after(100, self._process_ui_queue)

    # ----------------------------------------------------------------- UI setup
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        settings_frame = ttk.LabelFrame(self, text="Impostazioni rendering")
        settings_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
        settings_frame.columnconfigure(5, weight=1)

        # Title
        ttk.Label(settings_frame, text="Titolo opzionale").grid(
            row=0, column=0, sticky="w"
        )
        self.title_var = tk.StringVar(value=self.settings.rendering.title)
        title_entry = ttk.Entry(settings_frame, textvariable=self.title_var, width=40)
        title_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
        self.title_var.trace_add("write", self._on_title_change)

        # Font selection
        ttk.Label(settings_frame, text="Font TTF").grid(row=1, column=0, sticky="w")
        self.font_var = tk.StringVar(
            value=self.settings.rendering.font_path or "Seleziona un font…"
        )
        self.font_display = ttk.Label(settings_frame, textvariable=self.font_var)
        self.font_display.grid(row=1, column=1, sticky="w", padx=5)
        font_button = ttk.Button(
            settings_frame, text="Scegli…", command=self._select_font_file
        )
        font_button.grid(row=1, column=2, sticky="w")

        # Clip duration
        ttk.Label(settings_frame, text="Durata clip (s)").grid(
            row=2, column=0, sticky="w"
        )
        self.clip_duration_var = tk.IntVar(
            value=self.settings.rendering.clip_duration
        )
        clip_duration_spin = ttk.Spinbox(
            settings_frame,
            from_=30,
            to=600,
            increment=10,
            textvariable=self.clip_duration_var,
            width=8,
        )
        clip_duration_spin.grid(row=2, column=1, sticky="w", padx=5)
        self.clip_duration_var.trace_add("write", self._on_clip_duration_change)

        ttk.Label(settings_frame, text="Overlap (s)").grid(row=2, column=2, sticky="w")
        self.overlap_var = tk.IntVar(value=self.settings.rendering.clip_overlap)
        overlap_spin = ttk.Spinbox(
            settings_frame,
            from_=0,
            to=30,
            increment=1,
            textvariable=self.overlap_var,
            width=6,
        )
        overlap_spin.grid(row=2, column=3, sticky="w", padx=5)
        self.overlap_var.trace_add("write", self._on_overlap_change)

        ttk.Label(settings_frame, text="Durata finale min (s)").grid(
            row=3, column=0, sticky="w"
        )
        self.final_min_var = tk.IntVar(value=self.settings.rendering.final_clip_min)
        final_min_spin = ttk.Spinbox(
            settings_frame,
            from_=60,
            to=360,
            increment=10,
            textvariable=self.final_min_var,
            width=8,
        )
        final_min_spin.grid(row=3, column=1, sticky="w", padx=5)
        self.final_min_var.trace_add("write", self._on_final_min_change)

        ttk.Label(settings_frame, text="Durata finale max (s)").grid(
            row=3, column=2, sticky="w"
        )
        self.final_max_var = tk.IntVar(value=self.settings.rendering.final_clip_max)
        final_max_spin = ttk.Spinbox(
            settings_frame,
            from_=90,
            to=480,
            increment=10,
            textvariable=self.final_max_var,
            width=8,
        )
        final_max_spin.grid(row=3, column=3, sticky="w", padx=5)
        self.final_max_var.trace_add("write", self._on_final_max_change)

        ttk.Label(settings_frame, text="Qualità (CRF)").grid(row=4, column=0, sticky="w")
        self.crf_var = tk.IntVar(value=self.settings.rendering.crf)
        crf_spin = ttk.Spinbox(
            settings_frame, from_=10, to=35, increment=1, textvariable=self.crf_var, width=6
        )
        crf_spin.grid(row=4, column=1, sticky="w", padx=5)
        self.crf_var.trace_add("write", self._on_crf_change)

        ttk.Label(settings_frame, text="Preset x264").grid(row=4, column=2, sticky="w")
        self.preset_var = tk.StringVar(value=self.settings.rendering.x264_preset)
        preset_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.preset_var,
            values=[
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ],
            width=10,
            state="readonly",
        )
        preset_combo.grid(row=4, column=3, sticky="w", padx=5)
        self.preset_var.trace_add("write", self._on_preset_change)

        self.part_label_var = tk.BooleanVar(value=self.settings.rendering.show_part_label)
        part_check = ttk.Checkbutton(
            settings_frame,
            text="Mostra 'Parte N'",
            variable=self.part_label_var,
            command=self._on_part_toggle,
        )
        part_check.grid(row=5, column=0, sticky="w")

        ttk.Label(settings_frame, text="Prefisso parte").grid(row=5, column=1, sticky="w")
        self.part_prefix_var = tk.StringVar(
            value=self.settings.publication.part_label_prefix
        )
        part_prefix_entry = ttk.Entry(
            settings_frame, textvariable=self.part_prefix_var, width=15
        )
        part_prefix_entry.grid(row=5, column=2, sticky="w", padx=5)
        self.part_prefix_var.trace_add("write", self._on_part_prefix_change)

        # Publication settings
        publication_frame = ttk.LabelFrame(self, text="Pubblicazione")
        publication_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        publication_frame.columnconfigure(3, weight=1)
        publication_frame.rowconfigure(2, weight=1)

        ttk.Label(publication_frame, text="Intervallo base (min)").grid(
            row=0, column=0, sticky="w"
        )
        self.interval_var = tk.DoubleVar(
            value=self.settings.publication.publish_interval.as_minutes()
        )
        interval_spin = ttk.Spinbox(
            publication_frame,
            from_=0,
            to=180,
            increment=1,
            textvariable=self.interval_var,
            width=8,
        )
        interval_spin.grid(row=0, column=1, sticky="w", padx=5)
        self.interval_var.trace_add("write", self._on_interval_change)

        self.randomize = tk.BooleanVar(value=self.settings.publication.randomize_interval)
        self.random_button = ttk.Button(
            publication_frame,
            text=self._random_button_text(),
            command=self._toggle_randomization,
            width=20,
        )
        self.random_button.grid(row=0, column=2, sticky="w")

        ttk.Label(publication_frame, text="Random ± (s)").grid(row=0, column=3, sticky="w")
        self.random_range_var = tk.IntVar(
            value=self.settings.publication.randomization_range_seconds
        )
        random_range_spin = ttk.Spinbox(
            publication_frame,
            from_=0,
            to=600,
            increment=10,
            textvariable=self.random_range_var,
            width=8,
        )
        random_range_spin.grid(row=0, column=4, sticky="w", padx=5)
        self.random_range_var.trace_add("write", self._on_random_range_change)

        ttk.Label(publication_frame, text="Token TikTok").grid(row=1, column=0, sticky="w")
        self.token_var = tk.StringVar(
            value=self.settings.publication.tiktok_access_token
        )
        token_entry = ttk.Entry(
            publication_frame, textvariable=self.token_var, show="*", width=35
        )
        token_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=5)
        self.token_var.trace_add("write", self._on_token_change)

        queue_frame = ttk.Frame(publication_frame)
        queue_frame.grid(row=2, column=0, columnspan=5, sticky="nsew", pady=5)
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(1, weight=1)

        ttk.Label(queue_frame, text="Incolla link (uno per riga)").grid(
            row=0, column=0, sticky="w"
        )
        self.links_text = tk.Text(queue_frame, height=4)
        self.links_text.grid(row=1, column=0, sticky="nsew", pady=5)

        add_button = ttk.Button(queue_frame, text="Aggiungi alla coda", command=self._add_links)
        add_button.grid(row=2, column=0, sticky="e")

        tree_frame = ttk.Frame(publication_frame)
        tree_frame.grid(row=3, column=0, columnspan=5, sticky="nsew", pady=(5, 0))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        columns = ("id", "url", "status", "detail", "eta")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)
        headings = {
            "id": "ID",
            "url": "Link",
            "status": "Stato",
            "detail": "Dettagli",
            "eta": "Stima",
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=140 if column != "detail" else 240, stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = ScrolledText(log_frame, height=10, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")

    # ---------------------------------------------------------------- callbacks
    def _random_button_text(self) -> str:
        return "Random delay: ON" if self.randomize.get() else "Random delay: OFF"

    def _toggle_randomization(self) -> None:
        new_value = not self.randomize.get()
        self.randomize.set(new_value)
        self.settings.publication.randomize_interval = new_value
        self.random_button.configure(text=self._random_button_text())

    def _on_title_change(self, *_: object) -> None:
        self.settings.rendering.title = self.title_var.get().strip()

    def _on_clip_duration_change(self, *_: object) -> None:
        try:
            self.settings.rendering.clip_duration = int(self.clip_duration_var.get())
        except tk.TclError:
            pass

    def _on_overlap_change(self, *_: object) -> None:
        try:
            self.settings.rendering.clip_overlap = int(self.overlap_var.get())
        except tk.TclError:
            pass

    def _on_final_min_change(self, *_: object) -> None:
        try:
            self.settings.rendering.final_clip_min = int(self.final_min_var.get())
        except tk.TclError:
            pass

    def _on_final_max_change(self, *_: object) -> None:
        try:
            self.settings.rendering.final_clip_max = int(self.final_max_var.get())
        except tk.TclError:
            pass

    def _on_crf_change(self, *_: object) -> None:
        try:
            self.settings.rendering.crf = int(self.crf_var.get())
        except tk.TclError:
            pass

    def _on_preset_change(self, *_: object) -> None:
        self.settings.rendering.x264_preset = self.preset_var.get()

    def _on_part_toggle(self) -> None:
        value = bool(self.part_label_var.get())
        self.settings.rendering.show_part_label = value
        self.settings.publication.part_label_enabled = value

    def _on_part_prefix_change(self, *_: object) -> None:
        self.settings.publication.part_label_prefix = self.part_prefix_var.get().strip() or "Parte"

    def _on_interval_change(self, *_: object) -> None:
        try:
            minutes = float(self.interval_var.get())
        except tk.TclError:
            return
        self.settings.publication.publish_interval = PublishInterval.from_minutes(minutes)

    def _on_random_range_change(self, *_: object) -> None:
        try:
            value = int(self.random_range_var.get())
        except tk.TclError:
            return
        if value < 0:
            value = DEFAULT_RANDOMIZATION_RANGE_SECONDS
            self.random_range_var.set(value)
        self.settings.publication.randomization_range_seconds = value

    def _on_token_change(self, *_: object) -> None:
        self.settings.publication.tiktok_access_token = self.token_var.get().strip()

    def _select_font_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleziona font",
            filetypes=[("Font TrueType", "*.ttf"), ("Tutti i file", "*.*")],
        )
        if path:
            self.settings.rendering.font_path = path
            self.font_var.set(path)

    def _add_links(self) -> None:
        raw = self.links_text.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showinfo("ClipperStudio", "Inserisci almeno un link.")
            return
        links = [line.strip() for line in raw.splitlines() if line.strip()]
        for link in links:
            self.controller.submit(link)
        self.links_text.delete("1.0", tk.END)

    def _on_progress(self, job: VideoJob, stage: JobStage, message: str) -> None:
        self._ui_queue.put((job, stage, message))

    def _process_ui_queue(self) -> None:
        try:
            while True:
                job, stage, message = self._ui_queue.get_nowait()
                self._update_job(job, stage, message)
        except queue.Empty:
            pass
        finally:
            self.after(150, self._process_ui_queue)

    def _ensure_tree_item(self, job: VideoJob) -> str:
        item_id = job.identifier
        if not self.tree.exists(item_id):
            self.tree.insert(
                "",
                "end",
                iid=item_id,
                values=(job.identifier, job.url, job.status.label(), "", "—"),
            )
        return item_id

    def _update_job(self, job: VideoJob, stage: JobStage, message: str) -> None:
        if stage is JobStage.FAILED:
            job.update_status(stage, job.error)
        else:
            job.update_status(stage)
        item_id = self._ensure_tree_item(job)
        estimate = self.controller.estimate_completion(job)
        eta_text = estimate or "—"
        self.tree.item(
            item_id,
            values=(job.identifier, job.url, stage.label(), message, eta_text),
        )
        self._append_log(job, stage, message)

    def _append_log(self, job: VideoJob, stage: JobStage, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(
            tk.END,
            f"[{job.identifier}] {stage.label()}: {message}\n",
        )
        self.log_text.configure(state="disabled")
        self.log_text.yview_moveto(1.0)


class ClipperStudioApp(tk.Tk):
    """Main Tkinter application."""

    def __init__(self) -> None:
        super().__init__()
        self.title("ClipperStudio")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        self.registry = WorkspaceRegistry()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        for index in range(1, 4):
            frame = WorkspaceFrame(notebook, index, self.registry)
            notebook.add(frame, text=f"Scheda {index}")

    def _on_close(self) -> None:
        self.registry.stop_all()
        self.destroy()


def main() -> None:
    app = ClipperStudioApp()
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover - GUI entry point
    main()
