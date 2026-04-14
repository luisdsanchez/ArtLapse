import customtkinter as ctk
import ctypes
import math
import os
import shutil
import sys
import threading
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageDraw, ImageTk
import pystray

import config
import capture
import export
import lang
import constants
from constants import T, set_theme as _set_theme, APP_W, APP_H


def _make_app_icon(size=64) -> Image.Image:
    """Load the app icon from the bundled PNG asset."""
    _base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    path  = os.path.join(_base, "assets", "ArtLapse_icon.png")
    return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)

# Apply saved theme before any windows are created
_set_theme(config.load_theme())


def _apply_dwm_round(hwnd, large: bool = True):
    """Use DWM compositor (Windows 11+) for anti-aliased rounded corners.
    Falls back silently on older Windows."""
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCRP_ROUND       = ctypes.c_int(2)   # large radius (~8px)
        DWMWCRP_ROUNDSMALL  = ctypes.c_int(3)   # small radius (~4px)
        value = DWMWCRP_ROUND if large else DWMWCRP_ROUNDSMALL
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(value), ctypes.sizeof(value),
        )
        # Clear any hard clip-region so DWM owns the shape entirely
        ctypes.windll.user32.SetWindowRgn(hwnd, None, True)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  WINDOW / SCREEN PICKER POPUP
# ══════════════════════════════════════════════════════════════════════════════

