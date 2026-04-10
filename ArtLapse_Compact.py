import customtkinter as ctk
import ctypes
import os
import re
import shutil
from tkinter import filedialog
from PIL import Image

import config
import capture
import export
from constants import (
    ORANGE_THEME, ORANGE_DIM, BG_COLOR, CARD_COLOR, APP_W, APP_H
)

ctk.set_appearance_mode("dark")


class ArtLapseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.overrideredirect(True)
        self.geometry(f"{APP_W}x{APP_H}")
        self.configure(fg_color=BG_COLOR)
        self.update_idletasks()
        self.after(20, self._setup_taskbar_presence)
        self.after(20, self.apply_round_region)

        self.is_recording  = False
        self.base_path     = config.load_config()
        self.after_id      = None
        self.count         = 1
        self.final_path    = ""
        self._offsetx      = 0
        self._offsety      = 0
        self._thumb_photo          = None
        self._custom_duration_secs = None

        self._build_ui()

    # ------------------------------------------------------------------ #
    #  ROUNDED REGION                                                      #
    # ------------------------------------------------------------------ #
    def apply_round_region(self, w=APP_W, h=APP_H):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        rgn  = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w, h, 22, 22)
        ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)

    # ------------------------------------------------------------------ #
    #  UI CONSTRUCTION                                                     #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        # ── HEADER ──────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent", height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="ART-LAPSE",
            font=("Arial Black", 21, "bold"),
            text_color=ORANGE_THEME
        ).place(relx=0.5, rely=0.55, anchor="center")

        btn_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_frame.place(relx=1.0, rely=0.5, anchor="e", x=-8)

        ctk.CTkButton(btn_frame, text="—", width=34, height=34,
                      fg_color="transparent", hover_color="#333333",
                      font=("Arial", 15, "bold"),
                      corner_radius=8, command=self._minimize).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="✕", width=34, height=34,
                      fg_color="transparent", hover_color="#c42b1c",
                      font=("Arial", 15, "bold"),
                      corner_radius=8, command=self.destroy).pack(side="left", padx=2)

        for widget in (hdr,):
            widget.bind("<Button-1>",  self._click_window)
            widget.bind("<B1-Motion>", self._drag_window)

        # ── BODY ────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        # Window picker
        self._section_label(body, "CAPTURE WINDOW")
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", pady=(2, 0))
        self.window_dropdown = ctk.CTkComboBox(row1, values=capture.get_window_titles(), width=290)
        self.window_dropdown.pack(side="left")
        ctk.CTkButton(row1, text="⟳", width=44, height=34,
                      fg_color=CARD_COLOR, hover_color="#333333",
                      font=("Arial", 17, "bold"),
                      command=self.refresh_windows).pack(side="left", padx=(6, 0))

        # Folder picker
        self._section_label(body, "OUTPUT FOLDER")
        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=(2, 0))
        self.folder_label = ctk.CTkLabel(row2, text=config.get_short_path(self.base_path),
                                         font=("Arial", 10), text_color="gray",
                                         anchor="w", width=254)
        self.folder_label.pack(side="left")
        ctk.CTkButton(row2, text="📁", width=44, height=34,
                      fg_color=CARD_COLOR, hover_color="#333333",
                      font=("Arial", 16),
                      command=self.choose_folder).pack(side="left", padx=(6, 0))
        ctk.CTkButton(row2, text="↗", width=38, height=34,
                      fg_color=CARD_COLOR, hover_color="#333333",
                      font=("Arial", 17, "bold"),
                      command=self.open_output_folder).pack(side="left", padx=(4, 0))

        # Project name
        self._section_label(body, "PROJECT NAME  ·  type new or pick existing")
        proj_row = ctk.CTkFrame(body, fg_color="transparent")
        proj_row.pack(fill="x", pady=(2, 0))
        self.project_combo = ctk.CTkComboBox(proj_row, values=config.get_existing_projects(self.base_path), width=310)
        self.project_combo.pack(side="left")
        self.delete_btn = ctk.CTkButton(
            proj_row, text="🗑", width=44, height=34,
            fg_color="#3a1a1a", hover_color="#5a2020",
            font=("Arial", 16), text_color="#ff5555",
            command=self.delete_project
        )
        self.delete_btn.pack(side="left", padx=(6, 0))

        # Interval slider
        self._section_label(body, "INTERVAL")
        self.label_interval = ctk.CTkLabel(body, text="10 s",
                                           font=("Arial Black", 13),
                                           text_color=ORANGE_THEME)
        self.label_interval.pack(anchor="e")
        self.slider_interval = ctk.CTkSlider(
            body, from_=1, to=60,
            button_color=ORANGE_THEME,
            progress_color=ORANGE_THEME,
            command=self._update_interval_label
        )
        self.slider_interval.set(10)
        self.slider_interval.pack(fill="x", pady=(0, 6))

        # Thumbnail + size estimate
        info_row = ctk.CTkFrame(body, fg_color=CARD_COLOR, corner_radius=10)
        info_row.pack(fill="x", pady=(2, 4))

        self.thumb_label = ctk.CTkLabel(info_row, text="no preview",
                                        width=80, height=46,
                                        font=("Arial", 9), text_color="#555555",
                                        fg_color="#1a1d1f", corner_radius=8)
        self.thumb_label.pack(side="left", padx=8, pady=6)

        stats = ctk.CTkFrame(info_row, fg_color="transparent")
        stats.pack(side="left", padx=6, pady=6, fill="both", expand=True)
        self.frames_label = ctk.CTkLabel(stats, text="Frames: 0",
                                         font=("Arial", 11), anchor="w")
        self.frames_label.pack(anchor="w")
        self.size_label   = ctk.CTkLabel(stats, text="Est. size: —",
                                         font=("Arial", 11), anchor="w",
                                         text_color="gray")
        self.size_label.pack(anchor="w")
        self.warn_label   = ctk.CTkLabel(stats, text="",
                                         font=("Arial", 10), anchor="w",
                                         text_color="orange")
        self.warn_label.pack(anchor="w")

        # Status
        self.status_label = ctk.CTkLabel(body, text="Ready",
                                         font=("Arial", 12, "bold"),
                                         text_color="gray")
        self.status_label.pack(pady=(2, 4))

        # Start / stop buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 4))

        self.start_btn = ctk.CTkButton(
            btn_row, text="START", fg_color=ORANGE_THEME,
            hover_color=ORANGE_DIM, font=("Arial Black", 16, "bold"),
            height=52, command=self.toggle_capture
        )
        self.start_btn.pack(side="left", fill="x", expand=True)

        self.stop_btn = ctk.CTkButton(
            btn_row, text="⏹", fg_color="#3a1a1a", hover_color="#5a2020",
            font=("Arial Black", 18, "bold"), text_color="#ff5555",
            height=52, width=52, command=self.stop_and_reset
        )
        # Hidden until recording is paused

        # ── EXPORT SECTION ──────────────────────────────────────────────
        export_header = ctk.CTkFrame(body, fg_color="transparent")
        export_header.pack(fill="x", pady=(0, 0))

        self.ffmpeg_btn = ctk.CTkButton(
            export_header, text="▶  Export Timelapse MP4",
            fg_color=CARD_COLOR, hover_color="#333333",
            font=("Arial", 12, "bold"),
            height=38, command=self.compile_video
        )
        self.ffmpeg_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._export_collapsed = False
        self.collapse_btn = ctk.CTkButton(
            export_header, text="▲", width=38, height=38,
            fg_color=CARD_COLOR, hover_color="#333333",
            font=("Arial", 12, "bold"), text_color="gray",
            command=self._toggle_export_panel
        )
        self.collapse_btn.pack(side="left")

        # Collapsible export options card
        self.export_card = ctk.CTkFrame(body, fg_color=CARD_COLOR, corner_radius=10)
        self.export_card.pack(fill="x", pady=(4, 0))

        # Auto-export toggle
        top_row = ctk.CTkFrame(self.export_card, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(top_row, text="Auto-export on Stop",
                     font=("Arial", 11), anchor="w").pack(side="left")
        self.auto_compile_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(top_row, text="", variable=self.auto_compile_var,
                      width=40, button_color=ORANGE_THEME,
                      progress_color=ORANGE_DIM).pack(side="right")

        # Duration slider (snapping)
        self._dur_snaps  = [15, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600, None]
        self._dur_labels = ["15s", "30s", "45s", "1m", "1m30s",
                            "2m", "3m", "4m", "5m", "7m", "10m", "Realtime"]

        dur_row = ctk.CTkFrame(self.export_card, fg_color="transparent")
        dur_row.pack(fill="x", padx=10, pady=(6, 0))
        ctk.CTkLabel(dur_row, text="Duration",
                     font=("Arial", 11), anchor="w").pack(side="left")

        self.duration_val_label = ctk.CTkLabel(
            dur_row, text="30s",
            font=("Arial", 11, "underline"),
            text_color=ORANGE_THEME, cursor="hand2"
        )
        self.duration_val_label.pack(side="right")
        self.duration_val_label.bind("<Button-1>", self._open_duration_entry)

        self.duration_slider = ctk.CTkSlider(
            self.export_card,
            from_=0, to=len(self._dur_snaps) - 1,
            number_of_steps=len(self._dur_snaps) - 1,
            button_color=ORANGE_THEME,
            progress_color=ORANGE_THEME,
            command=self._on_duration_slide
        )
        self.duration_slider.set(1)
        self.duration_slider.pack(fill="x", padx=10, pady=(2, 0))

        dur_hints = ctk.CTkFrame(self.export_card, fg_color="transparent")
        dur_hints.pack(fill="x", padx=10, pady=(0, 2))
        ctk.CTkLabel(dur_hints, text="15 sec", font=("Arial", 9),
                     text_color="#444444").pack(side="left")
        ctk.CTkLabel(dur_hints, text="Realtime", font=("Arial", 9),
                     text_color="#444444").pack(side="right")

        self._dur_entry_frame = ctk.CTkFrame(self.export_card, fg_color="transparent")
        self.duration_entry = ctk.CTkEntry(
            self._dur_entry_frame, height=28,
            placeholder_text='minutes — e.g. "1.5" or "2m30s"',
            font=("Arial", 11)
        )
        self.duration_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.duration_entry.bind("<Return>", lambda e: self._apply_duration_entry())
        self.duration_entry.bind("<Escape>", lambda e: self._dur_entry_frame.pack_forget())
        ctk.CTkButton(
            self._dur_entry_frame, text="✓", width=32, height=28,
            fg_color=ORANGE_THEME, hover_color=ORANGE_DIM,
            font=("Arial", 12, "bold"),
            command=self._apply_duration_entry
        ).pack(side="left")

        # Quality slider
        q_row = ctk.CTkFrame(self.export_card, fg_color="transparent")
        q_row.pack(fill="x", padx=10, pady=(4, 0))
        ctk.CTkLabel(q_row, text="Quality",
                     font=("Arial", 11), anchor="w").pack(side="left")
        self.quality_val_label = ctk.CTkLabel(q_row, text="Balanced",
                                              font=("Arial", 10), text_color="gray")
        self.quality_val_label.pack(side="right")

        self.quality_slider = ctk.CTkSlider(
            self.export_card, from_=0, to=4,
            number_of_steps=4,
            button_color=ORANGE_THEME,
            progress_color=ORANGE_THEME,
            command=self._update_quality_label
        )
        self.quality_slider.set(2)
        self.quality_slider.pack(fill="x", padx=10, pady=(2, 0))

        q_hints = ctk.CTkFrame(self.export_card, fg_color="transparent")
        q_hints.pack(fill="x", padx=10, pady=(2, 10))
        ctk.CTkLabel(q_hints, text="Smallest", font=("Arial", 9),
                     text_color="#444444").pack(side="left")
        ctk.CTkLabel(q_hints, text="Highest", font=("Arial", 9),
                     text_color="#444444").pack(side="right")

    # ------------------------------------------------------------------ #
    #  UI HELPERS                                                          #
    # ------------------------------------------------------------------ #
    def _section_label(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=("Arial", 9, "bold"),
                     text_color="#555555", anchor="w").pack(anchor="w", pady=(6, 0))

    def _click_window(self, event):
        self._offsetx = event.x_root - self.winfo_x()
        self._offsety = event.y_root - self.winfo_y()

    def _drag_window(self, event):
        x = event.x_root - self._offsetx
        y = event.y_root - self._offsety
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------ #
    #  BORDERLESS WINDOW — WIN32                                           #
    # ------------------------------------------------------------------ #
    def _setup_taskbar_presence(self):
        GWL_EXSTYLE      = -20
        WS_EX_APPWINDOW  = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style &= ~WS_EX_TOOLWINDOW
        ex_style |=  WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

    def _minimize(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        ctypes.windll.user32.ShowWindow(hwnd, 6)

    # ------------------------------------------------------------------ #
    #  EXPORT PANEL CONTROLS                                               #
    # ------------------------------------------------------------------ #
    def _update_interval_label(self, val):
        self.label_interval.configure(text=f"{int(float(val))} s")
        self._refresh_size_estimate()

    def _toggle_export_panel(self):
        if self._export_collapsed:
            self.export_card.pack(fill="x", pady=(4, 0))
            self.collapse_btn.configure(text="▲")
            self._export_collapsed = False
            self.after(10, lambda: self.geometry(f"{APP_W}x{APP_H}"))
            self.after(20, lambda: self.apply_round_region(APP_W, APP_H))
        else:
            self.export_card.pack_forget()
            self.collapse_btn.configure(text="▼")
            self._export_collapsed = True
            self.update_idletasks()
            new_h = self.winfo_reqheight()
            self.geometry(f"{APP_W}x{new_h}")
            self.after(20, lambda: self.apply_round_region(APP_W, new_h))

    def _on_duration_slide(self, val):
        idx = int(round(float(val)))
        self.duration_slider.set(idx)
        self._custom_duration_secs = None
        self.duration_val_label.configure(text=self._dur_labels[idx])
        if self._dur_snaps[idx] is None:
            self._dur_entry_frame.pack_forget()

    def _get_duration_seconds(self):
        if getattr(self, "_custom_duration_secs", None):
            return self._custom_duration_secs
        idx = int(round(float(self.duration_slider.get())))
        return self._dur_snaps[idx]

    def _open_duration_entry(self, _event=None):
        idx = int(round(float(self.duration_slider.get())))
        if self._dur_snaps[idx] is None:
            return
        if self._dur_entry_frame.winfo_ismapped():
            self._dur_entry_frame.pack_forget()
        else:
            self._dur_entry_frame.pack(fill="x", padx=10, pady=(4, 0),
                                       after=self.duration_slider)
            self.after(50, self.duration_entry.focus)

    def _apply_duration_entry(self):
        raw = self.duration_entry.get().strip().lower()
        try:
            m = re.fullmatch(r'(\d+)m(\d+)s?', raw)
            if m:
                secs = int(m.group(1)) * 60 + int(m.group(2))
            elif raw.endswith('s'):
                secs = int(float(raw[:-1]))
            elif raw.endswith('m'):
                secs = int(float(raw[:-1]) * 60)
            else:
                secs = int(float(raw) * 60)

            secs   = max(5, min(secs, 3600))
            snaps  = [(i, s) for i, s in enumerate(self._dur_snaps) if s is not None]
            closest = min(snaps, key=lambda x: abs(x[1] - secs))
            self.duration_slider.set(closest[0])
            if abs(closest[1] - secs) <= 5:
                self._custom_duration_secs = None
                self.duration_val_label.configure(text=self._dur_labels[closest[0]])
            else:
                self._custom_duration_secs = secs
                mins, s = divmod(secs, 60)
                lbl = f"{mins}m{s}s" if mins and s else (f"{mins}m" if mins else f"{s}s")
                self.duration_val_label.configure(text=lbl + " ✎")

            self.duration_entry.delete(0, "end")
            self._dur_entry_frame.pack_forget()
        except (ValueError, AttributeError):
            self.duration_entry.configure(border_color="red")
            self.after(800, lambda: self.duration_entry.configure(border_color="gray"))

    _QUALITY_LABELS = ["Smallest", "Small", "Balanced", "High", "Highest"]
    _QUALITY_CRF    = [32, 28, 23, 20, 18]
    _QUALITY_PRESET = ["veryfast", "fast", "medium", "slow", "veryslow"]

    def _update_quality_label(self, val):
        idx = int(round(float(val)))
        self.quality_val_label.configure(text=self._QUALITY_LABELS[idx])

    def _get_crf_and_preset(self):
        idx = int(round(float(self.quality_slider.get())))
        return self._QUALITY_CRF[idx], self._QUALITY_PRESET[idx]

    # ------------------------------------------------------------------ #
    #  FOLDER / PROJECT HELPERS                                            #
    # ------------------------------------------------------------------ #
    def refresh_windows(self):
        self.window_dropdown.configure(values=capture.get_window_titles())

    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.base_path = path
            config.save_config(self.base_path)
            self.folder_label.configure(text=config.get_short_path(self.base_path))
            self.project_combo.configure(values=config.get_existing_projects(self.base_path))

    def open_output_folder(self):
        target = self.final_path if self.final_path and os.path.exists(self.final_path) else self.base_path
        if target and os.path.exists(target):
            os.startfile(target)
        else:
            self.status_label.configure(text="No folder to open", text_color="orange")

    def delete_project(self):
        name = self.project_combo.get().strip()
        if not name or name == "New Project" or not self.base_path:
            self.status_label.configure(text="No project selected to delete", text_color="orange")
            return

        target = os.path.join(self.base_path, name)
        if not os.path.exists(target):
            self.status_label.configure(text="Folder not found", text_color="orange")
            return

        if target == self.final_path and self.is_recording:
            self.status_label.configure(text="Can't delete — currently recording", text_color="red")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.overrideredirect(True)
        dialog.configure(fg_color="#2a1a1a")
        dialog.resizable(False, False)

        dw, dh = 300, 160
        cx = self.winfo_x() + (APP_W - dw) // 2
        cy = self.winfo_y() + (APP_H - dh) // 2
        dialog.geometry(f"{dw}x{dh}+{cx}+{cy}")
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Delete project?",
                     font=("Arial Black", 13, "bold"),
                     text_color="#ff5555").pack(pady=(18, 4))
        ctk.CTkLabel(dialog,
                     text=f'"{name}" and all its files\nwill be permanently deleted.',
                     font=("Arial", 11), text_color="gray").pack(pady=(0, 14))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20)

        def confirm():
            dialog.destroy()
            try:
                shutil.rmtree(target)
                if target == self.final_path:
                    self.stop_and_reset()
                else:
                    self.project_combo.set("")
                    self.project_combo.configure(values=config.get_existing_projects(self.base_path))
                self.status_label.configure(text=f'"{name}" deleted', text_color="gray")
            except Exception as e:
                self.status_label.configure(text=f"Delete failed: {e}", text_color="red")

        ctk.CTkButton(btn_row, text="Cancel", fg_color=CARD_COLOR, hover_color="#333333",
                      command=dialog.destroy, width=110).pack(side="left")
        ctk.CTkButton(btn_row, text="🗑  Delete", fg_color="#5a2020", hover_color="#7a2a2a",
                      text_color="#ff5555", font=("Arial", 12, "bold"),
                      command=confirm, width=130).pack(side="right")

    # ------------------------------------------------------------------ #
    #  SIZE ESTIMATE + THUMBNAIL                                           #
    # ------------------------------------------------------------------ #
    def _resolve_project_path(self):
        name = self.project_combo.get().strip()
        if not self.base_path or not name or name == "New Project":
            return None
        return os.path.join(self.base_path, name)

    def _refresh_size_estimate(self):
        if not self.final_path or not os.path.exists(self.final_path):
            self.size_label.configure(text="Est. size: —")
            return
        pngs = [f for f in os.listdir(self.final_path) if f.endswith(".png")]
        if not pngs:
            self.size_label.configure(text="Est. size: —")
            return
        avg_bytes = sum(
            os.path.getsize(os.path.join(self.final_path, f)) for f in pngs
        ) / len(pngs)
        total_mb = avg_bytes * len(pngs) / 1_048_576
        self.size_label.configure(text=f"Est. size: {total_mb:.1f} MB  ({len(pngs)} frames)")

    def _update_thumbnail(self, img_path: str):
        try:
            img = Image.open(img_path)
            self._thumb_photo = ctk.CTkImage(light_image=img, size=(80, 46))
            self.thumb_label.configure(image=self._thumb_photo, text="")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  CAPTURE                                                             #
    # ------------------------------------------------------------------ #
    def toggle_capture(self):
        if not self.is_recording:
            path = self._resolve_project_path()
            if not path:
                self.status_label.configure(text="Set a folder & project name first", text_color="red")
                return

            if path != self.final_path:
                self.final_path = path
                os.makedirs(self.final_path, exist_ok=True)
                existing = [f for f in os.listdir(self.final_path) if f.endswith(".png")]
                self.count = len(existing) + 1
                self.frames_label.configure(text=f"Frames: {len(existing)}")

            self.is_recording = True
            self.start_btn.configure(text="⏸  PAUSE", fg_color="#333333", hover_color="#444444")
            self.stop_btn.pack_forget()
            self.status_label.configure(text=f"Recording — frame {self.count}", text_color=ORANGE_THEME)
            self.warn_label.configure(text="")
            self.capture_loop()
        else:
            self.is_recording = False
            if self.after_id:
                self.after_cancel(self.after_id)
                self.after_id = None
            self.start_btn.configure(text="▶  RESUME", fg_color=ORANGE_THEME, hover_color=ORANGE_DIM)
            self.stop_btn.pack(side="left", padx=(6, 0))
            self.status_label.configure(text="Paused", text_color="orange")

    def stop_and_reset(self):
        self.is_recording = False
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

        export_path = self.final_path
        if self.auto_compile_var.get() and export_path and os.path.exists(export_path):
            self.compile_video(path_override=export_path)

        self.final_path = ""
        self.count      = 1
        self.start_btn.configure(text="START", fg_color=ORANGE_THEME, hover_color=ORANGE_DIM)
        self.stop_btn.pack_forget()
        self.status_label.configure(
            text="Exporting…" if self.auto_compile_var.get() and export_path else "Ready",
            text_color="gray"
        )
        self.warn_label.configure(text="")
        self.frames_label.configure(text="Frames: 0")
        self.size_label.configure(text="Est. size: —")
        self.thumb_label.configure(image="", text="no preview")
        self._thumb_photo = None
        self.project_combo.configure(values=config.get_existing_projects(self.base_path))
        self.project_combo.set("")

    def capture_loop(self):
        if not self.is_recording:
            return

        save_path = os.path.join(self.final_path, f"shot_{self.count:04d}.png")
        captured, warning = capture.capture_frame(self.window_dropdown.get(), save_path)

        self.warn_label.configure(text=warning)
        if captured:
            self.status_label.configure(text=f"Recording — frame {self.count}")
            self.frames_label.configure(text=f"Frames: {self.count}")
            self.count += 1
            self._update_thumbnail(save_path)
            self._refresh_size_estimate()

        interval_ms = int(float(self.slider_interval.get()) * 1000)
        self.after_id = self.after(interval_ms, self.capture_loop)

    # ------------------------------------------------------------------ #
    #  EXPORT                                                              #
    # ------------------------------------------------------------------ #
    def compile_video(self, path_override=None):
        path = path_override or self._resolve_project_path() or self.final_path
        if not path or not os.path.exists(path):
            self.status_label.configure(text="Select a project to export", text_color="orange")
            return

        pngs = sorted(
            [f for f in os.listdir(path) if f.lower().endswith(".png")],
            key=lambda x: x.lower()
        )
        if not pngs:
            self.status_label.configure(text="No frames found in folder", text_color="red")
            return

        if not shutil.which("ffmpeg"):
            self.status_label.configure(text="ffmpeg not found in PATH", text_color="red")
            return

        crf, preset  = self._get_crf_and_preset()
        duration_sec = self._get_duration_seconds()
        n            = len(pngs)

        if duration_sec is None:
            fps      = 24.0
            dur_str  = "Realtime (24fps)"
        else:
            fps     = round(max(n / duration_sec, 0.1), 4)
            mins, s = divmod(duration_sec, 60)
            dur_str = f"{mins}m{s}s" if mins else f"{duration_sec}s"

        self.status_label.configure(text=f"Exporting {n} frames at {fps:.2f} fps…", text_color="gray")
        self.ffmpeg_btn.configure(state="disabled")

        def on_done(size_mb, out_path):
            msg = f"Exported ✓  {n} frames · {dur_str} · {size_mb:.1f} MB"
            self.after(0, lambda: self.status_label.configure(text=msg, text_color=ORANGE_THEME))
            self.after(0, lambda: os.startfile(out_path))

        def on_error(msg):
            self.after(0, lambda: self.status_label.configure(text=msg, text_color="red"))

        def on_finally():
            self.after(0, lambda: self.ffmpeg_btn.configure(state="normal"))

        export.run_export(path, pngs, fps, crf, preset, on_done, on_error, on_finally)


if __name__ == "__main__":
    app = ArtLapseApp()
    app.mainloop()
