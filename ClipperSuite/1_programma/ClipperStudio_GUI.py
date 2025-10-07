"""Main GUI module for ClipperStudio."""
from __future__ import annotations

import queue
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from clipperstudio.config import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    DEFAULT_RANDOMIZATION_RANGE_SECONDS,
    PublishInterval,
    WorkspaceSettings,
    create_workspace_directories,
    duplicate_workspace_layout,
    ensure_project_structure,
    list_workspace_ids,
    load_workspace_layout,
    next_workspace_id,
    reset_workspace_layout,
    save_workspace_layout,
)
from clipperstudio.models import JobStage, VideoJob
from clipperstudio.workspace import WorkspaceRegistry


ensure_project_structure()


class LayerEditor(ttk.Frame):
    """Interactive 9:16 canvas used to arrange visual layers."""

    LAYER_ORDER = [
        "video_main",
        "title",
        "subtitles",
        "part_label",
        "link_label",
        "queue_label",
    ]

    LAYER_META = {
        "video_main": {"label": "VIDEO", "color": "#1d4ed8", "type": "video"},
        "title": {
            "label": "TITOLO (drag)",
            "color": "#0ea5e9",
            "width": 800,
            "height": 140,
        },
        "subtitles": {
            "label": "sottotitoli (drag)",
            "color": "#f97316",
            "width": 900,
            "height": 260,
        },
        "part_label": {
            "label": "PART N (drag)",
            "color": "#22c55e",
            "width": 540,
            "height": 120,
        },
        "link_label": {
            "label": "youtube.com/...",
            "color": "#c084fc",
            "width": 560,
            "height": 90,
        },
        "queue_label": {
            "label": "queue info",
            "color": "#facc15",
            "width": 500,
            "height": 80,
        },
    }

    def __init__(
        self,
        master: tk.Misc,
        layout_state: dict,
        on_change: Callable[[dict], None],
    ) -> None:
        super().__init__(master, style="Card.TFrame")
        self.layout_state = layout_state
        self._on_change = on_change
        self.layout_state.setdefault("canvas", {})
        layers = self.layout_state.setdefault("layers", {})
        for layer in self.LAYER_ORDER:
            layers.setdefault(layer, {})
        self.display_scale = 0.45
        self.canvas_width = int(DEFAULT_CANVAS_WIDTH * self.display_scale)
        self.canvas_height = int(DEFAULT_CANVAS_HEIGHT * self.display_scale)
        self.selected_layer: str = "video_main"
        self.dragging_layer: Optional[str] = None
        self._drag_start: Optional[Tuple[float, float]] = None
        self._layer_start: Optional[Tuple[float, float]] = None
        self.layer_items: Dict[str, Dict[str, int]] = {}
        self.layer_rows: Dict[str, ttk.Frame] = {}
        self.visible_vars: Dict[str, tk.BooleanVar] = {}
        self.lock_vars: Dict[str, tk.BooleanVar] = {}
        self.zoom_var = tk.DoubleVar(
            value=float(self.layout_state["layers"]["video_main"].get("scale", 1.12))
        )
        self.zoom_label_var = tk.StringVar(value=self._zoom_text(self.zoom_var.get()))
        self.fit_var = tk.StringVar(
            value=str(self.layout_state["layers"]["video_main"].get("fit", "width"))
        )
        self.safe_zones_var = tk.BooleanVar(
            value=bool(self.layout_state.get("canvas", {}).get("safe_zones", False))
        )
        self.snap_threshold = 8
        self._building = False
        self._build()

    # ----------------------------------------------------------------- helpers
    def _build(self) -> None:
        self._building = True
        for column in range(3):
            self.columnconfigure(column, weight=0)
        self.columnconfigure(1, weight=1)

        canvas_container = ttk.Frame(self, style="Card.TFrame")
        canvas_container.grid(row=0, column=0, rowspan=6, sticky="ns", padx=(0, 20))

        ttk.Label(
            canvas_container,
            text="Canvas 1080×1920",
            style="Section.TLabel",
        ).pack(anchor="center", pady=(0, 12))

        self.canvas = tk.Canvas(
            canvas_container,
            width=self.canvas_width,
            height=self.canvas_height,
            bg="#020617",
            highlightthickness=0,
        )
        self.canvas.pack()
        self.canvas.create_rectangle(
            0,
            0,
            self.canvas_width,
            self.canvas_height,
            fill="#020617",
            outline="#1f2937",
        )

        safe_color = "#facc1566"
        zone_height = int(180 * self.display_scale)
        self.safe_zone_top = self.canvas.create_rectangle(
            0,
            0,
            self.canvas_width,
            zone_height,
            fill=safe_color,
            outline="",
            state="hidden",
        )
        self.safe_zone_bottom = self.canvas.create_rectangle(
            0,
            self.canvas_height - zone_height,
            self.canvas_width,
            self.canvas_height,
            fill=safe_color,
            outline="",
            state="hidden",
        )

        self.guide_vertical = self.canvas.create_line(
            self.canvas_width // 2,
            0,
            self.canvas_width // 2,
            self.canvas_height,
            fill="#7c3aed",
            dash=(6, 4),
            width=2,
            state="hidden",
        )
        self.guide_horizontal = self.canvas.create_line(
            0,
            self.canvas_height // 2,
            self.canvas_width,
            self.canvas_height // 2,
            fill="#7c3aed",
            dash=(6, 4),
            width=2,
            state="hidden",
        )

        control_panel = ttk.Frame(self, style="Card.TFrame")
        control_panel.grid(row=0, column=1, sticky="nsew")
        control_panel.columnconfigure(1, weight=1)

        ttk.Label(control_panel, text="Livelli", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )

        for index, layer in enumerate(self.LAYER_ORDER, start=1):
            row = ttk.Frame(control_panel, style="LayerRow.TFrame", padding=(6, 4))
            row.grid(row=index, column=0, columnspan=3, sticky="ew", pady=2)
            row.bind("<Button-1>", lambda _e, name=layer: self.select_layer(name))
            label_text = layer.replace("_", " ").title()
            ttk.Label(row, text=label_text, style="Card.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            visible_var = tk.BooleanVar(
                value=bool(self.layout_state["layers"].get(layer, {}).get("visible", True))
            )
            lock_var = tk.BooleanVar(
                value=bool(self.layout_state["layers"].get(layer, {}).get("locked", False))
            )
            visible_btn = ttk.Checkbutton(
                row,
                text="👁",
                variable=visible_var,
                style="Layer.TCheckbutton",
                command=lambda name=layer, var=visible_var: self.set_layer_visibility(
                    name, bool(var.get())
                ),
            )
            visible_btn.grid(row=0, column=1, padx=6)
            lock_btn = ttk.Checkbutton(
                row,
                text="🔒",
                variable=lock_var,
                style="Layer.TCheckbutton",
                command=lambda name=layer, var=lock_var: self.set_layer_locked(
                    name, bool(var.get())
                ),
            )
            lock_btn.grid(row=0, column=2, padx=6)
            self.visible_vars[layer] = visible_var
            self.lock_vars[layer] = lock_var
            self.layer_rows[layer] = row

        slider_row = ttk.Frame(control_panel, style="Card.TFrame", padding=(0, 12))
        slider_row.grid(row=len(self.LAYER_ORDER) + 2, column=0, columnspan=3, sticky="ew")
        ttk.Label(slider_row, text="Zoom video", style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(slider_row, textvariable=self.zoom_label_var, style="Subtle.TLabel").grid(
            row=0, column=1, sticky="e"
        )
        zoom_slider = ttk.Scale(
            slider_row,
            from_=0.8,
            to=1.6,
            orient="horizontal",
            variable=self.zoom_var,
            command=self._on_zoom_change,
        )
        zoom_slider.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        fit_row = ttk.Frame(control_panel, style="Card.TFrame", padding=(0, 8))
        fit_row.grid(row=len(self.LAYER_ORDER) + 3, column=0, columnspan=3, sticky="ew")
        ttk.Radiobutton(
            fit_row,
            text="Fit width",
            value="width",
            variable=self.fit_var,
            command=self._on_fit_change,
            style="Layer.TRadiobutton",
        ).grid(row=0, column=0, padx=(0, 12))
        ttk.Radiobutton(
            fit_row,
            text="Fit height",
            value="height",
            variable=self.fit_var,
            command=self._on_fit_change,
            style="Layer.TRadiobutton",
        ).grid(row=0, column=1)

        safe_row = ttk.Frame(control_panel, style="Card.TFrame")
        safe_row.grid(row=len(self.LAYER_ORDER) + 4, column=0, columnspan=3, sticky="ew")
        ttk.Checkbutton(
            safe_row,
            text="Safe zones",
            variable=self.safe_zones_var,
            style="Card.TCheckbutton",
            command=self._toggle_safe_zones,
        ).grid(row=0, column=0, sticky="w")

        self.selection_outline = self.canvas.create_rectangle(
            0,
            0,
            1,
            1,
            outline="#38bdf8",
            dash=(5, 3),
            width=2,
            state="hidden",
        )

        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        for sequence in ["<Left>", "<Right>", "<Up>", "<Down>"]:
            self.canvas.bind(sequence, self._on_arrow_key)
        self.canvas.bind("<FocusOut>", lambda _e: self._hide_guides())

        self._rebuild_layers()
        self._building = False
        self._toggle_safe_zones()
        self.select_layer(self.selected_layer, focus_canvas=False)

    # ------------------------------------------------------------- conversions
    def _zoom_text(self, value: float) -> str:
        return f"{value:.2f}×"

    def _to_display(self, value: float) -> float:
        return value * self.display_scale

    def _from_display(self, value: float) -> float:
        return value / self.display_scale

    def _anchor_offset(self, anchor: str, width: float, height: float) -> Tuple[float, float]:
        anchor = anchor.lower()
        if anchor == "topleft":
            return 0, 0
        if anchor == "topright":
            return -width, 0
        if anchor == "bottomleft":
            return 0, -height
        if anchor == "bottomright":
            return -width, -height
        if anchor == "top":
            return -width / 2, 0
        if anchor == "bottom":
            return -width / 2, -height
        if anchor == "left":
            return 0, -height / 2
        if anchor == "right":
            return -width, -height / 2
        return -width / 2, -height / 2

    def _layer_size(self, layer: str) -> Tuple[float, float]:
        info = self.layout_state["layers"].get(layer, {})
        if layer == "video_main":
            scale = float(info.get("scale", 1.12))
            fit_mode = str(info.get("fit", "width")).lower()
            if fit_mode == "height":
                height = DEFAULT_CANVAS_HEIGHT * scale
                width = height * 16 / 9
            else:
                width = DEFAULT_CANVAS_WIDTH * scale
                height = width * 9 / 16
            info["w"] = width
            info["h"] = height
            return width, height
        meta = self.LAYER_META.get(layer, {})
        width = float(info.get("w", meta.get("width", 400)))
        height = float(info.get("h", meta.get("height", 120)))
        info["w"] = width
        info["h"] = height
        return width, height

    def _layer_bbox(self, layer: str) -> Tuple[float, float, float, float]:
        info = self.layout_state["layers"].get(layer, {})
        width, height = self._layer_size(layer)
        anchor = str(info.get("anchor", "center"))
        base_x = float(info.get("x", DEFAULT_CANVAS_WIDTH / 2))
        base_y = float(info.get("y", DEFAULT_CANVAS_HEIGHT / 2))
        offset_x, offset_y = self._anchor_offset(anchor, width, height)
        x1 = self._to_display(base_x + offset_x)
        y1 = self._to_display(base_y + offset_y)
        x2 = self._to_display(base_x + offset_x + width)
        y2 = self._to_display(base_y + offset_y + height)
        return x1, y1, x2, y2

    def _rebuild_layers(self) -> None:
        for items in self.layer_items.values():
            for item in items.values():
                self.canvas.delete(item)
        self.layer_items.clear()
        for layer in self.LAYER_ORDER:
            bbox = self._layer_bbox(layer)
            meta = self.LAYER_META.get(layer, {})
            color = meta.get("color", "#64748b")
            rect = self.canvas.create_rectangle(
                *bbox,
                outline=color,
                width=2,
                fill=f"{color}33",
            )
            label = meta.get("label", layer)
            text = self.canvas.create_text(
                (bbox[0] + bbox[2]) / 2,
                (bbox[1] + bbox[3]) / 2,
                text=label,
                fill="#f8fafc",
                font=("Segoe UI", 10),
            )
            self.canvas.addtag_withtag(f"layer:{layer}", rect)
            self.canvas.addtag_withtag(f"layer:{layer}", text)
            self.layer_items[layer] = {"rect": rect, "text": text}
            if not self.visible_vars[layer].get():
                self.canvas.itemconfigure(rect, state="hidden")
                self.canvas.itemconfigure(text, state="hidden")

    def _update_layer(self, layer: str) -> None:
        bbox = self._layer_bbox(layer)
        items = self.layer_items.get(layer)
        if not items:
            return
        rect = items.get("rect")
        text = items.get("text")
        self.canvas.coords(rect, *bbox)
        self.canvas.coords(
            text,
            (bbox[0] + bbox[2]) / 2,
            (bbox[1] + bbox[3]) / 2,
        )
        if self.visible_vars[layer].get():
            self.canvas.itemconfigure(rect, state="normal")
            self.canvas.itemconfigure(text, state="normal")
        else:
            self.canvas.itemconfigure(rect, state="hidden")
            self.canvas.itemconfigure(text, state="hidden")
        if layer == self.selected_layer:
            self._update_selection_outline()

    def _notify_change(self) -> None:
        if not self._building:
            self._on_change(self.layout_state)

    # -------------------------------------------------------------- UI actions
    def select_layer(self, layer: str, focus_canvas: bool = True) -> None:
        if layer not in self.LAYER_ORDER:
            return
        self.selected_layer = layer
        for name, row in self.layer_rows.items():
            style = "LayerSelected.TFrame" if name == layer else "LayerRow.TFrame"
            row.configure(style=style)
        self._update_selection_outline()
        if focus_canvas:
            self.canvas.focus_set()

    def set_layer_visibility(self, layer: str, visible: bool) -> None:
        self.layout_state["layers"].setdefault(layer, {})["visible"] = visible
        self.visible_vars[layer].set(visible)
        self._update_layer(layer)
        self._notify_change()

    def set_layer_locked(self, layer: str, locked: bool) -> None:
        self.layout_state["layers"].setdefault(layer, {})["locked"] = locked
        self.lock_vars[layer].set(locked)
        self._notify_change()

    def toggle_selected_lock(self) -> None:
        state = not self.lock_vars[self.selected_layer].get()
        self.set_layer_locked(self.selected_layer, state)

    def reset_video_zoom(self) -> None:
        self.zoom_var.set(1.0)
        self.layout_state["layers"]["video_main"]["scale"] = 1.0
        self._update_layer("video_main")
        self.zoom_label_var.set(self._zoom_text(1.0))
        self._notify_change()

    def reload(self, new_state: dict) -> None:
        self.layout_state = new_state
        self.zoom_var.set(float(new_state["layers"]["video_main"].get("scale", 1.12)))
        self.zoom_label_var.set(self._zoom_text(self.zoom_var.get()))
        self.fit_var.set(str(new_state["layers"]["video_main"].get("fit", "width")))
        for layer in self.LAYER_ORDER:
            info = new_state["layers"].get(layer, {})
            self.visible_vars[layer].set(bool(info.get("visible", True)))
            self.lock_vars[layer].set(bool(info.get("locked", False)))
        self.safe_zones_var.set(bool(new_state.get("canvas", {}).get("safe_zones", False)))
        self._rebuild_layers()
        self._toggle_safe_zones()
        self.select_layer(self.selected_layer, focus_canvas=False)

    # --------------------------------------------------------------- callbacks
    def _on_zoom_change(self, *_: object) -> None:
        value = float(self.zoom_var.get())
        self.layout_state["layers"]["video_main"]["scale"] = value
        self.zoom_label_var.set(self._zoom_text(value))
        self._update_layer("video_main")
        self._notify_change()

    def _on_fit_change(self) -> None:
        value = self.fit_var.get()
        self.layout_state["layers"]["video_main"]["fit"] = value
        self._update_layer("video_main")
        self._notify_change()

    def _toggle_safe_zones(self) -> None:
        state = "normal" if self.safe_zones_var.get() else "hidden"
        self.canvas.itemconfigure(self.safe_zone_top, state=state)
        self.canvas.itemconfigure(self.safe_zone_bottom, state=state)
        self.layout_state.setdefault("canvas", {})["safe_zones"] = bool(
            self.safe_zones_var.get()
        )
        self._notify_change()

    def _update_selection_outline(self) -> None:
        bbox = self._layer_bbox(self.selected_layer)
        padding = 4
        self.canvas.coords(
            self.selection_outline,
            bbox[0] - padding,
            bbox[1] - padding,
            bbox[2] + padding,
            bbox[3] + padding,
        )
        if self.visible_vars[self.selected_layer].get():
            self.canvas.itemconfigure(self.selection_outline, state="normal")
        else:
            self.canvas.itemconfigure(self.selection_outline, state="hidden")

    def _on_canvas_click(self, event: tk.Event) -> None:
        self.canvas.focus_set()
        item = self.canvas.find_withtag("current")
        if not item:
            return
        tags = self.canvas.gettags(item[0])
        for tag in tags:
            if tag.startswith("layer:"):
                layer = tag.split(":", 1)[1]
                if self.lock_vars[layer].get():
                    return
                self.select_layer(layer, focus_canvas=False)
                self.dragging_layer = layer
                self._drag_start = (event.x, event.y)
                info = self.layout_state["layers"].get(layer, {})
                self._layer_start = (
                    float(info.get("x", DEFAULT_CANVAS_WIDTH / 2)),
                    float(info.get("y", DEFAULT_CANVAS_HEIGHT / 2)),
                )
                break

    def _hide_guides(self) -> None:
        self.canvas.itemconfigure(self.guide_vertical, state="hidden")
        self.canvas.itemconfigure(self.guide_horizontal, state="hidden")

    def _snap_value(self, value: float, targets: List[float]) -> Tuple[float, bool]:
        for target in targets:
            if abs(value - target) <= self.snap_threshold:
                return target, True
        return value, False

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if not self.dragging_layer or not self._drag_start or not self._layer_start:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        new_x = self._layer_start[0] + self._from_display(dx)
        new_y = self._layer_start[1] + self._from_display(dy)
        targets_x = [0, DEFAULT_CANVAS_WIDTH / 2, DEFAULT_CANVAS_WIDTH]
        targets_y = [0, DEFAULT_CANVAS_HEIGHT / 2, DEFAULT_CANVAS_HEIGHT]
        snapped_x, snap_x = self._snap_value(new_x, targets_x)
        snapped_y, snap_y = self._snap_value(new_y, targets_y)
        self.canvas.itemconfigure(
            self.guide_vertical, state="normal" if snap_x else "hidden"
        )
        self.canvas.itemconfigure(
            self.guide_horizontal, state="normal" if snap_y else "hidden"
        )
        info = self.layout_state["layers"].setdefault(self.dragging_layer, {})
        info["x"] = snapped_x
        info["y"] = snapped_y
        self._update_layer(self.dragging_layer)

    def _on_canvas_release(self, _event: tk.Event) -> None:
        if self.dragging_layer:
            self._notify_change()
        self.dragging_layer = None
        self._drag_start = None
        self._layer_start = None
        self._hide_guides()

    def _on_arrow_key(self, event: tk.Event) -> None:
        if self.lock_vars[self.selected_layer].get():
            return
        step = 10 if event.state & 0x0001 else 1  # Shift pressed
        if event.keysym == "Left":
            dx, dy = -step, 0
        elif event.keysym == "Right":
            dx, dy = step, 0
        elif event.keysym == "Up":
            dx, dy = 0, -step
        else:
            dx, dy = 0, step
        info = self.layout_state["layers"].setdefault(self.selected_layer, {})
        info["x"] = float(info.get("x", 0)) + dx
        info["y"] = float(info.get("y", 0)) + dy
        self._update_layer(self.selected_layer)
        self._notify_change()

class WorkspaceFrame(ttk.Frame):
    """A single workspace tab containing all controls and queue state."""

    def __init__(
        self, master: tk.Misc, workspace_id: int, registry: WorkspaceRegistry
    ) -> None:
        super().__init__(master)
        directories = create_workspace_directories(workspace_id)
        settings = WorkspaceSettings(
            download_directory=directories.downloads,
            processing_directory=directories.processing,
            clips_directory=directories.clips,
            published_directory=directories.published,
            logs_directory=directories.logs,
        )
        self.settings = settings
        self.directories = directories
        self.workspace_id = workspace_id
        self.registry = registry
        self._ui_queue: "queue.Queue[Tuple[VideoJob, JobStage, str]]" = queue.Queue()
        self.controller = registry.get_or_create(
            workspace_id, self.settings, self._on_progress
        )
        self.layout_state = load_workspace_layout(workspace_id)
        self.layout_dirty = False
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

        ttk.Label(left_panel, text="Titolo opzionale", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.title_var = tk.StringVar(value=self.settings.rendering.title)
        title_entry = ttk.Entry(
            left_panel, textvariable=self.title_var, width=32, style="Dark.TEntry"
        )
        title_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        self.title_var.trace_add("write", self._on_title_change)

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

        center_column = ttk.Frame(container, style="Workspace.TFrame")
        center_column.grid(row=1, column=1, sticky="nsew", padx=24)
        center_column.columnconfigure(0, weight=1)
        center_column.rowconfigure(1, weight=1)

        layout_card = ttk.Frame(center_column, style="Card.TFrame", padding=20)
        layout_card.grid(row=0, column=0, sticky="nsew")
        layout_card.columnconfigure(0, weight=1)
        layout_card.rowconfigure(2, weight=1)

        ttk.Label(layout_card, text="Editor layout", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            layout_card,
            text="Organizza video, titolo e testi trascinando i livelli",
            style="SectionHint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        self.layout_status_var = tk.StringVar(value="Layout pronto")
        self.layout_editor = LayerEditor(layout_card, self.layout_state, self._on_layout_change)
        self.layout_editor.grid(row=2, column=0, sticky="nsew")

        buttons_row = ttk.Frame(layout_card, style="Card.TFrame")
        buttons_row.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        buttons_row.columnconfigure(0, weight=1)
        buttons_row.columnconfigure(1, weight=1)
        buttons_row.columnconfigure(2, weight=1)
        ttk.Button(
            buttons_row,
            text="Salva layout (Ctrl+S)",
            style="Accent.TButton",
            command=self._save_layout,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(
            buttons_row,
            text="Ripristina default (Ctrl+0)",
            style="Ghost.TButton",
            command=self._reset_layout,
        ).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(
            buttons_row,
            text="Duplica layout…",
            style="Ghost.TButton",
            command=self._duplicate_layout,
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        ttk.Label(
            layout_card, textvariable=self.layout_status_var, style="SectionHint.TLabel"
        ).grid(row=4, column=0, sticky="w", pady=(12, 0))

        queue_card = ttk.Frame(center_column, style="Card.TFrame", padding=20)
        queue_card.grid(row=1, column=0, sticky="nsew", pady=(24, 0))
        queue_card.columnconfigure(0, weight=1)
        queue_card.columnconfigure(1, weight=0)
        queue_card.rowconfigure(4, weight=1)

        ttk.Label(queue_card, text="Coda clip", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            queue_card,
            text="Incolla uno o più link (uno per riga)",
            style="SectionHint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))

        self.links_text = tk.Text(
            queue_card,
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
            queue_card,
            text="Aggiungi alla coda",
            style="Accent.TButton",
            command=self._add_links,
        )
        add_button.grid(row=3, column=0, sticky="e", pady=(12, 0))

        columns = ("id", "url", "status", "detail", "eta")
        self.tree = ttk.Treeview(
            queue_card,
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
            queue_card, orient="vertical", command=self.tree.yview, style="Vertical.TScrollbar"
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

        self._register_shortcuts()

    # ---------------------------------------------------------------- callbacks

    def _register_shortcuts(self) -> None:
        if getattr(self, "_shortcuts_bound", False):
            return
        toplevel = self.winfo_toplevel()
        toplevel.bind("<Control-s>", self._on_shortcut_save, add="+")
        toplevel.bind("<Control-0>", self._on_shortcut_reset, add="+")
        toplevel.bind("<Control-l>", self._on_shortcut_lock, add="+")
        self._shortcuts_bound = True

    def _is_active_tab(self) -> bool:
        try:
            notebook = self.master
            return str(self) == notebook.select()
        except Exception:
            return True

    def _on_shortcut_save(self, event: tk.Event) -> str:
        if not self._is_active_tab():
            return ""
        self._save_layout()
        return "break"

    def _on_shortcut_reset(self, event: tk.Event) -> str:
        if not self._is_active_tab():
            return ""
        self._reset_layout()
        return "break"

    def _on_shortcut_lock(self, event: tk.Event) -> str:
        if not self._is_active_tab():
            return ""
        self.layout_editor.toggle_selected_lock()
        self._on_layout_change(self.layout_state)
        return "break"

    def _on_layout_change(self, _state: dict) -> None:
        self.layout_dirty = True
        if hasattr(self, "layout_status_var"):
            self.layout_status_var.set("Modifiche non salvate")

    def _save_layout(self) -> None:
        save_workspace_layout(self.workspace_id, self.layout_state)
        self.layout_dirty = False
        if hasattr(self, "layout_status_var"):
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.layout_status_var.set(f"Layout salvato alle {timestamp}")

    def _reset_layout(self) -> None:
        if not messagebox.askyesno(
            "ClipperStudio", "Ripristinare il layout predefinito per questa scheda?"
        ):
            return
        self.layout_state = reset_workspace_layout(self.workspace_id)
        self.layout_editor.reload(self.layout_state)
        self.layout_dirty = False
        if hasattr(self, "layout_status_var"):
            self.layout_status_var.set("Layout ripristinato")

    def _duplicate_layout(self) -> None:
        target = simpledialog.askinteger(
            "Duplica layout",
            "Copia il layout corrente su workspace n°:",
            parent=self,
            minvalue=1,
            initialvalue=self.workspace_id + 1,
        )
        if target is None or target == self.workspace_id:
            return
        create_workspace_directories(target)
        duplicate_workspace_layout(self.workspace_id, target)
        messagebox.showinfo(
            "ClipperStudio",
            f"Layout duplicato su workspace {target}",
        )
        if hasattr(self, "layout_status_var"):
            self.layout_status_var.set(f"Layout copiato su workspace {target}")

    def _auto_save_layout(self) -> None:
        if self.layout_dirty:
            self._save_layout()


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
        self._auto_save_layout()
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
        log_file = job.logs_directory / "events.log"
        try:
            with open(log_file, "a", encoding="utf-8") as handle:
                handle.write(f"{stage.label()} | {message}\n")
        except OSError:
            pass


class ClipperStudioApp(tk.Tk):
    """Main Tkinter application."""

    def __init__(self) -> None:
        super().__init__()
        self.title("ClipperStudio")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        self._configure_styles()
        self.registry = WorkspaceRegistry()
        self.workspace_tabs: Dict[str, int] = {}
        self.workspace_frames: Dict[int, WorkspaceFrame] = {}
        self.current_workspace_id: Optional[int] = None
        self._context_tab: Optional[str] = None
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
        style.configure("LayerRow.TFrame", background=card_bg)
        style.configure("LayerSelected.TFrame", background="#1f2937")
        style.configure("Layer.TCheckbutton", background=card_bg, foreground="#e2e8f0")
        style.map(
            "Layer.TCheckbutton",
            background=[("active", card_bg), ("selected", "#2563eb")],
            foreground=[("disabled", "#475569")],
        )
        style.configure("Layer.TRadiobutton", background=card_bg, foreground="#e2e8f0")
        style.map(
            "Layer.TRadiobutton",
            background=[("active", card_bg), ("selected", "#2563eb")],
        )

    def _build_ui(self) -> None:
        container = ttk.Frame(self, style="Workspace.TFrame")
        container.pack(fill="both", expand=True)
        tabs_wrapper = ttk.Frame(container, style="Workspace.TFrame")
        tabs_wrapper.pack(fill="both", expand=True)
        tabs_wrapper.columnconfigure(0, weight=1)
        tabs_wrapper.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(tabs_wrapper)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.notebook.bind("<Button-3>", self._on_tab_right_click)

        add_button = ttk.Button(
            tabs_wrapper,
            text="+",
            style="Accent.TButton",
            command=self._add_workspace,
            width=3,
        )
        add_button.grid(row=0, column=1, padx=(8, 0), pady=(4, 0), sticky="ne")

        self.tab_menu = tk.Menu(self, tearoff=0)
        self.tab_menu.add_command(label="Rinomina scheda", command=self._rename_selected_tab)
        self.tab_menu.add_command(
            label="Duplica layout su nuova scheda", command=self._duplicate_current_tab
        )
        self.tab_menu.add_separator()
        self.tab_menu.add_command(label="Chiudi scheda", command=self._close_selected_tab)

        initial_ids = list_workspace_ids()
        if not initial_ids:
            initial_ids = [1]
        for workspace_id in initial_ids:
            self._create_workspace_tab(workspace_id)

        if self.notebook.tabs():
            self.notebook.select(self.notebook.tabs()[0])

    def _tab_id_from_event(self, event: tk.Event) -> Optional[str]:
        try:
            index = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return None
        tabs = self.notebook.tabs()
        if 0 <= index < len(tabs):
            return tabs[index]
        return None

    def _create_workspace_tab(self, workspace_id: int, label: Optional[str] = None) -> None:
        frame = WorkspaceFrame(self.notebook, workspace_id, self.registry)
        text = label or f"Scheda {workspace_id}"
        self.notebook.add(frame, text=text)
        tab_id = self.notebook.tabs()[-1]
        self.workspace_tabs[tab_id] = workspace_id
        self.workspace_frames[workspace_id] = frame

    def _add_workspace(self) -> None:
        new_id = next_workspace_id(set(self.workspace_frames.keys()))
        self._create_workspace_tab(new_id)
        self.notebook.select(self.notebook.tabs()[-1])

    def _on_tab_right_click(self, event: tk.Event) -> None:
        tab_id = self._tab_id_from_event(event)
        if not tab_id:
            return
        self._context_tab = tab_id
        try:
            self.tab_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tab_menu.grab_release()

    def _rename_selected_tab(self) -> None:
        tab_id = self._context_tab or self.notebook.select()
        if not tab_id:
            return
        current_text = self.notebook.tab(tab_id, "text")
        new_name = simpledialog.askstring(
            "Rinomina scheda", "Nuovo nome", parent=self, initialvalue=current_text
        )
        if new_name:
            self.notebook.tab(tab_id, text=new_name.strip())
        self._context_tab = None

    def _duplicate_current_tab(self) -> None:
        tab_id = self._context_tab or self.notebook.select()
        if not tab_id:
            return
        workspace_id = self.workspace_tabs.get(tab_id)
        if workspace_id is None:
            return
        frame = self.workspace_frames.get(workspace_id)
        if frame:
            frame._save_layout()
        existing = set(self.workspace_frames.keys())
        new_id = next_workspace_id(existing)
        duplicate_workspace_layout(workspace_id, new_id)
        self._create_workspace_tab(new_id)
        self.notebook.select(self.notebook.tabs()[-1])
        self._context_tab = None

    def _close_selected_tab(self) -> None:
        tab_id = self._context_tab or self.notebook.select()
        if not tab_id:
            return
        workspace_id = self.workspace_tabs.pop(tab_id, None)
        if workspace_id is not None:
            frame = self.workspace_frames.pop(workspace_id, None)
            if frame is not None:
                self.registry.remove(workspace_id)
                frame.destroy()
        try:
            self.notebook.forget(tab_id)
        except tk.TclError:
            pass
        if not self.notebook.tabs():
            new_id = next_workspace_id(set())
            self._create_workspace_tab(new_id)
        self._context_tab = None
        if self.notebook.tabs():
            self.notebook.select(self.notebook.tabs()[-1])

    def _on_tab_changed(self, _event: tk.Event) -> None:
        self._context_tab = None
        tab_id = self.notebook.select()
        workspace_id = self.workspace_tabs.get(tab_id)
        if workspace_id is not None:
            self.current_workspace_id = workspace_id

    def _on_close(self) -> None:
        self.registry.stop_all()
        self.destroy()


def main() -> None:
    app = ClipperStudioApp()
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover - GUI entry point
    main()