class WindowPickerPopup(ctk.CTkToplevel):
    _POPUP_W = 520
    _POPUP_H = 460
    _CARD_W  = 152    # (520 - scrollbar~16 - 14*2 - 8*2) // 3
    _THUMB_W = 148    # CARD_W - 4
    _THUMB_H = 84     # ≈ 16:9
    _CARD_H  = 116    # THUMB_H + bottom + padding
    _COLS    = 3
    _PAD     = 14
    _GAP     = 8

    def __init__(self, parent: ctk.CTk, current_target: "dict | None", on_select):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(fg_color=T["popup_bg"])
        self.wm_attributes("-topmost", True)

        self._on_select  = on_select
        self._cur_target = current_target
        self._card_data  = []       # list of (card_frame, info_dict)
        self._drag_ox    = 0
        self._drag_oy    = 0

        # Center on parent
        parent.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self._POPUP_W) // 2
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self._POPUP_H) // 2)
        self.geometry(f"{self._POPUP_W}x{self._POPUP_H}+{px}+{py}")

        self._build_ui()
        self.after(20, self._apply_round)
        self.grab_set()

        threading.Thread(target=self._load_data, daemon=True).start()

    def _apply_round(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        _apply_dwm_round(hwnd, large=False)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Title bar
        tbar = ctk.CTkFrame(self, fg_color=T["popup_bg"], height=42, corner_radius=0)
        tbar.pack(fill="x")
        tbar.pack_propagate(False)
        tbar.bind("<Button-1>",  self._drag_start)
        tbar.bind("<B1-Motion>", self._drag_move)

        _lbl = ctk.CTkLabel(
            tbar, text=lang.t("picker_title"),
            font=("Arial", 10, "bold"), text_color=T["subtext"],
        )
        _lbl.place(relx=0.5, rely=0.5, anchor="center")
        _lbl.bind("<Button-1>",  self._drag_start)
        _lbl.bind("<B1-Motion>", self._drag_move)

        btn_area = ctk.CTkFrame(tbar, fg_color="transparent")
        btn_area.place(relx=1.0, rely=0.5, anchor="e", x=-6)

        ctk.CTkButton(
            btn_area, text="↺", width=30, height=30,
            fg_color="transparent", hover_color=T["hover"],
            font=("Arial", 15, "bold"), text_color="#888888",
            command=self._reload,
        ).pack(side="left", padx=(0, 2))

        ctk.CTkButton(
            btn_area, text="✕", width=30, height=30,
            fg_color="transparent", hover_color="#c42b1c",
            font=("Arial", 13, "bold"),
            command=self.destroy,
        ).pack(side="left")

        # Scrollable content
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=T["hover"],
            scrollbar_button_hover_color=T["muted"],
        )
        self._scroll.pack(fill="both", expand=True)

        self._status_lbl = ctk.CTkLabel(
            self._scroll, text=lang.t("picker_loading"),
            font=("Arial", 11), text_color=T["muted"],
        )
        self._status_lbl.pack(pady=30)

    def _drag_start(self, event):
        self._drag_ox = event.x_root - self.winfo_x()
        self._drag_oy = event.y_root - self.winfo_y()

    def _drag_move(self, event):
        self.geometry(f"+{event.x_root - self._drag_ox}+{event.y_root - self._drag_oy}")

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self):
        try:
            monitors = capture.get_monitors()
            windows  = capture.get_visible_windows()
            self.after(0, lambda: self._populate(monitors, windows))
        except Exception as e:
            self.after(0, lambda err=e: self._status_lbl.configure(text=f"Error: {err}"))

    def _reload(self):
        for card, _ in self._card_data:
            if card.winfo_exists():
                card.destroy()
        self._card_data.clear()

        for w in list(self._scroll.winfo_children()):
            w.destroy()

        self._status_lbl = ctk.CTkLabel(
            self._scroll, text=lang.t("picker_loading"),
            font=("Arial", 11), text_color=T["muted"],
        )
        self._status_lbl.pack(pady=30)

        threading.Thread(target=self._load_data, daemon=True).start()

    def _populate(self, monitors: list, windows: list):
        if not self.winfo_exists():
            return
        self._status_lbl.destroy()

        # ── SCREENS ──────────────────────────────────────────────────────────
        screens_wrap = ctk.CTkFrame(self._scroll, fg_color="transparent")
        screens_wrap.pack(fill="x", padx=self._PAD, pady=(10, 0))

        ctk.CTkLabel(
            screens_wrap, text=lang.t("picker_screens"),
            font=("Arial", 9, "bold"), text_color=T["muted"], anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        screens_row = ctk.CTkFrame(screens_wrap, fg_color="transparent")
        screens_row.pack(fill="x")

        for col, mon in enumerate(monitors):
            card = self._make_card(screens_row, mon)
            card.grid(row=0, column=col,
                      padx=(0 if col == 0 else self._GAP, 0), sticky="nw")
            self._card_data.append((card, mon))
            self._launch_screen_thumb(card, mon)

        # ── APPLICATIONS ─────────────────────────────────────────────────────
        apps_wrap = ctk.CTkFrame(self._scroll, fg_color="transparent")
        apps_wrap.pack(fill="x", padx=self._PAD, pady=(14, 12))

        ctk.CTkLabel(
            apps_wrap, text=lang.t("picker_apps"),
            font=("Arial", 9, "bold"), text_color=T["muted"], anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        if not windows:
            ctk.CTkLabel(apps_wrap, text=lang.t("picker_no_windows"),
                         font=("Arial", 10), text_color=T["muted"]).pack()
            return

        apps_grid = ctk.CTkFrame(apps_wrap, fg_color="transparent")
        apps_grid.pack(fill="x")

        for i, win in enumerate(windows):
            row = i // self._COLS
            col = i % self._COLS
            card = self._make_card(apps_grid, win)
            card.grid(
                row=row, column=col,
                padx=(0 if col == 0 else self._GAP, 0),
                pady=(0 if row == 0 else self._GAP, 0),
                sticky="nw",
            )
            self._card_data.append((card, win))
            self._launch_window_thumb(card, win)

    # ── Async thumbnail loaders ───────────────────────────────────────────────

    def _launch_screen_thumb(self, card, mon: dict):
        def _work():
            thumb = capture.get_screen_thumbnail(mon, self._THUMB_W, self._THUMB_H)
            if thumb and self.winfo_exists():
                img = ctk.CTkImage(light_image=thumb,
                                   size=(self._THUMB_W, self._THUMB_H))
                self.after(0, lambda: self._set_thumb(card, img))
        threading.Thread(target=_work, daemon=True).start()

    def _launch_window_thumb(self, card, win: dict):
        def _work():
            thumb = capture.get_window_thumbnail(
                win["hwnd"], win["width"], win["height"],
                self._THUMB_W, self._THUMB_H)
            icon  = capture.get_window_icon(win["hwnd"], 14)
            updates = {}
            if thumb:
                updates["thumb"] = ctk.CTkImage(light_image=thumb,
                                                 size=(self._THUMB_W, self._THUMB_H))
            if icon:
                updates["icon"]  = ctk.CTkImage(light_image=icon, size=(14, 14))
            if updates and self.winfo_exists():
                self.after(0, lambda u=updates: self._apply_updates(card, u))
        threading.Thread(target=_work, daemon=True).start()

    def _set_thumb(self, card, ctk_img):
        if card.winfo_exists() and hasattr(card, "_thumb_lbl"):
            card._thumb_lbl.configure(image=ctk_img, text="")

    def _apply_updates(self, card, updates: dict):
        if not card.winfo_exists():
            return
        if "thumb" in updates and hasattr(card, "_thumb_lbl"):
            card._thumb_lbl.configure(image=updates["thumb"], text="")
        if "icon" in updates and hasattr(card, "_icon_lbl"):
            card._icon_lbl.configure(image=updates["icon"])

    # ── Card builder ──────────────────────────────────────────────────────────

    def _make_card(self, parent, info: dict) -> ctk.CTkFrame:
        selected = self._is_current(info)
        card = ctk.CTkFrame(
            parent,
            width=self._CARD_W, height=self._CARD_H,
            fg_color=T["card"], corner_radius=8,
            border_width=2,
            border_color=T["accent"] if selected else T["card_border"],
        )
        card.pack_propagate(False)

        # Thumbnail placeholder
        thumb_lbl = ctk.CTkLabel(
            card, text="", image=None,
            width=self._THUMB_W, height=self._THUMB_H,
            fg_color=T["card_inner"], corner_radius=6,
        )
        thumb_lbl.pack(padx=2, pady=(2, 0))
        card._thumb_lbl = thumb_lbl

        # Bottom row: icon + title
        bot = ctk.CTkFrame(card, fg_color="transparent", height=24)
        bot.pack(fill="x", padx=5, pady=(2, 2))
        bot.pack_propagate(False)

        icon_lbl = ctk.CTkLabel(bot, text="", width=14, height=14,
                                 fg_color="transparent")
        icon_lbl.pack(side="left")
        card._icon_lbl = icon_lbl

        title = info.get("name") if info.get("type") == "screen" else info.get("title", "")
        display = (title[:20] + "…") if len(title) > 20 else title
        ctk.CTkLabel(
            bot, text=display,
            font=("Arial", 9), text_color=T["primary"], anchor="w",
        ).pack(side="left", padx=(3, 0))

        self._bind_card(card, info)
        return card

    def _bind_card(self, card: ctk.CTkFrame, info: dict):
        _leave_id = [None]

        def on_click(*_):
            self._on_select(info)
            self.destroy()

        def on_enter(*_):
            if _leave_id[0]:
                card.after_cancel(_leave_id[0])
                _leave_id[0] = None
            if not self._is_current(info):
                card.configure(border_color="#4a5055")

        def on_leave(*_):
            def _do():
                if not self._is_current(info):
                    card.configure(border_color=T["card_border"])
            if _leave_id[0]:
                card.after_cancel(_leave_id[0])
            _leave_id[0] = card.after(40, _do)

        def _bind_all(widget):
            widget.bind("<Button-1>", on_click)
            widget.bind("<Enter>",    on_enter)
            widget.bind("<Leave>",    on_leave)
            for child in widget.winfo_children():
                _bind_all(child)

        _bind_all(card)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_current(self, info: dict) -> bool:
        if not self._cur_target:
            return False
        if info.get("type") != self._cur_target.get("type"):
            return False
        if info.get("type") == "screen":
            return info.get("index") == self._cur_target.get("index")
        return info.get("hwnd") == self._cur_target.get("hwnd")


# ══════════════════════════════════════════════════════════════════════════════
#  PROJECT PICKER POPUP
# ══════════════════════════════════════════════════════════════════════════════

class ProjectPickerPopup(ctk.CTkToplevel):
    _POPUP_W = 520
    _POPUP_H = 420
    _PAD     = 14

    def __init__(self, parent, current_project: str, base_path: str, on_select, on_delete):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(fg_color=T["popup_bg"])
        self.wm_attributes("-topmost", True)

        self._on_select = on_select
        self._on_delete = on_delete
        self._current   = current_project
        self._base_path = base_path
        self._drag_ox   = 0
        self._drag_oy   = 0

        parent.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self._POPUP_W) // 2
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self._POPUP_H) // 2)
        self.geometry(f"{self._POPUP_W}x{self._POPUP_H}+{px}+{py}")

        self._build_ui()
        self.after(20, self._apply_round)
        self.grab_set()
        self.after(60, self._name_entry.focus)

    def _apply_round(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        _apply_dwm_round(hwnd, large=False)

    def _build_ui(self):
        # Title bar
        tbar = ctk.CTkFrame(self, fg_color=T["popup_bg"], height=42, corner_radius=0)
        tbar.pack(fill="x")
        tbar.pack_propagate(False)
        tbar.bind("<Button-1>",  self._drag_start)
        tbar.bind("<B1-Motion>", self._drag_move)

        _lbl = ctk.CTkLabel(
            tbar, text=lang.t("proj_title"),
            font=("Arial", 10, "bold"), text_color=T["subtext"],
        )
        _lbl.place(relx=0.5, rely=0.5, anchor="center")
        _lbl.bind("<Button-1>",  self._drag_start)
        _lbl.bind("<B1-Motion>", self._drag_move)

        ctk.CTkButton(
            tbar, text="✕", width=30, height=30,
            fg_color="transparent", hover_color="#c42b1c",
            font=("Arial", 13, "bold"),
            command=self.destroy,
        ).place(relx=1.0, rely=0.5, anchor="e", x=-6)

        # New project input
        new_section = ctk.CTkFrame(self, fg_color="transparent")
        new_section.pack(fill="x", padx=self._PAD, pady=(10, 0))

        ctk.CTkLabel(
            new_section, text=lang.t("proj_new"),
            font=("Arial", 9, "bold"), text_color=T["muted"], anchor="w",
        ).pack(anchor="w", pady=(0, 4))

        entry_row = ctk.CTkFrame(new_section, fg_color="transparent")
        entry_row.pack(fill="x")

        self._name_entry = ctk.CTkEntry(
            entry_row, height=34,
            placeholder_text=lang.t("proj_new_ph"),
            font=("Arial", 11), fg_color=T["card"],
        )
        self._name_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._name_entry.bind("<Return>", lambda e: self._confirm_new())

        ctk.CTkButton(
            entry_row, text="✓", width=34, height=34,
            fg_color=T["accent"], hover_color=T["accent_dim"],
            font=("Arial", 13, "bold"),
            command=self._confirm_new,
        ).pack(side="left")

        # Existing projects section
        ctk.CTkLabel(
            self, text=lang.t("proj_existing"),
            font=("Arial", 9, "bold"), text_color=T["muted"], anchor="w",
        ).pack(anchor="w", padx=self._PAD, pady=(10, 0))

        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=T["hover"],
            scrollbar_button_hover_color=T["muted"],
        )
        self._scroll.pack(fill="both", expand=True, padx=self._PAD, pady=(4, self._PAD))

        self._populate()

    def _drag_start(self, event):
        self._drag_ox = event.x_root - self.winfo_x()
        self._drag_oy = event.y_root - self.winfo_y()

    def _drag_move(self, event):
        self.geometry(f"+{event.x_root - self._drag_ox}+{event.y_root - self._drag_oy}")

    def _populate(self):
        for w in list(self._scroll.winfo_children()):
            w.destroy()

        projects = config.get_existing_projects(self._base_path)
        if not projects:
            ctk.CTkLabel(
                self._scroll, text=lang.t("proj_no_projects"),
                font=("Arial", 10), text_color=T["muted"],
            ).pack(pady=16)
            return

        for name in projects:
            self._make_row(name)

    def _make_row(self, name: str):
        selected = (name == self._current)

        frame_count = 0
        if self._base_path:
            proj_path = os.path.join(self._base_path, name)
            if os.path.isdir(proj_path):
                try:
                    frame_count = len([f for f in os.listdir(proj_path) if f.endswith(".png")])
                except Exception:
                    pass

        row = ctk.CTkFrame(
            self._scroll,
            fg_color=T["card"], corner_radius=8,
            border_width=2,
            border_color=T["accent"] if selected else T["card_border"],
            height=50,
        )
        row.pack(fill="x", pady=(0, 6))
        row.pack_propagate(False)

        # Folder icon area
        icon_area = ctk.CTkFrame(row, fg_color=T["card_inner"], corner_radius=6, width=36, height=36)
        icon_area.pack(side="left", padx=(7, 0), pady=7)
        icon_area.pack_propagate(False)
        ctk.CTkLabel(
            icon_area, text="📁", font=("Arial", 14), fg_color="transparent",
            text_color=T["accent"],
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Name + frame count
        info_col = ctk.CTkFrame(row, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=6)

        ctk.CTkLabel(
            info_col, text=name,
            font=("Arial", 10, "bold"), text_color=T["primary"], anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            info_col,
            text=lang.t("frame_plural" if frame_count != 1 else "frame_single", n=frame_count),
            font=("Arial", 9), text_color=T["muted"], anchor="w",
        ).pack(anchor="w")

        # Delete button — excluded from click-to-select binding
        del_btn = ctk.CTkButton(
            row, text="🗑", width=30, height=30,
            fg_color="transparent", hover_color="#5a2020",
            font=("Arial", 13), text_color="#ff5555",
            command=lambda n=name: self._request_delete(n),
        )
        del_btn.pack(side="right", padx=(0, 7))

        # Open folder button — excluded from click-to-select binding
        def _open_folder(path=proj_path):
            if os.path.isdir(path):
                import subprocess
                subprocess.Popen(["explorer", os.path.normpath(path)])

        open_btn = ctk.CTkButton(
            row, text="▲", width=30, height=30,
            fg_color="transparent", hover_color=T["accent_dim"],
            font=("Arial", 14, "bold"), text_color=T["accent"],
            command=_open_folder,
        )
        open_btn.pack(side="right", padx=(0, 2))

        self._bind_row(row, name, del_btn, open_btn)

    def _bind_row(self, row, name, del_btn, open_btn=None):
        _leave_id = [None]

        def on_click(*_):
            self._on_select(name)
            self.destroy()

        def on_enter(*_):
            if _leave_id[0]:
                row.after_cancel(_leave_id[0])
                _leave_id[0] = None
            if name != self._current:
                row.configure(border_color="#4a5055")

        def on_leave(*_):
            def _do():
                if name != self._current:
                    row.configure(border_color=T["card_border"])
            if _leave_id[0]:
                row.after_cancel(_leave_id[0])
            _leave_id[0] = row.after(40, _do)

        skip = {del_btn, open_btn}

        def _bind_all(widget):
            if widget in skip:
                return
            widget.bind("<Button-1>", on_click)
            widget.bind("<Enter>",    on_enter)
            widget.bind("<Leave>",    on_leave)
            for child in widget.winfo_children():
                _bind_all(child)

        _bind_all(row)

    def _confirm_new(self):
        name = self._name_entry.get().strip()
        if not name:
            self._name_entry.configure(border_color="red")
            self.after(800, lambda: self._name_entry.configure(border_color="gray"))
            return
        self._on_select(name)
        self.destroy()

    def _request_delete(self, name: str):
        self.grab_release()
        self._on_delete(name, refresh_cb=self._safe_repopulate)

    def _safe_repopulate(self):
        if self.winfo_exists():
            self._populate()
            self.grab_set()


# ══════════════════════════════════════════════════════════════════════════════
#  EXPORT POPUP
# ══════════════════════════════════════════════════════════════════════════════

class ExportPopup(ctk.CTkToplevel):
    _POPUP_W = 300
    _POPUP_H = 260

    _DUR_SNAPS  = [15, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600, None]
    _DUR_LABELS = ["15s", "30s", "45s", "1m", "1m30s",
                   "2m", "3m", "4m", "5m", "7m", "10m", "Realtime"]
    _QUALITY_LABELS = ["Smallest", "Small", "Balanced", "High", "Highest"]
    _QUALITY_CRF    = [32, 28, 23, 20, 18]
    _QUALITY_PRESET = ["veryfast", "fast", "medium", "slow", "veryslow"]

    def __init__(self, parent, on_export,
                 init_dur_idx=1, init_qual_idx=2, init_custom_secs=None):
        super().__init__(parent)
        self._on_export = on_export
        self._custom_duration_secs = init_custom_secs
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(fg_color=T["popup_bg"])
        self.resizable(False, False)

        self._drag_ox = 0
        self._drag_oy = 0

        self._build_ui(init_dur_idx, init_qual_idx)
        self.update_idletasks()

        # Auto-fit height, then center over parent
        h = self.winfo_reqheight()
        self._POPUP_H = h
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x = px + (pw - self._POPUP_W) // 2
        y = py + ph // 2 - h // 2
        self.geometry(f"{self._POPUP_W}x{h}+{x}+{y}")

        self.after(100, self._apply_round_region)
        self.grab_set()
        self.bind("<Escape>", lambda _: self.destroy())

    def _apply_round_region(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        _apply_dwm_round(hwnd, large=False)

    def _drag_start(self, event):
        self._drag_ox = event.x_root - self.winfo_x()
        self._drag_oy = event.y_root - self.winfo_y()

    def _drag_move(self, event):
        self.geometry(f"+{event.x_root - self._drag_ox}+{event.y_root - self._drag_oy}")

    def _build_ui(self, init_dur_idx, init_qual_idx):
        # Title bar
        hdr = ctk.CTkFrame(self, fg_color=T["popup_bg"], height=42, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<Button-1>",  self._drag_start)
        hdr.bind("<B1-Motion>", self._drag_move)

        _lbl = ctk.CTkLabel(hdr, text=lang.t("export_title"),
                            font=("Arial", 10, "bold"),
                            text_color=T["subtext"])
        _lbl.place(relx=0.5, rely=0.5, anchor="center")
        _lbl.bind("<Button-1>",  self._drag_start)
        _lbl.bind("<B1-Motion>", self._drag_move)
        ctk.CTkButton(hdr, text="✕", width=30, height=30,
                      fg_color="transparent", hover_color="#c42b1c",
                      font=("Arial", 13, "bold"),
                      command=self.destroy
                      ).place(relx=1.0, rely=0.5, anchor="e", x=-6)

        self._body = ctk.CTkFrame(self, fg_color="transparent")
        body = self._body
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # Duration
        dur_row = ctk.CTkFrame(body, fg_color="transparent")
        dur_row.pack(fill="x")
        self._dur_lbl = ctk.CTkLabel(dur_row, text=lang.t("lbl_duration"),
                                     font=("Arial", 13), anchor="w")
        self._dur_lbl.pack(side="left")
        self.duration_val_label = ctk.CTkLabel(
            dur_row, text=self._DUR_LABELS[init_dur_idx],
            font=("Arial", 13, "underline"),
            text_color=T["accent"], cursor="hand2")
        self.duration_val_label.pack(side="right")
        self.duration_val_label.bind("<Button-1>", self._open_duration_entry)

        self.duration_slider = ctk.CTkSlider(
            body, from_=0, to=len(self._DUR_SNAPS) - 1,
            number_of_steps=len(self._DUR_SNAPS) - 1,
            button_color=T["accent"], button_hover_color=T["primary"],
            progress_color=T["accent"],
            command=self._on_duration_slide)
        self.duration_slider.set(init_dur_idx)
        self.duration_slider.pack(fill="x", pady=(2, 0))

        dur_hints = ctk.CTkFrame(body, fg_color="transparent")
        dur_hints.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(dur_hints, text=lang.t("hint_15s"),
                     font=("Arial", 11), text_color="#444444").pack(side="left")
        ctk.CTkLabel(dur_hints, text=lang.t("hint_realtime"),
                     font=("Arial", 11), text_color="#444444").pack(side="right")

        self._dur_entry_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.duration_entry = ctk.CTkEntry(
            self._dur_entry_frame, height=28,
            placeholder_text='e.g. "1.5" or "2m30s"',
            font=("Arial", 11))
        self.duration_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.duration_entry.bind("<Return>", lambda e: self._apply_duration_entry())
        self.duration_entry.bind("<Escape>", lambda e: self._dur_entry_frame.pack_forget())
        ctk.CTkButton(
            self._dur_entry_frame, text="✓", width=32, height=28,
            fg_color=T["accent"], hover_color=T["accent_dim"],
            font=("Arial", 12, "bold"),
            command=self._apply_duration_entry).pack(side="left")

        # Quality
        q_row = ctk.CTkFrame(body, fg_color="transparent")
        q_row.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(q_row, text=lang.t("lbl_quality"),
                     font=("Arial", 13), anchor="w").pack(side="left")
        self.quality_val_label = ctk.CTkLabel(
            q_row, text=self._QUALITY_LABELS[init_qual_idx],
            font=("Arial", 12), text_color="gray")
        self.quality_val_label.pack(side="right")

        self.quality_slider = ctk.CTkSlider(
            body, from_=0, to=4, number_of_steps=4,
            button_color=T["accent"], button_hover_color=T["primary"],
            progress_color=T["accent"],
            command=self._update_quality_label)
        self.quality_slider.set(init_qual_idx)
        self.quality_slider.pack(fill="x", pady=(2, 0))

        q_hints = ctk.CTkFrame(body, fg_color="transparent")
        q_hints.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(q_hints, text=lang.t("hint_smallest"),
                     font=("Arial", 11), text_color="#444444").pack(side="left")
        ctk.CTkLabel(q_hints, text=lang.t("hint_highest"),
                     font=("Arial", 11), text_color="#444444").pack(side="right")

        # Export button
        self._export_btn = ctk.CTkButton(
            body, text=lang.t("btn_export"),
            fg_color=T["accent"], hover_color=T["accent_dim"],
            font=("Arial", 12, "bold"), height=34,
            command=self._do_export)
        self._export_btn.pack(fill="x", pady=(10, 0))

    # ── duration helpers ──────────────────────────────────────────────────────

    def _on_duration_slide(self, val):
        idx = int(round(float(val)))
        self.duration_slider.set(idx)
        self._custom_duration_secs = None
        self.duration_val_label.configure(text=self._DUR_LABELS[idx])
        if self._DUR_SNAPS[idx] is None:
            self._dur_entry_frame.pack_forget()

    def get_duration_seconds(self):
        if getattr(self, "_custom_duration_secs", None):
            return self._custom_duration_secs
        idx = int(round(float(self.duration_slider.get())))
        return self._DUR_SNAPS[idx]

    def _open_duration_entry(self, _event=None):
        idx = int(round(float(self.duration_slider.get())))
        if self._DUR_SNAPS[idx] is None:
            return
        if self._dur_entry_frame.winfo_ismapped():
            self._dur_entry_frame.pack_forget()
        else:
            self._dur_entry_frame.pack(fill="x", padx=10, pady=(4, 0),
                                       after=self.duration_slider)
            self.after(50, self.duration_entry.focus)

    def _apply_duration_entry(self):
        import re
        raw = self.duration_entry.get().strip().lower()
        try:
            m = re.fullmatch(r'(\d+)m(\d+)s?', raw)
            if m:
                secs = int(m.group(1)) * 60 + int(m.group(2))
            elif raw.endswith("m"):
                secs = int(float(raw[:-1]) * 60)
            elif raw.endswith("s"):
                secs = float(raw[:-1])
            else:
                secs = float(raw)
            if secs <= 0:
                raise ValueError
            self._custom_duration_secs = secs
            mins, s = divmod(int(secs), 60)
            self.duration_val_label.configure(
                text=f"{mins}m{s}s" if mins else f"{int(secs)}s")
            self._dur_entry_frame.pack_forget()
            self.duration_entry.configure(border_color="gray")
        except ValueError:
            self.duration_entry.configure(border_color="red")
            self.after(800, lambda: self.duration_entry.configure(border_color="gray"))

    # ── quality helpers ───────────────────────────────────────────────────────

    def _update_quality_label(self, val):
        idx = int(round(float(val)))
        self.quality_val_label.configure(text=self._QUALITY_LABELS[idx])

    def get_crf_and_preset(self):
        idx = int(round(float(self.quality_slider.get())))
        return self._QUALITY_CRF[idx], self._QUALITY_PRESET[idx]

    def get_quality_label(self):
        idx = int(round(float(self.quality_slider.get())))
        return self._QUALITY_LABELS[idx]

    # ── export ────────────────────────────────────────────────────────────────

    def _do_export(self):
        self._show_progress_view()
        self._on_export(
            duration_secs=self.get_duration_seconds(),
            crf_preset=self.get_crf_and_preset(),
            quality_label=self.get_quality_label(),
            on_progress_cb=self._on_progress,
            on_success_cb=self._show_success_view,
            on_error_cb=self._show_error_view,
        )

    def _show_progress_view(self):
        self._body.destroy()
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=14, pady=10)

        ctk.CTkLabel(self._body, text=lang.t("status_exporting"),
                     font=("Arial", 13, "bold")).pack(pady=(10, 6))

        self._progress_bar = ctk.CTkProgressBar(
            self._body, width=240, height=14,
            progress_color=T["accent"], fg_color=T.get("border", "#333333"))
        self._progress_bar.set(0)
        self._progress_bar.pack(pady=(0, 6))

        self._progress_lbl = ctk.CTkLabel(
            self._body, text="0%", font=("Arial", 11), text_color="gray")
        self._progress_lbl.pack()

    def _on_progress(self, fraction):
        if hasattr(self, "_progress_bar") and self._progress_bar.winfo_exists():
            self._progress_bar.set(fraction)
        if hasattr(self, "_progress_lbl") and self._progress_lbl.winfo_exists():
            self._progress_lbl.configure(text=f"{int(fraction * 100)}%")

    def _show_success_view(self, out_path):
        self._body.destroy()
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=14, pady=10)

        ctk.CTkLabel(self._body, text="✓", font=("Arial", 32, "bold"),
                     text_color=T["accent"]).pack(pady=(12, 4))
        ctk.CTkLabel(self._body, text=lang.t("export_success"),
                     font=("Arial", 13, "bold")).pack(pady=(0, 12))

        def _open_folder():
            import subprocess as sp
            sp.Popen(["explorer", os.path.normpath(os.path.dirname(out_path))])

        ctk.CTkButton(
            self._body, text=lang.t("btn_open_folder"),
            fg_color=T["accent"], hover_color=T["accent_dim"],
            font=("Arial", 12, "bold"), height=34,
            command=_open_folder,
        ).pack(fill="x", pady=(0, 4))

        ctk.CTkButton(
            self._body, text=lang.t("btn_close"),
            fg_color="transparent", hover_color=T.get("border", "#333333"),
            font=("Arial", 11), height=28,
            command=self.destroy,
        ).pack(fill="x")

    def _show_error_view(self, msg):
        self._body.destroy()
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=14, pady=10)

        ctk.CTkLabel(self._body, text="✕", font=("Arial", 28, "bold"),
                     text_color="red").pack(pady=(12, 4))
        ctk.CTkLabel(self._body, text=msg, font=("Arial", 11),
                     text_color="red", wraplength=240).pack(pady=(0, 12))
        ctk.CTkButton(
            self._body, text=lang.t("btn_close"),
            fg_color=T["accent"], hover_color=T["accent_dim"],
            font=("Arial", 12, "bold"), height=34,
            command=self.destroy,
        ).pack(fill="x")


