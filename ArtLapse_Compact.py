import customtkinter as ctk
import ctypes
import os
import re
import shutil
import threading
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageDraw
import pystray

import config
import capture
import export
from constants import (
    ORANGE_THEME, ORANGE_DIM, BG_COLOR, CARD_COLOR, APP_W, APP_H
)


def _make_app_icon(size=64) -> Image.Image:
    """Create an orange rounded-rectangle icon with a white 'A' centered."""
    from PIL import ImageFont
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    r   = size // 6
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=(232, 92, 37, 255))

    # Draw white "A" centered
    font_size = int(size * 0.55)
    font = None
    for font_path in [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    bbox = d.textbbox((0, 0), "A", font=font)
    tx = (size - (bbox[2] - bbox[0])) // 2 - bbox[0]
    ty = (size - (bbox[3] - bbox[1])) // 2 - bbox[1]
    d.text((tx, ty), "A", fill=(255, 255, 255, 255), font=font)
    return img

ctk.set_appearance_mode("dark")


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
        self.configure(fg_color=BG_COLOR)
        self.wm_attributes("-topmost", True)

        self._on_select  = on_select
        self._cur_target = current_target
        self._card_data  = []       # list of (card_frame, info_dict)
        self._drag_ox    = 0
        self._drag_oy    = 0

        # Center on parent
        px = parent.winfo_x() + (APP_W       - self._POPUP_W) // 2
        py = parent.winfo_y() + max(0, (APP_H - self._POPUP_H) // 2)
        self.geometry(f"{self._POPUP_W}x{self._POPUP_H}+{px}+{py}")

        self._build_ui()
        self.after(20, self._apply_round)
        self.grab_set()

        threading.Thread(target=self._load_data, daemon=True).start()

    def _apply_round(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        rgn  = ctypes.windll.gdi32.CreateRoundRectRgn(
            0, 0, self._POPUP_W, self._POPUP_H, 14, 14)
        ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Title bar
        tbar = ctk.CTkFrame(self, fg_color=CARD_COLOR, height=42, corner_radius=0)
        tbar.pack(fill="x")
        tbar.pack_propagate(False)
        tbar.bind("<Button-1>",  self._drag_start)
        tbar.bind("<B1-Motion>", self._drag_move)

        ctk.CTkLabel(
            tbar, text="SELECT CAPTURE TARGET",
            font=("Arial", 10, "bold"), text_color="#666666",
        ).place(relx=0.5, rely=0.5, anchor="center")

        btn_area = ctk.CTkFrame(tbar, fg_color="transparent")
        btn_area.place(relx=1.0, rely=0.5, anchor="e", x=-6)

        ctk.CTkButton(
            btn_area, text="↺", width=30, height=30,
            fg_color="transparent", hover_color="#333333",
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
            scrollbar_button_color="#333333",
            scrollbar_button_hover_color="#555555",
        )
        self._scroll.pack(fill="both", expand=True)

        self._status_lbl = ctk.CTkLabel(
            self._scroll, text="Loading…",
            font=("Arial", 11), text_color="#555555",
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
            self._scroll, text="Loading…",
            font=("Arial", 11), text_color="#555555",
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
            screens_wrap, text="SCREENS",
            font=("Arial", 9, "bold"), text_color="#555555", anchor="w",
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
            apps_wrap, text="APPLICATIONS",
            font=("Arial", 9, "bold"), text_color="#555555", anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        if not windows:
            ctk.CTkLabel(apps_wrap, text="No visible windows found.",
                         font=("Arial", 10), text_color="#555555").pack()
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
            fg_color=CARD_COLOR, corner_radius=8,
            border_width=2,
            border_color=ORANGE_THEME if selected else "#2d3133",
        )
        card.pack_propagate(False)

        # Thumbnail placeholder
        thumb_lbl = ctk.CTkLabel(
            card, text="", image=None,
            width=self._THUMB_W, height=self._THUMB_H,
            fg_color="#161819", corner_radius=6,
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
            font=("Arial", 9), text_color="#cccccc", anchor="w",
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
                    card.configure(border_color="#2d3133")
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
        self.configure(fg_color=BG_COLOR)
        self.wm_attributes("-topmost", True)

        self._on_select = on_select
        self._on_delete = on_delete
        self._current   = current_project
        self._base_path = base_path
        self._drag_ox   = 0
        self._drag_oy   = 0

        px = parent.winfo_x() + (APP_W       - self._POPUP_W) // 2
        py = parent.winfo_y() + max(0, (APP_H - self._POPUP_H) // 2)
        self.geometry(f"{self._POPUP_W}x{self._POPUP_H}+{px}+{py}")

        self._build_ui()
        self.after(20, self._apply_round)
        self.grab_set()
        self.after(60, self._name_entry.focus)

    def _apply_round(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        rgn  = ctypes.windll.gdi32.CreateRoundRectRgn(
            0, 0, self._POPUP_W, self._POPUP_H, 14, 14)
        ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)

    def _build_ui(self):
        # Title bar
        tbar = ctk.CTkFrame(self, fg_color=CARD_COLOR, height=42, corner_radius=0)
        tbar.pack(fill="x")
        tbar.pack_propagate(False)
        tbar.bind("<Button-1>",  self._drag_start)
        tbar.bind("<B1-Motion>", self._drag_move)

        ctk.CTkLabel(
            tbar, text="SELECT PROJECT",
            font=("Arial", 10, "bold"), text_color="#666666",
        ).place(relx=0.5, rely=0.5, anchor="center")

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
            new_section, text="NEW PROJECT",
            font=("Arial", 9, "bold"), text_color="#555555", anchor="w",
        ).pack(anchor="w", pady=(0, 4))

        entry_row = ctk.CTkFrame(new_section, fg_color="transparent")
        entry_row.pack(fill="x")

        self._name_entry = ctk.CTkEntry(
            entry_row, height=34,
            placeholder_text="type a new project name…",
            font=("Arial", 11), fg_color=CARD_COLOR,
        )
        self._name_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._name_entry.bind("<Return>", lambda e: self._confirm_new())

        ctk.CTkButton(
            entry_row, text="✓", width=34, height=34,
            fg_color=ORANGE_THEME, hover_color=ORANGE_DIM,
            font=("Arial", 13, "bold"),
            command=self._confirm_new,
        ).pack(side="left")

        # Existing projects section
        ctk.CTkLabel(
            self, text="EXISTING PROJECTS",
            font=("Arial", 9, "bold"), text_color="#555555", anchor="w",
        ).pack(anchor="w", padx=self._PAD, pady=(10, 0))

        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color="#333333",
            scrollbar_button_hover_color="#555555",
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
                self._scroll, text="No existing projects.",
                font=("Arial", 10), text_color="#555555",
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
            fg_color=CARD_COLOR, corner_radius=8,
            border_width=2,
            border_color=ORANGE_THEME if selected else "#2d3133",
            height=50,
        )
        row.pack(fill="x", pady=(0, 6))
        row.pack_propagate(False)

        # Folder icon area
        icon_area = ctk.CTkFrame(row, fg_color="#1a1d1f", corner_radius=6, width=36, height=36)
        icon_area.pack(side="left", padx=(7, 0), pady=7)
        icon_area.pack_propagate(False)
        ctk.CTkLabel(
            icon_area, text="📁", font=("Arial", 14), fg_color="transparent",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Name + frame count
        info_col = ctk.CTkFrame(row, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=6)

        ctk.CTkLabel(
            info_col, text=name,
            font=("Arial", 10, "bold"), text_color="#dddddd", anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            info_col,
            text=f"{frame_count} frame{'s' if frame_count != 1 else ''}",
            font=("Arial", 9), text_color="#555555", anchor="w",
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
            fg_color="transparent", hover_color=ORANGE_DIM,
            font=("Arial", 14, "bold"), text_color=ORANGE_THEME,
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
                    row.configure(border_color="#2d3133")
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
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════

class ArtLapseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.overrideredirect(True)
        self.geometry(f"{APP_W}x{APP_H}")
        self.configure(fg_color=BG_COLOR)
        self.update_idletasks()
        import sys
        _base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        self._ico_path = os.path.join(_base, "artlapse.ico")
        self.after(20, self._setup_taskbar_presence)
        self.after(20, self.apply_round_region)

        # System tray
        self._tray_icon = None
        self._setup_tray()

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

        _min_btn = ctk.CTkButton(btn_frame, text="—", width=34, height=34,
                      fg_color="transparent", hover_color="#333333",
                      font=("Arial", 15, "bold"),
                      corner_radius=8, command=self._minimize)
        _min_btn.pack(side="left", padx=2)
        self._bind_tooltip(_min_btn, "Minimize")

        _tray_btn = ctk.CTkButton(btn_frame, text="⬛", width=34, height=34,
                      fg_color="transparent", hover_color="#333333",
                      font=("Arial", 11), text_color=ORANGE_THEME,
                      corner_radius=8, command=self._hide_to_tray)
        _tray_btn.pack(side="left", padx=2)
        self._bind_tooltip(_tray_btn, "Hide to system tray")

        _close_btn = ctk.CTkButton(btn_frame, text="✕", width=34, height=34,
                      fg_color="transparent", hover_color="#c42b1c",
                      font=("Arial", 15, "bold"),
                      corner_radius=8, command=self._quit_app)
        _close_btn.pack(side="left", padx=2)
        self._bind_tooltip(_close_btn, "Quit ArtLapse")

        for widget in (hdr,):
            widget.bind("<Button-1>",  self._click_window)
            widget.bind("<B1-Motion>", self._drag_window)

        # ── BODY ────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        # Capture target picker
        self._step_target_lbl = self._section_label(body, "1 · Capture Target")
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", pady=(2, 0))

        self._target_btn = ctk.CTkButton(
            row1,
            text="  Click to select a window or screen…",
            height=34, anchor="w",
            fg_color=CARD_COLOR, hover_color="#333333",
            font=("Arial", 12), text_color="#666666",
            corner_radius=6,
            command=self._open_picker,
        )
        self._target_btn.pack(fill="x")

        # Folder picker
        self._section_label(body, "2 · Output Folder")
        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=(2, 0))
        self.folder_label = ctk.CTkLabel(row2, text=config.get_short_path(self.base_path),
                                         font=("Arial", 12), text_color="gray",
                                         anchor="w")
        self.folder_label.pack(side="left", fill="x", expand=True)
        _browse_btn = ctk.CTkButton(row2, text="📁", width=44, height=34,
                      fg_color=CARD_COLOR, hover_color="#333333",
                      font=("Arial", 16),
                      command=self.choose_folder)
        _browse_btn.pack(side="left", padx=(6, 0))
        self._bind_tooltip(_browse_btn, "Browse for output folder")
        _open_btn = ctk.CTkButton(row2, text="▲", width=38, height=34,
                      fg_color=CARD_COLOR, hover_color=ORANGE_DIM,
                      font=("Arial", 17, "bold"), text_color=ORANGE_THEME,
                      command=self.open_output_folder)
        _open_btn.pack(side="left", padx=(4, 0))
        self._bind_tooltip(_open_btn, "Open folder in Explorer")

        # Project name
        self._step_project_lbl = self._section_label(body, "3 · Project Name")
        proj_row = ctk.CTkFrame(body, fg_color="transparent")
        proj_row.pack(fill="x", pady=(2, 0))

        self._project_btn = ctk.CTkButton(
            proj_row,
            text="  Click to name or pick a project…",
            height=34, anchor="w",
            fg_color=CARD_COLOR, hover_color="#333333",
            font=("Arial", 12), text_color="#666666",
            corner_radius=6,
            command=self._open_project_picker,
        )
        self._project_btn.pack(fill="x")

        # Interval slider
        self._section_label(body, "4 · Capture Interval")
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
        self.slider_interval.pack(fill="x", pady=(0, 4))

        # Smart Capture toggle
        smart_row = ctk.CTkFrame(body, fg_color="transparent")
        smart_row.pack(fill="x", pady=(0, 4))
        self.smart_capture_var = ctk.BooleanVar(value=True)
        self._smart_cb = ctk.CTkCheckBox(
            smart_row, text="Smart Capture",
            variable=self.smart_capture_var,
            font=("Arial", 12),
            text_color="#aaaaaa",
            checkbox_width=16, checkbox_height=16,
            checkmark_color="white",
            fg_color=ORANGE_THEME, hover_color=ORANGE_DIM,
            border_color="#555555",
        )
        self._smart_cb.pack(side="left")
        self._smart_cb.bind("<Enter>", self._show_smart_tooltip)
        self._smart_cb.bind("<Leave>", self._hide_smart_tooltip)
        ctk.CTkLabel(smart_row, text="— skips saving identical frames",
                     font=("Arial", 10), text_color="#555555").pack(side="left", padx=(6, 0))

        # Status / guidance
        self.status_label = ctk.CTkLabel(body, text="▲ Step 1 — pick a capture target to begin",
                                         font=("Arial", 13, "bold"),
                                         text_color="#666666")
        self.status_label.pack(pady=(2, 4))

        # Start / stop buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 4))

        self.start_btn = ctk.CTkButton(
            btn_row, text="START", fg_color="#2a2a2a",
            hover_color="#2a2a2a", text_color="#555555",
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
            export_header, text="▶  Export Timelapse MP4",
            fg_color=CARD_COLOR, hover_color="#333333",
            font=("Arial", 13, "bold"),
            height=38, command=self.compile_video
        )
        self.ffmpeg_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._export_collapsed = True
        self.collapse_btn = ctk.CTkButton(
            export_header, text="▼", width=38, height=38,
            fg_color=CARD_COLOR, hover_color="#333333",
            font=("Arial", 13, "bold"), text_color="gray",
            command=self._toggle_export_panel
        )
        self.collapse_btn.pack(side="left")

        # Collapsible export options card (hidden on start)
        self.export_card = ctk.CTkFrame(body, fg_color=CARD_COLOR, corner_radius=10)

        # ── Two-column layout: thumbnail left, settings right ────────────
        self._dur_snaps  = [15, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600, None]
        self._dur_labels = ["15s", "30s", "45s", "1m", "1m30s",
                            "2m", "3m", "4m", "5m", "7m", "10m", "Realtime"]

        cols = ctk.CTkFrame(self.export_card, fg_color="transparent")
        cols.pack(fill="x", padx=8, pady=(8, 8))

        # Left column — thumbnail + stats
        left_col = ctk.CTkFrame(cols, fg_color="transparent", width=76)
        left_col.pack(side="left", fill="y", padx=(0, 8))
        left_col.pack_propagate(False)

        self.thumb_label = ctk.CTkLabel(left_col, text="no\npreview",
                                        width=72, height=50,
                                        font=("Arial", 8), text_color="#555555",
                                        fg_color="#1a1d1f", corner_radius=6)
        self.thumb_label.pack()

        self.frames_label = ctk.CTkLabel(left_col, text="Frames: 0",
                                         font=("Arial", 11), text_color="gray",
                                         wraplength=72, justify="center")
        self.frames_label.pack(pady=(3, 0))

        self.size_label = ctk.CTkLabel(left_col, text="—",
                                       font=("Arial", 11), text_color="#555555",
                                       wraplength=72, justify="center")
        self.size_label.pack(pady=(1, 0))

        self.warn_label = ctk.CTkLabel(left_col, text="",
                                       font=("Arial", 11), text_color="orange",
                                       wraplength=72, justify="center")
        self.warn_label.pack(pady=(1, 0))

        # Right column — export settings
        right_col = ctk.CTkFrame(cols, fg_color="transparent")
        right_col.pack(side="left", fill="both", expand=True)

        # Auto-export toggle
        top_row = ctk.CTkFrame(right_col, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(top_row, text="Auto-export on Stop",
                     font=("Arial", 13), anchor="w").pack(side="left")
        self.auto_compile_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(top_row, text="", variable=self.auto_compile_var,
                      width=40, button_color=ORANGE_THEME,
                      progress_color=ORANGE_DIM).pack(side="right")

        # Duration
        dur_row = ctk.CTkFrame(right_col, fg_color="transparent")
        dur_row.pack(fill="x")
        ctk.CTkLabel(dur_row, text="Duration",
                     font=("Arial", 13), anchor="w").pack(side="left")
        self.duration_val_label = ctk.CTkLabel(
            dur_row, text="30s",
            font=("Arial", 13, "underline"),
            text_color=ORANGE_THEME, cursor="hand2"
        )
        self.duration_val_label.pack(side="right")
        self.duration_val_label.bind("<Button-1>", self._open_duration_entry)

        self.duration_slider = ctk.CTkSlider(
            right_col,
            from_=0, to=len(self._dur_snaps) - 1,
            number_of_steps=len(self._dur_snaps) - 1,
            button_color=ORANGE_THEME,
            progress_color=ORANGE_THEME,
            command=self._on_duration_slide
        )
        self.duration_slider.set(1)
        self.duration_slider.pack(fill="x", pady=(2, 0))

        dur_hints = ctk.CTkFrame(right_col, fg_color="transparent")
        dur_hints.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(dur_hints, text="15 sec", font=("Arial", 11),
                     text_color="#444444").pack(side="left")
        ctk.CTkLabel(dur_hints, text="Realtime", font=("Arial", 11),
                     text_color="#444444").pack(side="right")

        self._dur_entry_frame = ctk.CTkFrame(right_col, fg_color="transparent")
        self.duration_entry = ctk.CTkEntry(
            self._dur_entry_frame, height=28,
            placeholder_text='e.g. "1.5" or "2m30s"',
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

        # Quality
        q_row = ctk.CTkFrame(right_col, fg_color="transparent")
        q_row.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(q_row, text="Quality",
                     font=("Arial", 13), anchor="w").pack(side="left")
        self.quality_val_label = ctk.CTkLabel(q_row, text="Balanced",
                                              font=("Arial", 12), text_color="gray")
        self.quality_val_label.pack(side="right")

        self.quality_slider = ctk.CTkSlider(
            right_col, from_=0, to=4,
            number_of_steps=4,
            button_color=ORANGE_THEME,
            progress_color=ORANGE_THEME,
            command=self._update_quality_label
        )
        self.quality_slider.set(2)
        self.quality_slider.pack(fill="x", pady=(2, 0))

        q_hints = ctk.CTkFrame(right_col, fg_color="transparent")
        q_hints.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(q_hints, text="Smallest", font=("Arial", 11),
                     text_color="#444444").pack(side="left")
        ctk.CTkLabel(q_hints, text="Highest", font=("Arial", 11),
                     text_color="#444444").pack(side="right")

        # Shrink window to collapsed height on first draw
        self.after(30, self._init_collapsed_height)

    def _init_collapsed_height(self):
        self.update_idletasks()
        new_h = self.winfo_reqheight()
        self.geometry(f"{APP_W}x{new_h}")
        self.after(10, lambda: self.apply_round_region(APP_W, new_h))

    # ------------------------------------------------------------------ #
    #  UI HELPERS                                                          #
    # ------------------------------------------------------------------ #
    def _section_label(self, parent, text):
        lbl = ctk.CTkLabel(parent, text=text,
                           font=("Arial", 11, "bold"),
                           text_color="#555555", anchor="w")
        lbl.pack(anchor="w", pady=(6, 0))
        return lbl

    def _show_smart_tooltip(self, event=None):
        if self._tooltip_win:
            return
        x = self._smart_cb.winfo_rootx()
        y = self._smart_cb.winfo_rooty() - 52
        self._tooltip_win = tk.Toplevel(self)
        self._tooltip_win.overrideredirect(True)
        self._tooltip_win.wm_attributes("-topmost", True)
        self._tooltip_win.configure(bg="#2a2d2f")
        self._tooltip_win.geometry(f"+{x}+{y}")
        tk.Label(
            self._tooltip_win,
            text="Skips saving a frame if the screen\nhasn't changed for 5 consecutive shots.",
            font=("Arial", 11),
            fg="#cccccc",
            bg="#2a2d2f",
            justify="left",
        ).pack(padx=10, pady=6)
        self._active_tooltips.add(self._tooltip_win)
        self.after(50, self._poll_smart_tooltip)

    def _poll_smart_tooltip(self):
        if not self._tooltip_win:
            return
        try:
            mx = self.winfo_pointerx()
            my = self.winfo_pointery()
            wx = self._smart_cb.winfo_rootx()
            wy = self._smart_cb.winfo_rooty()
            ww = self._smart_cb.winfo_width()
            wh = self._smart_cb.winfo_height()
            if mx < wx or mx > wx + ww or my < wy or my > wy + wh:
                self._hide_smart_tooltip()
                return
        except Exception:
            self._hide_smart_tooltip()
            return
        self.after(50, self._poll_smart_tooltip)

    def _hide_smart_tooltip(self, event=None):
        if self._tooltip_win:
            self._active_tooltips.discard(self._tooltip_win)
            self._tooltip_win.destroy()
            self._tooltip_win = None

    def _close_all_tooltips(self):
        for tip in list(self._active_tooltips):
            try:
                tip.destroy()
            except Exception:
                pass
        self._active_tooltips.clear()
        self._tooltip_win = None

    def _bind_tooltip(self, widget, text: str):
        """Attach a small hover tooltip to any widget."""
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
            win.configure(bg="#2a2d2f")
            win.geometry(f"+{x}+{y}")
            tk.Label(win, text=text, font=("Arial", 10),
                     fg="#cccccc", bg="#2a2d2f",
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
                text="▲ Step 1 — pick a capture target to begin",
                text_color="#666666")
            self._step_target_lbl.configure(text_color="#cc7733")
            self._step_project_lbl.configure(text_color="#555555")
        elif not self._current_project.strip():
            self.status_label.configure(
                text="▲ Step 3 — name your project to continue",
                text_color="#666666")
            self._step_target_lbl.configure(text_color="#55aa55")
            self._step_project_lbl.configure(text_color="#cc7733")
        else:
            self.status_label.configure(text="Ready — press START", text_color="gray")
            self._step_target_lbl.configure(text_color="#55aa55")
            self._step_project_lbl.configure(text_color="#55aa55")

    def _refresh_start_btn(self):
        """Enable or disable the START button based on required fields."""
        if self.is_recording:
            return
        ready = self._capture_target is not None and bool(self._current_project.strip())
        if ready:
            self.start_btn.configure(
                state="normal", fg_color=ORANGE_THEME, hover_color=ORANGE_DIM,
                text_color="white")
        else:
            self.start_btn.configure(
                state="disabled", fg_color="#2a2a2a", hover_color="#2a2a2a",
                text_color="#555555")

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
        import sys
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
        self._target_btn.configure(text=f"  {display}", text_color="white")
        self._update_status_guidance()
        self._refresh_start_btn()

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
    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.base_path = path
            config.save_config(self.base_path)
            self.folder_label.configure(text=config.get_short_path(self.base_path))
            # project picker refreshes dynamically from base_path

    def open_output_folder(self):
        target = self.final_path if self.final_path and os.path.exists(self.final_path) else self.base_path
        if target and os.path.exists(target):
            os.startfile(target)
        else:
            self.status_label.configure(text="No folder to open", text_color="orange")

    def delete_project(self, name: str = None, refresh_cb=None):
        if name is None:
            name = self._current_project
        name = name.strip()
        if not name or not self.base_path:
            self.status_label.configure(text="No project selected to delete", text_color="orange")
            if refresh_cb:
                refresh_cb()
            return

        target = os.path.join(self.base_path, name)
        if not os.path.exists(target):
            self.status_label.configure(text="Folder not found", text_color="orange")
            if refresh_cb:
                refresh_cb()
            return

        if target == self.final_path and self.is_recording:
            self.status_label.configure(text="Can't delete — currently recording", text_color="red")
            if refresh_cb:
                refresh_cb()
            return

        dialog = ctk.CTkToplevel(self)
        dialog.overrideredirect(True)
        dialog.configure(fg_color="#2a1a1a")
        dialog.resizable(False, False)
        dialog.wm_attributes("-topmost", True)

        dw, dh = 300, 160
        cx = self.winfo_x() + (APP_W - dw) // 2
        cy = self.winfo_y() + (APP_H - dh) // 2
        dialog.geometry(f"{dw}x{dh}+{cx}+{cy}")
        dialog.lift()
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
                elif name == self._current_project:
                    self._current_project = ""
                    self._project_btn.configure(
                        text="  type new or pick existing…", text_color="#666666"
                    )
                self.status_label.configure(text=f'"{name}" deleted', text_color="gray")
            except Exception as e:
                self.status_label.configure(text=f"Delete failed: {e}", text_color="red")
            if refresh_cb:
                refresh_cb()

        def cancel():
            dialog.destroy()
            if refresh_cb:
                refresh_cb()

        ctk.CTkButton(btn_row, text="Cancel", fg_color=CARD_COLOR, hover_color="#333333",
                      command=cancel, width=110).pack(side="left")
        ctk.CTkButton(btn_row, text="🗑  Delete", fg_color="#5a2020", hover_color="#7a2a2a",
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
                self.status_label.configure(text="Select a capture target first", text_color="red")
                return

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
            self._identical_streak = 0; self._prev_thumb_bytes = None
            self.start_btn.configure(
                state="normal", text="⏸  PAUSE", fg_color="#333333", hover_color="#444444",
                text_color="white")
            self.stop_btn.pack_forget()
            self.status_label.configure(text=f"Recording — frame {self.count}", text_color=ORANGE_THEME)
            self.warn_label.configure(text="")
            self.capture_loop()
        else:
            self.is_recording = False
            self._identical_streak = 0; self._prev_thumb_bytes = None
            if self.after_id:
                self.after_cancel(self.after_id)
                self.after_id = None
            self.start_btn.configure(
                state="normal", text="▶  RESUME", fg_color=ORANGE_THEME, hover_color=ORANGE_DIM,
                text_color="white")
            self.stop_btn.pack(side="left", padx=(6, 0))
            self.status_label.configure(text="Paused — press ▶ to resume or ⏹ to stop", text_color="orange")

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
            self.status_label.configure(text="Exporting…", text_color="gray")
        self.warn_label.configure(text="")
        self.frames_label.configure(text="Frames: 0")
        self.size_label.configure(text="—")
        self.thumb_label.configure(image="", text="no preview")
        self._thumb_photo = None
        self._current_project = ""
        self._project_btn.configure(text="  Click to name or pick a project…", text_color="#666666")
        self._update_status_guidance()
        self._refresh_start_btn()

    def capture_loop(self):
        if not self.is_recording:
            return

        interval_ms = int(float(self.slider_interval.get()) * 1000)
        save_path   = os.path.join(self.final_path, f"shot_{self.count:04d}.png")

        if self.smart_capture_var.get():
            img, warning = capture.capture_frame_raw(self._capture_target)
            captured = False
            if img is not None:
                import struct
                thumb_bytes = img.resize((32, 32)).convert("L").tobytes()
                prev = getattr(self, "_prev_thumb_bytes", None)
                self._prev_thumb_bytes = thumb_bytes

                if prev is not None:
                    # mean absolute difference across the 32×32 grayscale thumbnail
                    diff = sum(abs(a - b) for a, b in zip(thumb_bytes, prev)) / 1024
                    same = diff < 4.0  # threshold: avg pixel change < 4/255
                else:
                    same = False

                if same:
                    self._identical_streak = getattr(self, "_identical_streak", 0) + 1
                else:
                    self._identical_streak = 0

                if self._identical_streak >= 4:   # 5th identical frame → pause
                    self.warn_label.configure(text="")
                    self.status_label.configure(
                        text=f"Smart pause — frame {self.count - 1}", text_color="#555555"
                    )
                    self.after_id = self.after(interval_ms, self.capture_loop)
                    return

                img.convert("RGB").save(save_path)
                captured = True
        else:
            captured, warning = capture.capture_frame(self._capture_target, save_path)

        self.warn_label.configure(text=warning)
        if captured:
            self.status_label.configure(
                text=f"Recording — frame {self.count}", text_color=ORANGE_THEME
            )
            self.frames_label.configure(text=f"Frames: {self.count}")
            self.count += 1
            self._update_thumbnail(save_path)
            self._refresh_size_estimate()

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
