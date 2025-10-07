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
        container = ttk.Frame(self, style="Workspace.TFrame", padding=24)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=0)
        container.columnconfigure(1, weight=1)
        container.columnconfigure(2, weight=0)
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container, style="Header.TFrame")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 24))
        header.columnconfigure(0, weight=1)

        brand = ttk.Label(
            header,
            text="▶ ClipperStudio",
            style="HeaderBrand.TLabel",
        )
        brand.grid(row=0, column=0, sticky="w")

        refresh_button = ttk.Button(
            header,
            text="Aggiorna stato",
            style="Ghost.TButton",
            command=lambda: None,
        )
        refresh_button.grid(row=0, column=1, padx=(12, 0), sticky="e")

        left_panel = ttk.Frame(container, style="Card.TFrame", padding=20)
        left_panel.grid(row=1, column=0, sticky="nsew")
        for index in range(4):
            left_panel.rowconfigure(index, weight=0)
        left_panel.columnconfigure(1, weight=1)

        ttk.Label(
            left_panel, text="Parametri", style="Section.TLabel"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        # Title
        ttk.Label(left_panel, text="Titolo opzionale", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.title_var = tk.StringVar(value=self.settings.rendering.title)
        title_entry = ttk.Entry(
            left_panel, textvariable=self.title_var, width=32, style="Dark.TEntry"
        )
        title_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        self.title_var.trace_add("write", self._on_title_change)

        # Font selection
        ttk.Label(left_panel, text="Font TTF", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=4
        )
        self.font_var = tk.StringVar(
            value=self.settings.rendering.font_path or "Seleziona un font…"
        )
        font_row = ttk.Frame(left_panel, style="Card.TFrame")
        font_row.grid(row=2, column=1, sticky="ew", padx=(12, 0))
        font_row.columnconfigure(0, weight=1)
        self.font_display = ttk.Label(
            font_row, textvariable=self.font_var, style="Subtle.TLabel"
        )
        self.font_display.grid(row=0, column=0, sticky="w")
        font_button = ttk.Button(
            font_row, text="Scegli…", style="Ghost.TButton", command=self._select_font_file
        )
        font_button.grid(row=0, column=1, padx=(12, 0))

        ttk.Separator(left_panel, orient="horizontal").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(16, 12)
        )

        ttk.Label(left_panel, text="Durata clip (s)", style="Card.TLabel").grid(
            row=4, column=0, sticky="w"
        )
        self.clip_duration_var = tk.IntVar(
            value=self.settings.rendering.clip_duration
        )
        clip_duration_spin = ttk.Spinbox(
            left_panel,
            from_=30,
            to=600,
            increment=10,
            textvariable=self.clip_duration_var,
            width=8,
            style="Dark.TSpinbox",
        )
        clip_duration_spin.grid(row=4, column=1, sticky="w", padx=(12, 0), pady=4)
        self.clip_duration_var.trace_add("write", self._on_clip_duration_change)

        ttk.Label(left_panel, text="Overlap (s)", style="Card.TLabel").grid(
            row=5, column=0, sticky="w"
        )
        self.overlap_var = tk.IntVar(value=self.settings.rendering.clip_overlap)
        overlap_spin = ttk.Spinbox(
            left_panel,
            from_=0,
            to=30,
            increment=1,
            textvariable=self.overlap_var,
            width=6,
            style="Dark.TSpinbox",
        )
        overlap_spin.grid(row=5, column=1, sticky="w", padx=(12, 0), pady=4)
        self.overlap_var.trace_add("write", self._on_overlap_change)

        ttk.Label(left_panel, text="Durata finale min (s)", style="Card.TLabel").grid(
            row=6, column=0, sticky="w"
        )
        self.final_min_var = tk.IntVar(value=self.settings.rendering.final_clip_min)
        final_min_spin = ttk.Spinbox(
            left_panel,
            from_=60,
            to=360,
            increment=10,
            textvariable=self.final_min_var,
            width=8,
            style="Dark.TSpinbox",
        )
        final_min_spin.grid(row=6, column=1, sticky="w", padx=(12, 0), pady=4)
        self.final_min_var.trace_add("write", self._on_final_min_change)

        ttk.Label(left_panel, text="Durata finale max (s)", style="Card.TLabel").grid(
            row=7, column=0, sticky="w"
        )
        self.final_max_var = tk.IntVar(value=self.settings.rendering.final_clip_max)
        final_max_spin = ttk.Spinbox(
            left_panel,
            from_=90,
            to=480,
            increment=10,
            textvariable=self.final_max_var,
            width=8,
            style="Dark.TSpinbox",
        )
        final_max_spin.grid(row=7, column=1, sticky="w", padx=(12, 0), pady=4)
        self.final_max_var.trace_add("write", self._on_final_max_change)

        ttk.Separator(left_panel, orient="horizontal").grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(16, 12)
        )

        ttk.Label(left_panel, text="Qualità (CRF)", style="Card.TLabel").grid(
            row=9, column=0, sticky="w"
        )
        self.crf_var = tk.IntVar(value=self.settings.rendering.crf)
        crf_spin = ttk.Spinbox(
            left_panel,
            from_=10,
            to=35,
            increment=1,
            textvariable=self.crf_var,
            width=6,
            style="Dark.TSpinbox",
        )
        crf_spin.grid(row=9, column=1, sticky="w", padx=(12, 0), pady=4)
        self.crf_var.trace_add("write", self._on_crf_change)

        ttk.Label(left_panel, text="Preset x264", style="Card.TLabel").grid(
            row=10, column=0, sticky="w"
        )
        self.preset_var = tk.StringVar(value=self.settings.rendering.x264_preset)
        preset_combo = ttk.Combobox(
            left_panel,
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
            width=12,
            state="readonly",
            style="Dark.TCombobox",
        )
        preset_combo.grid(row=10, column=1, sticky="w", padx=(12, 0), pady=4)
        self.preset_var.trace_add("write", self._on_preset_change)

        self.part_label_var = tk.BooleanVar(value=self.settings.rendering.show_part_label)
        part_check = ttk.Checkbutton(
            left_panel,
            text="Mostra 'Parte N'",
            variable=self.part_label_var,
            command=self._on_part_toggle,
            style="Card.TCheckbutton",
        )
        part_check.grid(row=11, column=0, columnspan=2, sticky="w", pady=(12, 4))

        ttk.Label(left_panel, text="Prefisso parte", style="Card.TLabel").grid(
            row=12, column=0, sticky="w"
        )
        self.part_prefix_var = tk.StringVar(
            value=self.settings.publication.part_label_prefix
        )
        part_prefix_entry = ttk.Entry(
            left_panel, textvariable=self.part_prefix_var, width=15, style="Dark.TEntry"
        )
        part_prefix_entry.grid(row=12, column=1, sticky="w", padx=(12, 0), pady=4)
        self.part_prefix_var.trace_add("write", self._on_part_prefix_change)

        ttk.Separator(left_panel, orient="horizontal").grid(
            row=13, column=0, columnspan=2, sticky="ew", pady=(16, 12)
        )

        ttk.Label(left_panel, text="Intervallo base (min)", style="Card.TLabel").grid(
            row=14, column=0, sticky="w"
        )
        self.interval_var = tk.DoubleVar(
            value=self.settings.publication.publish_interval.as_minutes()
        )
        interval_spin = ttk.Spinbox(
            left_panel,
            from_=0,
            to=180,
            increment=1,
            textvariable=self.interval_var,
            width=8,
            style="Dark.TSpinbox",
        )
        interval_spin.grid(row=14, column=1, sticky="w", padx=(12, 0), pady=4)
        self.interval_var.trace_add("write", self._on_interval_change)

        self.randomize = tk.BooleanVar(value=self.settings.publication.randomize_interval)
        self.random_button = ttk.Button(
            left_panel,
            text=self._random_button_text(),
            command=self._toggle_randomization,
            style="Toggle.TButton",
            width=22,
        )
        self.random_button.grid(row=15, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        self._update_random_button_style()

        ttk.Label(left_panel, text="Random ± (s)", style="Card.TLabel").grid(
            row=16, column=0, sticky="w"
        )
        self.random_range_var = tk.IntVar(
            value=self.settings.publication.randomization_range_seconds
        )
        random_range_spin = ttk.Spinbox(
            left_panel,
            from_=0,
            to=600,
            increment=10,
            textvariable=self.random_range_var,
            width=8,
            style="Dark.TSpinbox",
        )
        random_range_spin.grid(row=16, column=1, sticky="w", padx=(12, 0), pady=4)
        self.random_range_var.trace_add("write", self._on_random_range_change)

        center_panel = ttk.Frame(container, style="Card.TFrame", padding=20)
        center_panel.grid(row=1, column=1, sticky="nsew", padx=24)
        center_panel.columnconfigure(0, weight=1)
        center_panel.columnconfigure(1, weight=0)
        center_panel.rowconfigure(4, weight=1)

        ttk.Label(center_panel, text="Coda clip", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            center_panel,
            text="Incolla uno o più link (uno per riga)",
            style="SectionHint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))

        self.links_text = tk.Text(
            center_panel,
            height=4,
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#1e293b",
            wrap="word",
        )
        self.links_text.grid(row=2, column=0, sticky="ew")

        add_button = ttk.Button(
            center_panel,
            text="Aggiungi alla coda",
            style="Accent.TButton",
            command=self._add_links,
        )
        add_button.grid(row=3, column=0, sticky="e", pady=(12, 0))

        columns = ("id", "url", "status", "detail", "eta")
        self.tree = ttk.Treeview(
            center_panel,
            columns=columns,
            show="headings",
            height=8,
            style="Jobs.Treeview",
        )
        headings = {
            "id": "ID",
            "url": "Link",
            "status": "Stato",
            "detail": "Dettagli",
            "eta": "Stima",
        }
        for column in columns:
            self.tree.heading(column, text=headings[column], anchor="w")
            self.tree.column(
                column,
                width=140 if column not in {"detail", "url"} else 220,
                stretch=True,
                anchor="w",
            )
        self.tree.grid(row=4, column=0, sticky="nsew", pady=(16, 0))

        scrollbar = ttk.Scrollbar(
            center_panel, orient="vertical", command=self.tree.yview, style="Vertical.TScrollbar"
        )
        scrollbar.grid(row=4, column=1, sticky="ns", pady=(16, 0), padx=(6, 0))
        self.tree.configure(yscrollcommand=scrollbar.set)

        right_panel = ttk.Frame(container, style="Card.TFrame", padding=20)
        right_panel.grid(row=1, column=2, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(6, weight=1)

        ttk.Label(right_panel, text="Account", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            right_panel,
            text="Connesso con token OAuth",
            style="SectionHint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        self.token_var = tk.StringVar(
            value=self.settings.publication.tiktok_access_token
        )
        token_entry = ttk.Entry(
            right_panel,
            textvariable=self.token_var,
            show="*",
            width=28,
            style="Dark.TEntry",
        )
        token_entry.grid(row=2, column=0, sticky="ew")
        self.token_var.trace_add("write", self._on_token_change)

        ttk.Button(
            right_panel,
            text="Aggiorna token",
            style="Accent.TButton",
            command=lambda: None,
        ).grid(row=3, column=0, sticky="ew", pady=(12, 16))

        ttk.Label(right_panel, text="Log", style="Section.TLabel").grid(
            row=4, column=0, sticky="w"
        )
        ttk.Label(
            right_panel,
            text="Aggiornamenti in tempo reale",
            style="SectionHint.TLabel",
        ).grid(row=5, column=0, sticky="w", pady=(4, 8))

        self.log_text = ScrolledText(
            right_panel,
            height=12,
            state="disabled",
            bg="#0f172a",
            fg="#94a3b8",
            insertbackground="#e2e8f0",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#1e293b",
        )
        self.log_text.grid(row=6, column=0, sticky="nsew")

    # ---------------------------------------------------------------- callbacks
    def _random_button_text(self) -> str:
        return "Random delay: ON" if self.randomize.get() else "Random delay: OFF"

    def _update_random_button_style(self) -> None:
        style_name = "Accent.TButton" if self.randomize.get() else "Toggle.TButton"
        self.random_button.configure(text=self._random_button_text(), style=style_name)

    def _toggle_randomization(self) -> None:
        new_value = not self.randomize.get()
        self.randomize.set(new_value)
        self.settings.publication.randomize_interval = new_value
        self._update_random_button_style()

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
        self._configure_styles()
        self.registry = WorkspaceRegistry()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        base_bg = "#0b1220"
        card_bg = "#111827"
        accent = "#2563eb"
        subtle = "#94a3b8"
        self.configure(background=base_bg)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=base_bg)
        style.configure("Workspace.TFrame", background=base_bg)
        style.configure("Header.TFrame", background=base_bg)
        style.configure("Card.TFrame", background=card_bg, relief="flat")
        style.configure("Section.TLabel", background=card_bg, foreground="#f8fafc", font=("Segoe UI", 12, "bold"))
        style.configure("Card.TLabel", background=card_bg, foreground="#e2e8f0", font=("Segoe UI", 10))
        style.configure("Subtle.TLabel", background=card_bg, foreground=subtle, font=("Segoe UI", 9))
        style.configure("SectionHint.TLabel", background=card_bg, foreground=subtle, font=("Segoe UI", 9))
        style.configure("HeaderBrand.TLabel", background=base_bg, foreground="#f9fafb", font=("Segoe UI", 20, "bold"))
        style.configure(
            "Ghost.TButton",
            background=card_bg,
            foreground="#e2e8f0",
            padding=(12, 8),
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#1f2937"), ("pressed", "#1f2937")],
            foreground=[("disabled", "#475569")],
        )
        style.configure("Accent.TButton", background=accent, foreground="#f8fafc", padding=(12, 8), borderwidth=0)
        style.map(
            "Accent.TButton",
            background=[("active", "#1d4ed8"), ("pressed", "#1d4ed8")],
        )
        style.configure("Toggle.TButton", background="#1f2937", foreground="#f8fafc", padding=(12, 8), borderwidth=0)
        style.map(
            "Toggle.TButton",
            background=[("active", "#2563eb"), ("pressed", "#2563eb")],
        )
        style.configure("Card.TCheckbutton", background=card_bg, foreground="#e2e8f0")
        style.map(
            "Card.TCheckbutton",
            background=[("active", card_bg)],
            foreground=[("disabled", "#475569")],
        )
        style.configure("Dark.TEntry", fieldbackground="#0f172a", foreground="#f8fafc")
        style.configure("Dark.TSpinbox", fieldbackground="#0f172a", foreground="#f8fafc")
        style.configure("Dark.TCombobox", fieldbackground="#0f172a", background="#0f172a", foreground="#f8fafc")
        style.map("Dark.TCombobox", fieldbackground=[("readonly", "#0f172a")])
        style.configure("Vertical.TScrollbar", background="#1e293b", troughcolor="#0f172a")
        style.configure(
            "Jobs.Treeview",
            background=card_bg,
            fieldbackground=card_bg,
            foreground="#f8fafc",
            borderwidth=0,
            rowheight=60,
        )
        style.map(
            "Jobs.Treeview",
            background=[("selected", "#1d4ed8")],
            foreground=[("selected", "#f8fafc")],
        )
        style.configure(
            "Jobs.Treeview.Heading",
            background="#1f2937",
            foreground="#e2e8f0",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Jobs.Treeview.Heading",
            background=[("active", "#2563eb")],
            foreground=[("active", "#f8fafc")],
        )
        style.configure("TNotebook", background=base_bg, borderwidth=0)
        style.configure("TNotebook.Tab", background="#111827", foreground=subtle, padding=(16, 10))
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#1f2937")],
            foreground=[("selected", "#f8fafc")],
        )

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