# ══════════════════════════════════════════════════════════════════════════════
#  SETTINGS POPUP
# ══════════════════════════════════════════════════════════════════════════════

class SettingsPopup(ctk.CTkToplevel):
    _POPUP_W = 320
    _POPUP_H = 428

    def __init__(self, parent, on_lang_change, on_settings_change=None, on_theme_change=None):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(fg_color=T["popup_bg"])
        self.wm_attributes("-topmost", True)

        self._on_lang_change     = on_lang_change
        self._on_settings_change = on_settings_change
        self._on_theme_change    = on_theme_change
        self._drag_ox = 0
        self._drag_oy = 0

        parent.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self._POPUP_W) // 2
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self._POPUP_H) // 2)
        self.geometry(f"{self._POPUP_W}x{self._POPUP_H}+{px}+{py}")

        self._build_ui()
        self.after(20, self._apply_round)
        self.grab_set()

    def _apply_round(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        _apply_dwm_round(hwnd, large=False)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _row(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", pady=(0, 6))
        return f

    def _lbl(self, parent, key):
        return ctk.CTkLabel(parent, text=lang.t(key),
                            font=("Arial", 12), text_color=T["label"],
                            width=120, anchor="w")

    def _tri_buttons(self, parent, options, current, on_select):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        btns = {}
        for key, display in options:
            active = key == current
            b = ctk.CTkButton(
                frame, text=display,
                width=54, height=26,
                font=("Arial", 11),
                fg_color=T["accent"] if active else T["card"],
                hover_color=T["accent_dim"] if active else T["hover"],
                text_color="white" if active else T["label"],
                corner_radius=5,
                command=lambda k=key: on_select(k),
            )
            b.pack(side="left", padx=(0, 3))
            btns[key] = b
        return frame, btns

    def _bind_tip(self, widget, text_key):
        """Lightweight hover tooltip for settings widgets."""
        tip = [None]

        def _show(*_):
            if tip[0]:
                return
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() - 34
            win = tk.Toplevel(self)
            win.overrideredirect(True)
            win.wm_attributes("-topmost", True)
            win.configure(bg=T["tooltip_bg"])
            win.geometry(f"+{x}+{y}")
            tk.Label(win, text=lang.t(text_key), font=("Arial", 10),
                     fg=T["tooltip_fg"], bg=T["tooltip_bg"], padx=8, pady=4).pack()
            tip[0] = win
            self.after(50, _poll)

        def _poll():
            if not tip[0]:
                return
            try:
                mx = self.winfo_pointerx()
                my = self.winfo_pointery()
                wx = widget.winfo_rootx()
                wy = widget.winfo_rooty()
                if mx < wx or mx > wx + widget.winfo_width() or \
                   my < wy or my > wy + widget.winfo_height():
                    _hide()
                    return
            except Exception:
                _hide()
                return
            self.after(50, _poll)

        def _hide(*_):
            if tip[0]:
                tip[0].destroy()
                tip[0] = None

        widget.bind("<Enter>", _show, add="+")
        widget.bind("<Leave>", _hide, add="+")

    def _refresh_tri(self, btns, active_key):
        for k, b in btns.items():
            active = k == active_key
            b.configure(
                fg_color=T["accent"] if active else T["card"],
                hover_color=T["accent_dim"] if active else T["hover"],
                text_color="white" if active else T["label"],
            )

    # ── UI build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        tbar = ctk.CTkFrame(self, fg_color=T["popup_bg"], height=42, corner_radius=0)
        self._tbar = tbar
        tbar.pack(fill="x")
        tbar.pack_propagate(False)
        tbar.bind("<Button-1>",  self._drag_start)
        tbar.bind("<B1-Motion>", self._drag_move)

        _lbl = ctk.CTkLabel(
            tbar, text=lang.t("settings_title"),
            font=("Arial", 10, "bold"), text_color=T["subtext"],
        )
        _lbl.place(relx=0.5, rely=0.5, anchor="center")
        _lbl.bind("<Button-1>",  self._drag_start)
        _lbl.bind("<B1-Motion>", self._drag_move)

        ctk.CTkButton(
            tbar, text="\u2715", width=30, height=30,
            fg_color="transparent", hover_color="#c42b1c",
            font=("Arial", 13, "bold"),
            command=self.destroy,
        ).place(relx=1.0, rely=0.5, anchor="e", x=-6)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # ── Language ──────────────────────────────────────────────────────
        row = self._row(body)
        self._lbl_language = self._lbl(row, "settings_language")
        self._lbl_language.pack(side="left")
        bf = ctk.CTkFrame(row, fg_color="transparent")
        bf.pack(side="right")
        self._lang_btns = {}
        for code, label in [("en", "English"), ("es", "Espa\u00f1ol")]:
            b = ctk.CTkButton(
                bf, text=label,
                width=82, height=26,
                font=("Arial", 11),
                fg_color=T["accent"] if lang.get_lang() == code else T["card"],
                hover_color=T["accent_dim"] if lang.get_lang() == code else T["hover"],
                text_color="white" if lang.get_lang() == code else T["label"],
                corner_radius=5,
                command=lambda c=code: self._select_lang(c),
            )
            b.pack(side="left", padx=(0 if code == "en" else 4, 0))
            self._lang_btns[code] = b

        # ── Capture Quality ───────────────────────────────────────────────
        row = self._row(body)
        self._lbl_cq = self._lbl(row, "settings_capture_quality")
        self._lbl_cq.pack(side="left")
        cq_opts = [("Low", lang.t("cq_low")), ("Med", lang.t("cq_med")), ("High", lang.t("cq_high"))]
        self._cq_frame, self._cq_btns = self._tri_buttons(
            row, cq_opts, config.load_capture_quality(), self._select_cq)
        self._cq_frame.pack(side="right")
        self._bind_tip(self._lbl_cq, "tip_settings_cq")
        for key, btn in self._cq_btns.items():
            self._bind_tip(btn, f"cq_tip_{key.lower()}")

        # ── Launch behavior ───────────────────────────────────────────────
        row = self._row(body)
        self._lbl_launch = self._lbl(row, "settings_launch")
        self._lbl_launch.pack(side="left")
        launch_opts = [
            ("normal",    lang.t("launch_normal")),
            ("minimized", lang.t("launch_minimized")),
            ("tray",      lang.t("launch_tray")),
        ]
        self._launch_frame, self._launch_btns = self._tri_buttons(
            row, launch_opts, config.load_launch_behavior(), self._select_launch)
        self._launch_frame.pack(side="right")

        # ── Smart Capture ─────────────────────────────────────────────────
        row = self._row(body)
        self._lbl_smart = self._lbl(row, "settings_smart_capture")
        self._lbl_smart.pack(side="left")
        self._smart_var = ctk.BooleanVar(value=config.load_smart_capture())
        self._smart_switch = ctk.CTkSwitch(row, text="", variable=self._smart_var,
                      width=40, button_color=T["accent"], progress_color=T["accent_dim"],
                      command=self._select_smart)
        self._smart_switch.pack(side="right")
        self._bind_tip(self._lbl_smart, "tip_settings_smart")

        # ── Auto-export ───────────────────────────────────────────────────
        row = self._row(body)
        self._lbl_auto = self._lbl(row, "settings_auto_export")
        self._lbl_auto.pack(side="left")
        self._auto_var = ctk.BooleanVar(value=config.load_auto_export())
        self._auto_switch = ctk.CTkSwitch(row, text="", variable=self._auto_var,
                      width=40, button_color=T["accent"], progress_color=T["accent_dim"],
                      command=self._select_auto)
        self._auto_switch.pack(side="right")
        self._bind_tip(self._lbl_auto, "tip_settings_auto_export")

        # ── Default Interval ──────────────────────────────────────────────
        _isteps  = [0.5, 1, 2.5, 5, 10, 15, 20, 30, 40, 50, 60]
        _ilabels = ["0.5s", "1s", "2.5s", "5s", "10s", "15s", "20s", "30s", "40s", "50s", "60s"]
        self._interval_steps  = _isteps
        self._interval_labels = _ilabels
        cur_ii = config.load_default_interval_idx()

        row = self._row(body)
        self._lbl_interval = self._lbl(row, "settings_interval")
        self._lbl_interval.pack(side="left")
        self._interval_val_lbl = ctk.CTkLabel(
            row, text=_ilabels[cur_ii], font=("Arial", 12), text_color=T["accent"])
        self._interval_val_lbl.pack(side="right")

        self._interval_slider = ctk.CTkSlider(
            body, from_=0, to=len(_isteps) - 1,
            number_of_steps=len(_isteps) - 1,
            button_color=T["accent"], button_hover_color=T["primary"],
            progress_color=T["accent"],
            command=self._on_interval_slide,
        )
        self._interval_slider.set(cur_ii)
        self._interval_slider.pack(fill="x", pady=(0, 8))

        # ── Default Duration ──────────────────────────────────────────────
        _dur_snaps  = [15, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600, None]
        _dur_labels = ["15s", "30s", "45s", "1m", "1m30s", "2m", "3m", "4m", "5m", "7m", "10m", "Realtime"]
        self._dur_snaps  = _dur_snaps
        self._dur_labels_list = _dur_labels
        cur_di = config.load_default_duration_idx()

        row = self._row(body)
        self._lbl_dur = self._lbl(row, "settings_duration")
        self._lbl_dur.pack(side="left")
        self._dur_val_lbl = ctk.CTkLabel(
            row, text=_dur_labels[cur_di], font=("Arial", 12), text_color=T["accent"])
        self._dur_val_lbl.pack(side="right")

        self._dur_slider = ctk.CTkSlider(
            body, from_=0, to=len(_dur_snaps) - 1,
            number_of_steps=len(_dur_snaps) - 1,
            button_color=T["accent"], button_hover_color=T["primary"],
            progress_color=T["accent"],
            command=self._on_dur_slide,
        )
        self._dur_slider.set(cur_di)
        self._dur_slider.pack(fill="x", pady=(0, 8))

        # ── Theme ─────────────────────────────────────────────────────────
        row = self._row(body)
        self._lbl_theme = self._lbl(row, "settings_theme")
        self._lbl_theme.pack(side="left")
        tf = ctk.CTkFrame(row, fg_color="transparent")
        tf.pack(side="right")
        self._theme_btns = {}
        cur_theme = constants.CURRENT_THEME_NAME
        for name, left_hex, right_hex in [
            ("light", "#F2EBD9", "#2A8B7A"),
            ("dark",  "#1e2123", "#e85c25"),
        ]:
            active = name == cur_theme
            ball_img = self._make_theme_ball(left_hex, right_hex)
            b = ctk.CTkButton(
                tf, text=lang.t(f"theme_{name}"),
                image=ball_img, compound="left",
                width=74, height=26,
                font=("Arial", 11),
                fg_color=T["accent"] if active else T["card"],
                hover_color=T["accent_dim"] if active else T["hover"],
                text_color="white" if active else T["label"],
                corner_radius=5,
                command=lambda n=name: self._select_theme(n),
            )
            b.pack(side="left", padx=(0, 4))
            self._theme_btns[name] = b

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _select_lang(self, code: str):
        lang.set_lang(code)
        config.save_lang(code)
        self._refresh_tri(self._lang_btns, code)
        self._lbl_language.configure(text=lang.t("settings_language"))
        self._lbl_cq.configure(text=lang.t("settings_capture_quality"))
        self._lbl_smart.configure(text=lang.t("settings_smart_capture"))
        self._lbl_interval.configure(text=lang.t("settings_interval"))
        self._lbl_auto.configure(text=lang.t("settings_auto_export"))
        self._lbl_dur.configure(text=lang.t("settings_duration"))
        self._lbl_launch.configure(text=lang.t("settings_launch"))
        for key, btn in self._cq_btns.items():
            btn.configure(text=lang.t(f"cq_{key.lower()}"))
        for key, btn in self._launch_btns.items():
            btn.configure(text=lang.t(f"launch_{key}"))
        self._lbl_theme.configure(text=lang.t("settings_theme"))
        for name, btn in self._theme_btns.items():
            btn.configure(text=lang.t(f"theme_{name}"))
        self._on_lang_change()

    def _select_cq(self, key: str):
        config.save_capture_quality(key)
        self._refresh_tri(self._cq_btns, key)
        if self._on_settings_change:
            self._on_settings_change("capture_quality", key)

    def _select_smart(self):
        config.save_smart_capture(self._smart_var.get())
        if self._on_settings_change:
            self._on_settings_change("smart_capture", self._smart_var.get())

    def _on_interval_slide(self, val):
        idx = int(round(float(val)))
        self._interval_val_lbl.configure(text=self._interval_labels[idx])
        config.save_default_interval_idx(idx)
        if self._on_settings_change:
            self._on_settings_change("default_interval_idx", idx)

    def _select_auto(self):
        config.save_auto_export(self._auto_var.get())
        if self._on_settings_change:
            self._on_settings_change("auto_export", self._auto_var.get())

    def _on_dur_slide(self, val):
        idx = int(round(float(val)))
        self._dur_val_lbl.configure(text=self._dur_labels_list[idx])
        config.save_default_duration_idx(idx)
        if self._on_settings_change:
            self._on_settings_change("default_duration_idx", idx)

    def _select_launch(self, key: str):
        config.save_launch_behavior(key)
        self._refresh_tri(self._launch_btns, key)

    def _select_theme(self, name: str):
        config.save_theme(name)
        _set_theme(name)
        self._apply_popup_theme()
        if self._on_theme_change:
            self._on_theme_change()

    def _apply_popup_theme(self):
        """Re-color all popup widgets to match the current theme T."""
        self.configure(fg_color=T["popup_bg"])
        self._tbar.configure(fg_color=T["popup_bg"])
        for lbl in (self._lbl_language, self._lbl_cq, self._lbl_smart,
                    self._lbl_interval, self._lbl_auto, self._lbl_dur,
                    self._lbl_launch, self._lbl_theme):
            lbl.configure(text_color=T["label"])
        self._interval_val_lbl.configure(text_color=T["accent"])
        self._dur_val_lbl.configure(text_color=T["accent"])
        self._interval_slider.configure(button_color=T["accent"], progress_color=T["accent"])
        self._dur_slider.configure(button_color=T["accent"], progress_color=T["accent"])
        self._smart_switch.configure(button_color=T["accent"], progress_color=T["accent_dim"])
        self._auto_switch.configure(button_color=T["accent"], progress_color=T["accent_dim"])
        cur_lang = lang.get_lang()
        self._refresh_tri(self._lang_btns, cur_lang)
        self._refresh_tri(self._cq_btns, config.load_capture_quality())
        self._refresh_tri(self._launch_btns, config.load_launch_behavior())
        cur_theme = constants.CURRENT_THEME_NAME
        for tname, btn in self._theme_btns.items():
            active = tname == cur_theme
            btn.configure(
                fg_color=T["accent"] if active else T["card"],
                hover_color=T["accent_dim"] if active else T["hover"],
                text_color="white" if active else T["label"],
            )

    @staticmethod
    def _make_theme_ball(left_hex: str, right_hex: str, size: int = 16):
        """Draw a split circle: left half = bg color, right half = accent color."""
        scale = 4
        s = size * scale
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Left half-circle
        d.pieslice([0, 0, s - 1, s - 1], start=90, end=270, fill=left_hex)
        # Right half-circle
        d.pieslice([0, 0, s - 1, s - 1], start=270, end=90, fill=right_hex)
        # White border so it stands out from any button background
        d.ellipse([0, 0, s - 1, s - 1], outline="white", width=max(2, scale))
        img = img.resize((size, size), Image.LANCZOS)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))

    def _drag_start(self, event):
        self._drag_ox = event.x_root - self.winfo_x()
        self._drag_oy = event.y_root - self.winfo_y()

    def _drag_move(self, event):
        self.geometry(f"+{event.x_root - self._drag_ox}+{event.y_root - self._drag_oy}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════

class ArtLapseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ArtLapse")
        self.overrideredirect(True)
        self.geometry(f"{APP_W}x{APP_H}")
        self.configure(fg_color=T["bg"])
        self.update_idletasks()
        import sys
        _base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        self._ico_path = os.path.join(_base, "assets", "artlapse.ico")
        self.after(20, self._setup_taskbar_presence)
        self.after(20, self.apply_round_region)

        # System tray
        self._tray_icon = None
        self._setup_tray()

        lang.set_lang(config.load_lang())

        self.is_recording          = False
        self.base_path             = config.load_config()
        self.after_id              = None
        self.count                 = 1
        self.final_path            = ""
        self._offsetx              = 0
        self._offsety              = 0
        self._thumb_photo          = None
        self._custom_duration_secs = None
        self._capture_target       = None   # dict from capture.get_visible_windows / get_monitors
        self._current_project      = ""
        self._identical_streak     = 0      # consecutive identical frames (smart capture)
        self._prev_thumb_bytes     = None   # last 32×32 grayscale thumbnail for diff
        self._frame_hashes         = set()  # hashes of captured frames for dedup
        self._tooltip_win          = None
        self._active_tooltips      = set()   # all open tooltip toplevels
        self._section_labels       = []      # tracked for _apply_theme()

        self._build_ui()

    # ------------------------------------------------------------------ #
    #  ROUNDED REGION                                                      #
    # ------------------------------------------------------------------ #
    def apply_round_region(self, _w=APP_W, _h=APP_H):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        _apply_dwm_round(hwnd, large=True)

    # ------------------------------------------------------------------ #
    #  UI CONSTRUCTION                                                     #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        # ── HEADER ──────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent", height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        _assets = os.path.dirname(os.path.abspath(__file__))
        _logo_dark_pil  = Image.open(os.path.join(_assets, "assets", "ArtLapse_title.png"))
        _logo_light_pil = Image.open(os.path.join(_assets, "assets", "ArtLapse_title_light.png"))
        self._logo_dark_pil  = _logo_dark_pil
        self._logo_light_pil = _logo_light_pil
        _logo_img  = ctk.CTkImage(light_image=_logo_light_pil, dark_image=_logo_dark_pil, size=(131, 34))
        self._title_lbl = ctk.CTkLabel(hdr, text="", image=_logo_img)
        self._title_lbl.place(relx=0.5, rely=0.55, anchor="center")
        self._title_lbl.bind("<Button-1>",  self._click_window)
        self._title_lbl.bind("<B1-Motion>", self._drag_window)

        # Cog button on the left
        left_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        left_frame.place(relx=0.0, rely=0.5, anchor="w", x=8)
        _cog_img = self._make_cog_image(size=20, color=T["muted"])
        self._cog_btn = ctk.CTkButton(
            left_frame, text="", image=_cog_img, width=28, height=28,
            fg_color="transparent", hover_color=T["bg"],
            corner_radius=6, command=self._open_settings)
        self._cog_btn.pack()
        self._cog_btn.bind("<Enter>", lambda _e: self._cog_btn.configure(
            image=self._make_cog_image(size=20, color=T["accent"])))
        self._cog_btn.bind("<Leave>", lambda _e: self._cog_btn.configure(
            image=self._make_cog_image(size=20, color=T["muted"])))
        self._bind_tooltip(self._cog_btn, lambda: lang.t("settings_title"))

        btn_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_frame.place(relx=1.0, rely=0.5, anchor="e", x=-8)

        self._min_btn = ctk.CTkButton(btn_frame, text="—", width=34, height=34,
                      fg_color="transparent", hover_color=T["hover"],
                      font=("Arial", 15, "bold"), text_color=T["primary"],
                      corner_radius=8, command=self._minimize)
        self._min_btn.pack(side="left", padx=2)
        self._bind_tooltip(self._min_btn, lang.t("tip_minimize"))

        self._tray_btn = ctk.CTkButton(btn_frame, text="⬛", width=34, height=34,
                      fg_color="transparent", hover_color=T["hover"],
                      font=("Arial", 11), text_color=T["accent"],
                      corner_radius=8, command=self._hide_to_tray)
        self._tray_btn.pack(side="left", padx=2)
        self._bind_tooltip(self._tray_btn, lang.t("tip_tray"))

        self._close_btn = ctk.CTkButton(btn_frame, text="✕", width=34, height=34,
                      fg_color="transparent", hover_color="#c42b1c",
                      font=("Arial", 15, "bold"), text_color=T["primary"],
                      corner_radius=8, command=self._quit_app)
        self._close_btn.pack(side="left", padx=2)
        self._bind_tooltip(self._close_btn, lang.t("tip_quit"))

        for widget in (hdr,):
            widget.bind("<Button-1>",  self._click_window)
            widget.bind("<B1-Motion>", self._drag_window)

        # ── BODY ────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        # Capture target picker
        self._step_target_lbl = self._section_label(body, lang.t("section_target"))
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", pady=(2, 0))

        self._target_btn = ctk.CTkButton(
            row1,
            text=lang.t("target_placeholder"),
            height=34, anchor="w",
            fg_color=T["card"], hover_color=T["hover"],
            font=("Arial", 12), text_color=T["subtext"],
            corner_radius=6,
            command=self._open_picker,
        )
        self._target_btn.pack(fill="x")

        # Capture quality is now set in Settings; load from config
        self._capture_quality_var = ctk.StringVar(value=config.load_capture_quality())

        # Folder picker
        self._step_folder_lbl = self._section_label(body, lang.t("section_folder"))
        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=(2, 0))
        self.folder_label = ctk.CTkLabel(row2,
                                         text="  📂  " + config.get_short_path(self.base_path),
                                         font=("Arial", 12), text_color=T["label"],
                                         fg_color=T["card"], corner_radius=6,
                                         anchor="w", height=34)
        self.folder_label.pack(side="left", fill="x", expand=True)
        self._browse_btn = ctk.CTkButton(row2, text="📁", width=44, height=34,
                      fg_color=T["card"], hover_color=T["accent_dim"],
                      text_color=T["accent"], font=("Arial", 16),
                      command=self.choose_folder)
        self._browse_btn.pack(side="left", padx=(6, 0))
        self._bind_tooltip(self._browse_btn, lang.t("tip_browse"))
        self._open_btn = ctk.CTkButton(row2, text="▲", width=38, height=34,
                      fg_color=T["card"], hover_color=T["accent_dim"],
                      font=("Arial", 17, "bold"), text_color=T["accent"],
                      command=self.open_output_folder)
        self._open_btn.pack(side="left", padx=(4, 0))
        self._bind_tooltip(self._open_btn, lang.t("tip_open_folder"))

        # Project name
        self._step_project_lbl = self._section_label(body, lang.t("section_project"))
        proj_row = ctk.CTkFrame(body, fg_color="transparent")
        proj_row.pack(fill="x", pady=(2, 0))

        self._project_btn = ctk.CTkButton(
            proj_row,
            text=lang.t("project_placeholder"),
            height=34, anchor="w",
            fg_color=T["card"], hover_color=T["hover"],
            font=("Arial", 12), text_color=T["subtext"],
            corner_radius=6,
            command=self._open_project_picker,
        )
        self._project_btn.pack(fill="x")

        # Interval slider
        self.INTERVAL_STEPS = [0.5, 1, 2.5, 5, 10, 15, 20, 30, 40, 50, 60]
        self._step_interval_lbl = self._section_label(body, lang.t("section_interval"))
        self.label_interval = ctk.CTkLabel(body, text="2.5 s",
                                           font=("Arial Black", 13),
                                           text_color=T["accent"])
        self.label_interval.pack(anchor="e")
        self.slider_interval = ctk.CTkSlider(
            body, from_=0, to=len(self.INTERVAL_STEPS) - 1,
            number_of_steps=len(self.INTERVAL_STEPS) - 1,
            button_color=T["accent"], button_hover_color=T["primary"],
            progress_color=T["accent"],
            command=self._update_interval_label
        )
        # Default notch marker above slider
        self._interval_marker = tk.Canvas(
            body, height=8, bg=T["bg"],
            highlightthickness=0
        )
        self._interval_marker.pack(fill="x", pady=(0, 0))
        self._interval_marker.bind("<Configure>", self._draw_interval_marker)

        _ii_default = config.load_default_interval_idx()
        self.slider_interval.set(_ii_default)
        self._update_interval_label(_ii_default)
        self.slider_interval.pack(fill="x", pady=(0, 4))

        # Smart Capture toggle
        smart_row = ctk.CTkFrame(body, fg_color="transparent")
        smart_row.pack(fill="x", pady=(0, 4))
        self.smart_capture_var = ctk.BooleanVar(value=config.load_smart_capture())
        self._smart_cb = ctk.CTkCheckBox(
            smart_row, text=lang.t("smart_capture"),
            variable=self.smart_capture_var,
            font=("Arial", 12),
            text_color=T["label"],
            checkbox_width=16, checkbox_height=16,
            corner_radius=4,
            checkmark_color="white",
            fg_color=T["accent"], hover_color=T["accent_dim"],
            border_color=T["muted"],
        )
        self._smart_cb.pack(side="left")
        self._smart_caption_lbl = ctk.CTkLabel(
            smart_row, text=lang.t("smart_caption"),
            font=("Arial", 10), text_color=T["muted"])
        self._smart_caption_lbl.pack(side="left", padx=(6, 0))
        self._bind_tooltip(self._smart_cb, lambda: lang.t("smart_tooltip"))

        # Status / guidance
        self.status_label = ctk.CTkLabel(body, text=lang.t("status_step1"),
                                         font=("Arial", 13, "bold"),
                                         text_color=T["subtext"])
        self.status_label.pack(pady=(2, 4))

        # Start / stop buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 4))

        self.start_btn = ctk.CTkButton(
            btn_row, text=lang.t("btn_start"), fg_color="#2a2a2a",
            hover_color="#2a2a2a", text_color=T["muted"],
            font=("Arial Black", 16, "bold"),
            height=52, state="disabled", command=self.toggle_capture
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
            export_header, text=lang.t("btn_export"),
            fg_color=T["card"], hover_color=T["hover"],
            text_color=T["primary"],
            font=("Arial", 13, "bold"),
            height=38, command=self._open_export_popup
        )
        self.ffmpeg_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        # Auto-export is configured in Settings; var drives stop_and_reset
        self.auto_compile_var = ctk.BooleanVar(value=config.load_auto_export())
        self._export_popup = None

        # ── Stats row: thumbnail + frames + size ─────────────────────────
        self._stats_row = ctk.CTkFrame(body, fg_color=T["card"], corner_radius=10)
        self._stats_row.pack(fill="x", pady=(6, 0))
        stats_row = self._stats_row

        stats_inner = ctk.CTkFrame(stats_row, fg_color="transparent")
        stats_inner.pack(fill="x", padx=8, pady=6)

        self.thumb_label = ctk.CTkLabel(stats_inner, text=lang.t("thumb_no_preview"),
                                        width=72, height=50,
                                        font=("Arial", 8), text_color=T["muted"],
                                        fg_color=T["card_inner"], corner_radius=6)
        self.thumb_label.pack(side="left", padx=(0, 10))

        stats_text = ctk.CTkFrame(stats_inner, fg_color="transparent")
        stats_text.pack(side="left", fill="both", expand=True)

        self.frames_label = ctk.CTkLabel(stats_text, text=lang.t("frames_zero"),
                                         font=("Arial", 11), text_color="gray",
                                         anchor="w")
        self.frames_label.pack(anchor="w")

        self.size_label = ctk.CTkLabel(stats_text, text="—",
                                       font=("Arial", 11), text_color=T["muted"],
                                       anchor="w")
        self.size_label.pack(anchor="w")

        self.warn_label = ctk.CTkLabel(stats_text, text="",
                                       font=("Arial", 11), text_color="orange",
                                       anchor="w")
        self.warn_label.pack(anchor="w")

        # Auto-fit window height to actual content
        self.after(30, self._fit_window_height)

    def _fit_window_height(self):
        self.update_idletasks()
        h = self.winfo_reqheight()
        self.geometry(f"{APP_W}x{h}")
        self.after(10, lambda: self.apply_round_region(APP_W, h))

    # ------------------------------------------------------------------ #
    #  UI HELPERS                                                          #
    # ------------------------------------------------------------------ #
    def _section_label(self, parent, text):
        lbl = ctk.CTkLabel(parent, text=text,
                           font=("Arial", 11, "bold"),
                           text_color=T["muted"], anchor="w")
        lbl.pack(anchor="w", pady=(6, 0))
        self._section_labels.append(lbl)
        return lbl

    def _open_settings(self):
        SettingsPopup(self, on_lang_change=self._apply_lang,
                      on_settings_change=self._apply_setting,
                      on_theme_change=self._apply_theme)

    def _apply_setting(self, key: str, value):
        """Live-apply a setting changed in SettingsPopup."""
        if key == "capture_quality":
            self._capture_quality_var.set(value)
        elif key == "smart_capture":
            self.smart_capture_var.set(value)
            self._smart_cb.select() if value else self._smart_cb.deselect()
        elif key == "default_interval_idx":
            self.slider_interval.set(value)
            self._update_interval_label(value)
            self._draw_interval_marker()
        elif key == "auto_export":
            self.auto_compile_var.set(value)
        elif key == "default_duration_idx":
            pass  # duration default is read by ExportPopup when it opens

    def _apply_lang(self):
        """Refresh all translatable widgets after a language change."""
        self._step_target_lbl.configure(text=lang.t("section_target"))
        self._step_folder_lbl.configure(text=lang.t("section_folder"))
        self._step_project_lbl.configure(text=lang.t("section_project"))
        self._step_interval_lbl.configure(text=lang.t("section_interval"))
        self._smart_cb.configure(text=lang.t("smart_capture"))
        self._smart_caption_lbl.configure(text=lang.t("smart_caption"))
        self.ffmpeg_btn.configure(text=lang.t("btn_export"))
        # Frames / thumb labels (only when not recording)
        if not self.is_recording:
            self.frames_label.configure(text=lang.t("frames_zero"))
            thumb_text = self.thumb_label.cget("text")
            if thumb_text:   # still showing placeholder text, not an image
                self.thumb_label.configure(text=lang.t("thumb_no_preview"))
            # Start button
            self.start_btn.configure(text=lang.t("btn_start"))
        # Target button placeholder (only if no target selected)
        if self._capture_target is None:
            self._target_btn.configure(text=lang.t("target_placeholder"))
        # Project button placeholder (only if no project selected)
        if not self._current_project.strip():
            self._project_btn.configure(text=lang.t("project_placeholder"))
        # Re-run guidance so the status label updates too
        self._update_status_guidance()

    def _apply_theme(self):
        """Re-color all tracked widgets to match the current theme T."""
        self.configure(fg_color=T["bg"])

        _is_light = constants.CURRENT_THEME_NAME == "light"
        _logo_pil = self._logo_light_pil if _is_light else self._logo_dark_pil
        self._title_lbl.configure(
            image=ctk.CTkImage(light_image=_logo_pil, dark_image=_logo_pil, size=(131, 34))
        )

        self._cog_btn.configure(hover_color=T["bg"],
                                image=self._make_cog_image(size=20, color=T["muted"]))
        self._min_btn.configure(hover_color=T["hover"], text_color=T["primary"])
        self._tray_btn.configure(hover_color=T["hover"], text_color=T["accent"])
        self._close_btn.configure(text_color=T["primary"])
        for lbl in self._section_labels:
            lbl.configure(text_color=T["muted"])
        self._target_btn.configure(fg_color=T["card"], hover_color=T["hover"],
                                   text_color=T["subtext"])
        self.folder_label.configure(fg_color=T["card"], text_color=T["label"])
        self._browse_btn.configure(fg_color=T["card"], hover_color=T["accent_dim"],
                                   text_color=T["accent"])
        self._open_btn.configure(fg_color=T["card"], hover_color=T["accent_dim"],
                                 text_color=T["accent"])
        self._project_btn.configure(fg_color=T["card"], hover_color=T["hover"],
                                    text_color=T["subtext"])
        self.label_interval.configure(text_color=T["accent"])
        self.slider_interval.configure(button_color=T["accent"], progress_color=T["accent"])
        self._interval_marker.configure(bg=T["bg"])
        self._draw_interval_marker()
        self._smart_cb.configure(text_color=T["label"], fg_color=T["accent"],
                                 hover_color=T["accent_dim"])
        self._smart_caption_lbl.configure(text_color=T["muted"])
        self.status_label.configure(text_color=T["subtext"])
        self.ffmpeg_btn.configure(fg_color=T["card"], hover_color=T["hover"],
                                   text_color=T["primary"])
        self._stats_row.configure(fg_color=T["card"])
        self.thumb_label.configure(fg_color=T["card_inner"], text_color=T["muted"])
        self.frames_label.configure(text_color=T["label"])
        self.size_label.configure(text_color=T["muted"])
        # Refresh start button colors
        self._refresh_start_btn()
        self._update_status_guidance()

    def _close_all_tooltips(self):
        for tip in list(self._active_tooltips):
            try:
                tip.destroy()
            except Exception:
                pass
        self._active_tooltips.clear()
        self._tooltip_win = None

    @staticmethod
    def _make_cog_image(size=22, color=None):
        """Render a filled gear icon using PIL with 4× supersampling. Returns a CTkImage."""
        if color is None:
            color = T["accent"]
        scale = 4
        s = size * scale
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx, cy = s / 2, s / 2
        teeth = 8
        r_outer = s / 2 - 0.5
        r_inner = r_outer * 0.78
        r_hole  = r_outer * 0.31
        tooth_half = math.pi / teeth * 0.42
        points = []
        for i in range(teeth):
            base = 2 * math.pi * i / teeth
            for angle, r in (
                (base - tooth_half * 1.6, r_inner),
                (base - tooth_half,       r_outer),
                (base + tooth_half,       r_outer),
                (base + tooth_half * 1.6, r_inner),
            ):
                points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        draw.polygon(points, fill=color)
        draw.ellipse(
            [cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole],
            fill=(0, 0, 0, 0)
        )
        img = img.resize((size, size), Image.LANCZOS)
        return ctk.CTkImage(light_image=img, size=(size, size))

    def _bind_tooltip(self, widget, text):
        """Attach a small hover tooltip to any widget.
        *text* may be a plain string or a zero-arg callable that returns one."""
        tip = [None]

        def _poll():
            if not tip[0]:
                return
            try:
                mx = self.winfo_pointerx()
                my = self.winfo_pointery()
                wx = widget.winfo_rootx()
                wy = widget.winfo_rooty()
                ww = widget.winfo_width()
                wh = widget.winfo_height()
                if mx < wx or mx > wx + ww or my < wy or my > wy + wh:
                    _hide()
                    return
            except Exception:
                _hide()
                return
            self.after(50, _poll)

        def _show(*_):
            if tip[0]:
                return
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() - 30
            win = tk.Toplevel(self)
            win.overrideredirect(True)
            win.wm_attributes("-topmost", True)
            win.configure(bg=T["tooltip_bg"])
            win.geometry(f"+{x}+{y}")
            tk.Label(win, text=text() if callable(text) else text, font=("Arial", 10),
                     fg=T["tooltip_fg"], bg=T["tooltip_bg"],
                     padx=8, pady=4).pack()
            tip[0] = win
            self._active_tooltips.add(win)
            self.after(50, _poll)

        def _hide(*_):
            if tip[0]:
                self._active_tooltips.discard(tip[0])
                tip[0].destroy()
                tip[0] = None

        widget.bind("<Enter>", _show, add="+")

    def _update_status_guidance(self):
        """Update the status label and step colours to guide the user."""
        if self.is_recording:
            return
        if self._capture_target is None:
            self.status_label.configure(
                text=lang.t("status_step1"),
                text_color=T["subtext"])
            self._step_target_lbl.configure(text_color=T["accent"])
            self._step_project_lbl.configure(text_color=T["muted"])
        elif not self._current_project.strip():
            self.status_label.configure(
                text=lang.t("status_step3"),
                text_color=T["subtext"])
            self._step_target_lbl.configure(text_color="#55aa55")
            self._step_project_lbl.configure(text_color=T["accent"])
        else:
            self.status_label.configure(text=lang.t("status_ready"), text_color="gray")
            self._step_target_lbl.configure(text_color="#55aa55")
            self._step_project_lbl.configure(text_color="#55aa55")

    def _refresh_start_btn(self):
        """Enable or disable the START button based on required fields."""
        if self.is_recording:
            return
        ready = self._capture_target is not None and bool(self._current_project.strip())
        if ready:
            self.start_btn.configure(
                state="normal", fg_color=T["accent"], hover_color=T["accent_dim"],
                text_color="white")
        else:
            self.start_btn.configure(
                state="disabled", fg_color="#2a2a2a", hover_color="#2a2a2a",
                text_color=T["muted"])

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

        # When frozen, iconbitmap(sys.executable) lets Windows read the icon
        # directly from the exe's PE resources — sharp at all sizes.
        if getattr(sys, "frozen", False):
            self.iconbitmap(sys.executable)
        else:
            self.iconbitmap(self._ico_path)

    def _minimize(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        ctypes.windll.user32.ShowWindow(hwnd, 6)

    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show ArtLapse", self._tray_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._tray_quit),
        )
        icon_img = _make_app_icon(64)
        self._tray_icon = pystray.Icon("ArtLapse", icon_img, "ArtLapse", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _tray_show(self, icon=None, item=None):
        self.after(0, self._restore_window)

    def _restore_window(self):
        self.deiconify()
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)

    def _tray_quit(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
        self.after(0, self.destroy)

    def _hide_to_tray(self):
        self._close_all_tooltips()
        self.withdraw()

    def _quit_app(self):
        if self._tray_icon:
            self._tray_icon.stop()
        self.destroy()

    # ------------------------------------------------------------------ #
    #  CAPTURE TARGET PICKER                                               #
    # ------------------------------------------------------------------ #
    def _open_picker(self):
        WindowPickerPopup(self, self._capture_target, self._on_target_selected)

    # ------------------------------------------------------------------ #
    #  PROJECT PICKER                                                      #
    # ------------------------------------------------------------------ #
    def _open_project_picker(self):
        ProjectPickerPopup(
            self, self._current_project, self.base_path,
            on_select=self._on_project_selected,
            on_delete=self.delete_project,
        )

    def _on_project_selected(self, name: str):
        self._current_project = name
        display = (name[:32] + "…") if len(name) > 32 else name
        self._project_btn.configure(text=f"  {display}", text_color="white")
        self._load_project_preview()
        self._update_status_guidance()
        self._refresh_start_btn()

    def _load_project_preview(self):
        path = self._resolve_project_path()
        if not path or not os.path.exists(path):
            return
        pngs = sorted(f for f in os.listdir(path) if f.endswith(".png"))
        if not pngs:
            return
        self.final_path = path
        self.frames_label.configure(text=f"Frames: {len(pngs)}")
        avg_bytes = sum(os.path.getsize(os.path.join(path, f)) for f in pngs) / len(pngs)
        total_mb = avg_bytes * len(pngs) / 1_048_576
        self.size_label.configure(text=f"~{total_mb:.1f} MB")
        self._update_thumbnail(os.path.join(path, pngs[-1]))

    def _on_target_selected(self, target: dict):
        self._capture_target = target
        if target["type"] == "screen":
            name = target["name"]
        else:
            name = target["title"]
        display = (name[:32] + "…") if len(name) > 32 else name
        self._target_btn.configure(text=f"  {display}", text_color=T["primary"])
        self._update_status_guidance()
        self._refresh_start_btn()

    # ------------------------------------------------------------------ #
    #  EXPORT PANEL CONTROLS                                               #
    # ------------------------------------------------------------------ #
    def _draw_interval_marker(self, _event=None):
        c = self._interval_marker
        c.delete("all")
        w = c.winfo_width()
        if w < 10:
            return
        # Align with CTkSlider thumb: use its internal button radius if available
        try:
            pad = self.slider_interval._button_radius
        except AttributeError:
            pad = 10
        track_w = w - 2 * pad
        default_idx = config.load_default_interval_idx()
        total_steps = len(self.INTERVAL_STEPS) - 1
        x = pad + int(track_w * default_idx / total_steps)
        # Draw anti-aliased downward-pointing triangle via PIL supersampling
        tri_w, tri_h = 11, 9
        scale = 4
        sw, sh = tri_w * scale, tri_h * scale
        color = T["accent"]
        tri_img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        tri_draw = ImageDraw.Draw(tri_img)
        tri_draw.polygon(
            [(sw // 2, sh - 1), (0, 0), (sw - 1, 0)],
            fill=color,
        )
        tri_img = tri_img.resize((tri_w, tri_h), Image.LANCZOS)
        # Store on self to prevent GC
        self._marker_photo = ImageTk.PhotoImage(tri_img)
        c.create_image(x, 0, anchor="n", image=self._marker_photo)

    def _get_interval_seconds(self):
        idx = round(self.slider_interval.get())
        return self.INTERVAL_STEPS[idx]

    def _update_interval_label(self, val):
        idx = round(float(val))
        v = self.INTERVAL_STEPS[idx]
        text = f"{v:.1f} s" if v % 1 else f"{int(v)} s"
        self.label_interval.configure(text=text)

    def _open_export_popup(self):
        if self._export_popup and self._export_popup.winfo_exists():
            self._export_popup.focus()
            return
        self._export_popup = ExportPopup(
            self,
            on_export=self._on_export_requested,
            init_dur_idx=config.load_default_duration_idx(),
            init_qual_idx=config.load_default_export_quality_idx(),
        )

    def _on_export_requested(self, duration_secs, crf_preset, quality_label,
                             on_done_cb=None, on_progress_cb=None, on_success_cb=None, on_error_cb=None):
        self.compile_video(
            duration_secs=duration_secs,
            crf_preset=crf_preset,
            quality_label=quality_label,
            on_done_cb=on_done_cb,
            on_progress_cb=on_progress_cb,
            on_success_cb=on_success_cb,
            on_error_cb=on_error_cb,
        )

    # "Native" → ("png", None)   "High" → ("jpg", 92)   etc.
    _CAPTURE_QUALITY_MAP = {"High": ("png", None), "Med": ("jpg", 75), "Low": ("jpg", 55)}

    def _set_capture_quality(self, label: str):
        self._capture_quality_var.set(label)

    def _get_capture_quality(self):
        return self._CAPTURE_QUALITY_MAP[self._capture_quality_var.get()]

    # ------------------------------------------------------------------ #
    #  FOLDER / PROJECT HELPERS                                            #
    # ------------------------------------------------------------------ #
    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.base_path = path
            config.save_config(self.base_path)
            self.folder_label.configure(text="  📂  " + config.get_short_path(self.base_path))
            # project picker refreshes dynamically from base_path

    def open_output_folder(self):
        target = self.final_path if self.final_path and os.path.exists(self.final_path) else self.base_path
        if target and os.path.exists(target):
            os.startfile(target)
        else:
            self.status_label.configure(text=lang.t("status_no_folder"), text_color="orange")

    def delete_project(self, name: str = None, refresh_cb=None):
        if name is None:
            name = self._current_project
        name = name.strip()
        if not name or not self.base_path:
            self.status_label.configure(text=lang.t("status_no_project_del"), text_color="orange")
            if refresh_cb:
                refresh_cb()
            return

        target = os.path.join(self.base_path, name)
        if not os.path.exists(target):
            self.status_label.configure(text=lang.t("status_folder_not_found"), text_color="orange")
            if refresh_cb:
                refresh_cb()
            return

        if target == self.final_path and self.is_recording:
            self.status_label.configure(text=lang.t("status_cant_delete"), text_color="red")
            if refresh_cb:
                refresh_cb()
            return

        dialog = ctk.CTkToplevel(self)
        dialog.overrideredirect(True)
        dialog.configure(fg_color="#2a1a1a")
        dialog.resizable(False, False)
        dialog.wm_attributes("-topmost", True)

        dw, dh = 300, 160
        self.update_idletasks()
        cx = self.winfo_rootx() + (self.winfo_width()  - dw) // 2
        cy = self.winfo_rooty() + (self.winfo_height() - dh) // 2
        dialog.geometry(f"{dw}x{dh}+{cx}+{cy}")
        dialog.lift()
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=lang.t("dlg_del_title"),
                     font=("Arial Black", 13, "bold"),
                     text_color="#ff5555").pack(pady=(18, 4))
        ctk.CTkLabel(dialog,
                     text=lang.t("dlg_del_body", name=name),
                     font=("Arial", 11), text_color="gray").pack(pady=(0, 14))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20)

        def confirm():
            dialog.destroy()
            try:
                shutil.rmtree(target)
                if target == self.final_path:
                    self.stop_and_reset()
                elif name == self._current_project:
                    self._current_project = ""
                    self._project_btn.configure(
                        text=lang.t("project_placeholder_short"), text_color=T["subtext"]
                    )
                self.status_label.configure(text=lang.t("status_deleted", name=name), text_color="gray")
            except Exception as e:
                self.status_label.configure(text=lang.t("status_delete_failed", err=e), text_color="red")
            if refresh_cb:
                refresh_cb()

        def cancel():
            dialog.destroy()
            if refresh_cb:
                refresh_cb()

        ctk.CTkButton(btn_row, text=lang.t("btn_cancel"), fg_color=T["card"], hover_color=T["hover"],
                      command=cancel, width=110).pack(side="left")
        ctk.CTkButton(btn_row, text=lang.t("btn_delete"), fg_color="#5a2020", hover_color="#7a2a2a",
                      text_color="#ff5555", font=("Arial", 12, "bold"),
                      command=confirm, width=130).pack(side="right")


    # ------------------------------------------------------------------ #
    #  SIZE ESTIMATE + THUMBNAIL                                           #
    # ------------------------------------------------------------------ #
    def _resolve_project_path(self):
        name = self._current_project.strip()
        if not self.base_path or not name:
            return None
        return os.path.join(self.base_path, name)

    def _refresh_size_estimate(self):
        if not self.final_path or not os.path.exists(self.final_path):
            self.size_label.configure(text="—")
            return
        pngs = [f for f in os.listdir(self.final_path) if f.endswith(".png")]
        if not pngs:
            self.size_label.configure(text="—")
            return
        avg_bytes = sum(
            os.path.getsize(os.path.join(self.final_path, f)) for f in pngs
        ) / len(pngs)
        total_mb = avg_bytes * len(pngs) / 1_048_576
        self.size_label.configure(text=f"~{total_mb:.1f} MB")

    def _update_thumbnail(self, img_path: str):
        try:
            img = Image.open(img_path)
            self._thumb_photo = ctk.CTkImage(light_image=img, size=(72, 50))
            self.thumb_label.configure(image=self._thumb_photo, text="")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  CAPTURE                                                             #
    # ------------------------------------------------------------------ #
    def toggle_capture(self):
        if not self.is_recording:
            if self._capture_target is None:
                self.status_label.configure(text=lang.t("status_no_target"), text_color="red")
                return

            path = self._resolve_project_path()
            if not path:
                self.status_label.configure(text=lang.t("status_no_project_rec"), text_color="red")
                return

            self.final_path = path
            os.makedirs(self.final_path, exist_ok=True)
            existing = [f for f in os.listdir(self.final_path)
                        if f.lower().endswith((".png", ".jpg", ".jpeg"))]
            self.count = len(existing) + 1
            self.frames_label.configure(text=lang.t("frames_n", n=len(existing)))

            self.is_recording = True
            self._identical_streak = 0; self._prev_thumb_bytes = None
            self.start_btn.configure(
                state="normal", text=lang.t("btn_pause"), fg_color=T["hover"], hover_color="#444444",
                text_color="white")
            self.stop_btn.pack_forget()
            self.status_label.configure(text=lang.t("status_recording", n=self.count), text_color=T["accent"])
            self.warn_label.configure(text="")
            self.capture_loop()
        else:
            self.is_recording = False
            self._identical_streak = 0; self._prev_thumb_bytes = None
            if self.after_id:
                self.after_cancel(self.after_id)
                self.after_id = None
            self.start_btn.configure(
                state="normal", text=lang.t("btn_resume"), fg_color=T["accent"], hover_color=T["accent_dim"],
                text_color="white")
            self.stop_btn.pack(side="left", padx=(6, 0))
            self.status_label.configure(text=lang.t("btn_paused_hint"), text_color="orange")

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
        self._frame_hashes.clear()
        self.stop_btn.pack_forget()
        if self.auto_compile_var.get() and export_path:
            self.status_label.configure(text=lang.t("status_exporting"), text_color="gray")
        self.warn_label.configure(text="")
        self.frames_label.configure(text=lang.t("frames_zero"))
        self.size_label.configure(text="—")
        self.thumb_label.configure(image="", text=lang.t("thumb_no_preview"))
        self._thumb_photo = None
        self._current_project = ""
        self._project_btn.configure(text=lang.t("project_placeholder"), text_color=T["subtext"])
        self._update_status_guidance()
        self._refresh_start_btn()

    def capture_loop(self):
        if not self.is_recording:
            return

        interval_ms = int(self._get_interval_seconds() * 1000)
        fmt, jpeg_q = self._get_capture_quality()
        save_path   = os.path.join(self.final_path, f"shot_{self.count:04d}.{fmt}")

        if self.smart_capture_var.get():
            img, warning = capture.capture_frame_raw(self._capture_target)
            captured = False
            if img is not None:
                thumb_bytes = img.resize((32, 32)).convert("L").tobytes()
                prev = getattr(self, "_prev_thumb_bytes", None)

                if prev is not None:
                    # mean absolute difference across the 32×32 grayscale thumbnail
                    diff = sum(abs(a - b) for a, b in zip(thumb_bytes, prev)) / 1024
                    same = diff < 0.2  # threshold: avg pixel change < 0.2/255
                else:
                    same = False

                if same:
                    self._identical_streak = getattr(self, "_identical_streak", 0) + 1
                else:
                    self._identical_streak = 0

                # Only advance the baseline while not paused — this way the paused
                # frame acts as an anchor, so any meaningful change from it is
                # detected even if the transition happens gradually frame-by-frame.
                if self._identical_streak < 4:
                    self._prev_thumb_bytes = thumb_bytes

                if self._identical_streak >= 4:   # 5th identical frame → pause
                    self.warn_label.configure(text="")
                    self.status_label.configure(
                        text=lang.t("status_smart_pause", n=self.count - 1), text_color=T["muted"]
                    )
                    self.after_id = self.after(interval_ms, self.capture_loop)
                    return

                rgb = img.convert("RGB")
                if jpeg_q is not None:
                    rgb.save(save_path, "JPEG", quality=jpeg_q)
                else:
                    rgb.save(save_path)
                captured = True
        else:
            captured, warning = capture.capture_frame(self._capture_target, save_path,
                                                      jpeg_quality=jpeg_q)

        self.warn_label.configure(text=warning)
        if captured:
            self.status_label.configure(
                text=lang.t("status_recording", n=self.count), text_color=T["accent"]
            )
            self.frames_label.configure(text=lang.t("frames_n", n=self.count))
            self.count += 1
            self._update_thumbnail(save_path)
            self._refresh_size_estimate()

        self.after_id = self.after(interval_ms, self.capture_loop)

    # ------------------------------------------------------------------ #
    #  EXPORT                                                              #
    # ------------------------------------------------------------------ #
    def compile_video(self, path_override=None,
                      duration_secs=None, crf_preset=None,
                      quality_label=None, on_done_cb=None,
                      on_progress_cb=None, on_success_cb=None, on_error_cb=None):
        path = path_override or self._resolve_project_path() or self.final_path
        if not path or not os.path.exists(path):
            self.status_label.configure(text=lang.t("status_select_export"), text_color="orange")
            return

        pngs = sorted(
            [f for f in os.listdir(path) if f.lower().endswith((".png", ".jpg", ".jpeg"))],
            key=lambda x: x.lower()
        )
        if not pngs:
            self.status_label.configure(text=lang.t("status_no_frames"), text_color="red")
            return

        if getattr(sys, "frozen", False):
            _ffmpeg_ok = os.path.isfile(os.path.join(sys._MEIPASS, "ffmpeg.exe"))
        else:
            _ffmpeg_ok = bool(shutil.which("ffmpeg"))
        if not _ffmpeg_ok:
            self.status_label.configure(text=lang.t("status_no_ffmpeg"), text_color="red")
            return

        # Fall back to defaults when called from auto-export (no popup params)
        if crf_preset is None:
            crf, preset = 23, "medium"
        else:
            crf, preset = crf_preset
        if quality_label is None:
            quality_label = "Balanced"

        duration_sec = duration_secs
        n = len(pngs)

        if duration_sec is None:
            fps     = 24.0
            dur_str = "Realtime (24fps)"
        else:
            fps     = round(max(n / duration_sec, 0.1), 4)
            mins, s = divmod(duration_sec, 60)
            dur_str = f"{mins}m{s}s" if mins else f"{duration_sec}s"

        self.status_label.configure(text=f"Exporting {n} frames at {fps:.2f} fps…", text_color="gray")
        self.ffmpeg_btn.configure(state="disabled")

        def on_done(size_mb, out_path):
            msg = f"Exported ✓  {n} frames · {dur_str} · {size_mb:.1f} MB"
            self.after(0, lambda: self.status_label.configure(text=msg, text_color=T["accent"]))
            if on_success_cb:
                self.after(0, lambda: on_success_cb(out_path))
            else:
                self.after(0, lambda: os.startfile(out_path))
            if on_done_cb:
                on_done_cb()

        def on_error(msg):
            self.after(0, lambda: self.status_label.configure(text=msg, text_color="red"))
            if on_error_cb:
                self.after(0, lambda: on_error_cb(msg))
            if on_done_cb:
                on_done_cb()

        def on_finally():
            self.after(0, lambda: self.ffmpeg_btn.configure(state="normal"))

        def on_progress(fraction):
            if on_progress_cb:
                self.after(0, lambda f=fraction: on_progress_cb(f))

        project_name = self._current_project or os.path.basename(path)
        export.run_export(path, pngs, fps, crf, preset, on_done, on_error, on_finally,
                          project_name=project_name, quality_label=quality_label,
                          on_progress=on_progress)


if __name__ == "__main__":
    app = ArtLapseApp()
    _launch = config.load_launch_behavior()
    if _launch == "minimized":
        app.after(100, app._minimize)
    elif _launch == "tray":
        app.after(100, app._hide_to_tray)
    app.mainloop()
