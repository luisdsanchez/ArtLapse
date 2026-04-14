"""
Update popup demo — previews all update UI states without any network calls.
"""

import time
import threading
import ctypes
import customtkinter as ctk

import constants
from constants import T, set_theme as _set_theme
import lang

FAKE_VERSION = "1.2.0"

_set_theme("dark")
ctk.set_appearance_mode("dark")


def _apply_dwm_round(hwnd):
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        value = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(value), ctypes.sizeof(value),
        )
        ctypes.windll.user32.SetWindowRgn(hwnd, None, True)
    except Exception:
        pass


class UpdatePopup(ctk.CTkToplevel):
    _W, _H = 280, 152

    def __init__(self, parent, ver: str, demo_mode: str = "normal"):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(fg_color=T["popup_bg"])
        self.wm_attributes("-topmost", True)

        self._ver         = ver
        self._demo_mode   = demo_mode
        self._drag_ox = self._drag_oy = 0

        parent.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self._W) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self._H) // 2
        self.geometry(f"{self._W}x{self._H}+{px}+{py}")

        self._build_ui()
        self.after(20, lambda: _apply_dwm_round(
            ctypes.windll.user32.GetParent(self.winfo_id())
        ))

        if demo_mode == "error":
            self.after(200, self._show_error)

    def _drag_start(self, e):
        self._drag_ox = e.x_root - self.winfo_x()
        self._drag_oy = e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._drag_ox}+{e.y_root - self._drag_oy}")

    def _build_ui(self):
        tbar = ctk.CTkFrame(self, fg_color=T["popup_bg"], height=36, corner_radius=0)
        tbar.pack(fill="x")
        tbar.pack_propagate(False)
        tbar.bind("<Button-1>",  self._drag_start)
        tbar.bind("<B1-Motion>", self._drag_move)

        title = ctk.CTkLabel(
            tbar, text=lang.t("update_title"),
            font=("Arial", 10, "bold"), text_color=T["subtext"],
        )
        title.place(relx=0.5, rely=0.5, anchor="center")
        title.bind("<Button-1>",  self._drag_start)
        title.bind("<B1-Motion>", self._drag_move)

        ctk.CTkButton(
            tbar, text="✕", width=28, height=28,
            fg_color="transparent", hover_color="#c42b1c",
            font=("Arial", 12, "bold"), text_color=T["subtext"],
            corner_radius=4, command=self.destroy,
        ).place(relx=1.0, rely=0.5, anchor="e", x=-4)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(8, 14))

        self._msg_lbl = ctk.CTkLabel(
            body,
            text=lang.t("update_available", ver=self._ver),
            font=("Arial", 12, "bold"), text_color=T["primary"],
        )
        self._msg_lbl.pack(pady=(0, 10))

        self._progress_bar = ctk.CTkProgressBar(
            body, width=220, height=10,
            progress_color=T["accent"], fg_color=T["card"],
        )
        self._progress_bar.set(0)
        self._progress_bar.pack(pady=(0, 10))
        self._progress_bar.pack_forget()

        self._update_btn = ctk.CTkButton(
            body, text=lang.t("update_now"),
            width=160, height=30,
            fg_color=T["accent"], hover_color=T["accent_dim"],
            font=("Arial", 11, "bold"), text_color="#ffffff",
            corner_radius=6, command=self._start_fake_download,
        )
        self._update_btn.pack()

    def _start_fake_download(self):
        self._update_btn.configure(state="disabled", text=lang.t("update_downloading", pct=0))
        self._progress_bar.set(0)
        self._progress_bar.pack(pady=(0, 10), before=self._update_btn)

        def run():
            for pct in range(0, 101, 3):
                time.sleep(0.06)
                self.after(0, lambda p=pct: self._on_progress(p)
                           if self.winfo_exists() else None)
            time.sleep(0.3)
            self.after(0, self._show_done)

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, pct: int):
        if not self.winfo_exists():
            return
        self._progress_bar.set(pct / 100)
        self._update_btn.configure(text=lang.t("update_downloading", pct=pct))

    def _show_done(self):
        if self.winfo_exists():
            self._progress_bar.set(1)
            self._msg_lbl.configure(text="✓  App would relaunch now",
                                    text_color=T["accent"])
            self._update_btn.configure(text="Done")

    def _show_error(self):
        if self.winfo_exists():
            self._progress_bar.pack_forget()
            self._msg_lbl.configure(text=lang.t("update_error"),
                                    text_color="#e85c25")
            self._update_btn.configure(state="normal", text=lang.t("update_now"))


class DemoApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Update Popup Demo")
        self.geometry("300, 200")
        self.geometry("300x200")
        self.resizable(False, False)
        self.configure(fg_color=T["bg"])
        self._popup = None
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Update popup demo",
            font=("Arial", 13, "bold"), text_color=T["label"],
        ).pack(pady=(24, 4))

        ctk.CTkLabel(
            self, text="Click a state to preview",
            font=("Arial", 10), text_color=T["muted"],
        ).pack(pady=(0, 16))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack()

        for label, mode in [("Update available", "normal"), ("Error", "error")]:
            ctk.CTkButton(
                btn_row, text=label, width=110, height=30,
                fg_color=T["card"], hover_color=T["hover"],
                font=("Arial", 11), text_color=T["primary"],
                corner_radius=6,
                command=lambda m=mode: self._open(m),
            ).pack(side="left", padx=4)

        theme_row = ctk.CTkFrame(self, fg_color="transparent")
        theme_row.pack(pady=(16, 0))

        ctk.CTkLabel(
            theme_row, text="Theme:",
            font=("Arial", 10), text_color=T["muted"],
        ).pack(side="left", padx=(0, 6))

        for name in ("dark", "light"):
            ctk.CTkButton(
                theme_row, text=name.capitalize(), width=60, height=26,
                fg_color=T["card"], hover_color=T["hover"],
                font=("Arial", 10), text_color=T["primary"],
                corner_radius=6,
                command=lambda n=name: self._switch_theme(n),
            ).pack(side="left", padx=3)

    def _open(self, mode: str):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
        self._popup = UpdatePopup(self, FAKE_VERSION, demo_mode=mode)

    def _switch_theme(self, name: str):
        _set_theme(name)
        ctk.set_appearance_mode(T["appearance"])
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
        self.configure(fg_color=T["bg"])


if __name__ == "__main__":
    app = DemoApp()
    app.mainloop()
