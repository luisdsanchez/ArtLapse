import customtkinter as ctk
import pygetwindow as gw
import pyautogui
import os
import json
import ctypes
import subprocess
import threading
import shutil
import pywinstyles
from tkinter import filedialog
from PIL import Image, ImageTk

# --- CONFIGURATION ---
CONFIG_FILE = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ArtLapse", "config.json")
ORANGE_THEME = "#e85c25"
ORANGE_DIM   = "#bc4a1e"
BG_COLOR     = "#1e2123"
CARD_COLOR   = "#262a2d"

ctk.set_appearance_mode("dark")

APP_W, APP_H = 400, 560


class ArtLapseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- WINDOW SETUP ---
        self.overrideredirect(True)
        self.geometry(f"{APP_W}x{APP_H}")
        self.configure(fg_color=BG_COLOR)
        self.update_idletasks()
        self._setup_taskbar_presence()
        self.after(20, self.apply_round_region)
        self.is_recording  = False
        self.base_path     = self.load_config()
        self.after_id      = None
        self.count         = 1
        self.final_path    = ""
        self._offsetx      = 0
        self._offsety      = 0
        self._thumb_photo  = None   # keep reference to avoid GC

        self._build_ui()

    # ------------------------------------------------------------------ #
    #  ROUNDED REGION                                                      #
    # ------------------------------------------------------------------ #
    def apply_round_region(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        rgn  = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, APP_W, APP_H, 22, 22)
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

        # ── BODY (scrollable content area) ──────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        # Window picker
        self._section_label(body, "CAPTURE WINDOW")
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", pady=(2, 0))
        self.window_dropdown = ctk.CTkComboBox(row1, values=self.get_window_titles(), width=290)
        self.window_dropdown.pack(side="left")
        ctk.CTkButton(row1, text="⟳", width=44, height=34,
                      fg_color=CARD_COLOR, hover_color="#333333",
                      font=("Arial", 17, "bold"),
                      command=self.refresh_windows).pack(side="left", padx=(6, 0))

        # Folder picker
        self._section_label(body, "OUTPUT FOLDER")
        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=(2, 0))
        self.folder_label = ctk.CTkLabel(row2, text=self.get_short_path(),
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
        self.project_combo = ctk.CTkComboBox(proj_row, values=self.get_existing_projects(), width=310)
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
        info_row.pack(fill="x", pady=(2, 6))

        self.thumb_label = ctk.CTkLabel(info_row, text="no preview",
                                        width=90, height=56,
                                        font=("Arial", 9), text_color="#555555",
                                        fg_color="#1a1d1f", corner_radius=8)
        self.thumb_label.pack(side="left", padx=8, pady=8)

        stats = ctk.CTkFrame(info_row, fg_color="transparent")
        stats.pack(side="left", padx=6, pady=8, fill="both", expand=True)
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
        self.status_label.pack(pady=(2, 6))

        # Start / ffmpeg buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 6))

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

        self.ffmpeg_btn = ctk.CTkButton(
            body, text="⬛  Compile to MP4  (ffmpeg)",
            fg_color=CARD_COLOR, hover_color="#333333",
            height=34, command=self.compile_video
        )
        self.ffmpeg_btn.pack(fill="x")

    # ------------------------------------------------------------------ #
    #  HELPERS                                                             #
    # ------------------------------------------------------------------ #
    def _section_label(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=("Arial", 9, "bold"),
                     text_color="#555555", anchor="w").pack(anchor="w", pady=(10, 0))

    def _click_window(self, event):
        self._offsetx = event.x_root - self.winfo_x()
        self._offsety = event.y_root - self.winfo_y()

    def _drag_window(self, event):
        x = event.x_root - self._offsetx
        y = event.y_root - self._offsety
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------ #
    #  BORDERLESS VIA WINDOWS API                                          #
    # ------------------------------------------------------------------ #
    def _setup_taskbar_presence(self):
        """
        overrideredirect windows have no taskbar entry and vanish on focus loss.
        Fix: set the WS_EX_APPWINDOW extended style on the underlying HWND so
        Windows treats it as a top-level app window — it stays visible, appears
        in the taskbar, and can be minimized normally.
        """
        GWL_EXSTYLE      = -20
        WS_EX_APPWINDOW  = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style &= ~WS_EX_TOOLWINDOW   # remove "hide from taskbar" flag
        ex_style |=  WS_EX_APPWINDOW    # add "show in taskbar" flag
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

    def _minimize(self):
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        ctypes.windll.user32.ShowWindow(hwnd, 6)   # SW_MINIMIZE = 6

    def _show_tray_icon(self): pass
    def _restore_from_tray(self, icon=None, item=None): pass
    def _quit_from_tray(self, icon=None, item=None): pass

    def _update_interval_label(self, val):
        self.label_interval.configure(text=f"{int(float(val))} s")
        self._refresh_size_estimate()

    # ------------------------------------------------------------------ #
    #  CONFIG                                                              #
    # ------------------------------------------------------------------ #
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f).get("base_path", "")
            except Exception:
                pass
        return ""

    def save_config(self):
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump({"base_path": self.base_path}, f)

    # ------------------------------------------------------------------ #
    #  WINDOW / FOLDER HELPERS                                            #
    # ------------------------------------------------------------------ #
    def get_short_path(self):
        if not self.base_path:
            return "Not Set"
        return f"…{self.base_path[-34:]}" if len(self.base_path) > 36 else self.base_path

    def get_window_titles(self):
        titles = [w.title for w in gw.getAllWindows() if w.title.strip()]
        return titles or ["No Windows Found"]

    def refresh_windows(self):
        self.window_dropdown.configure(values=self.get_window_titles())

    def get_existing_projects(self):
        if self.base_path and os.path.exists(self.base_path):
            try:
                return [d for d in os.listdir(self.base_path)
                        if os.path.isdir(os.path.join(self.base_path, d))] or ["New Project"]
            except Exception:
                pass
        return ["New Project"]

    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.base_path = path
            self.save_config()
            self.folder_label.configure(text=self.get_short_path())
            self.project_combo.configure(values=self.get_existing_projects())

    def open_output_folder(self):
        """Open the currently selected output folder (or base path) in Explorer."""
        target = self.final_path if self.final_path and os.path.exists(self.final_path) else self.base_path
        if target and os.path.exists(target):
            os.startfile(target)
        else:
            self.status_label.configure(text="No folder to open", text_color="orange")

    def delete_project(self):
        """Show a confirmation dialog then permanently delete the selected project folder."""
        name = self.project_combo.get().strip()
        if not name or name == "New Project" or not self.base_path:
            self.status_label.configure(text="No project selected to delete", text_color="orange")
            return

        target = os.path.join(self.base_path, name)
        if not os.path.exists(target):
            self.status_label.configure(text="Folder not found", text_color="orange")
            return

        # Block deletion of the currently active/recording project
        if target == self.final_path and self.is_recording:
            self.status_label.configure(text="Can't delete — currently recording", text_color="red")
            return

        # --- Confirmation dialog ---
        dialog = ctk.CTkToplevel(self)
        dialog.overrideredirect(True)
        dialog.configure(fg_color="#2a1a1a")
        dialog.resizable(False, False)

        dw, dh = 300, 160
        # Centre over main window
        cx = self.winfo_x() + (APP_W - dw) // 2
        cy = self.winfo_y() + (APP_H - dh) // 2
        dialog.geometry(f"{dw}x{dh}+{cx}+{cy}")
        dialog.grab_set()   # modal

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
                # If this was the loaded project, reset state
                if target == self.final_path:
                    self.stop_and_reset()
                else:
                    self.project_combo.set("")
                    self.project_combo.configure(values=self.get_existing_projects())
                self.status_label.configure(text=f'"{name}" deleted', text_color="gray")
            except Exception as e:
                self.status_label.configure(text=f"Delete failed: {e}", text_color="red")

        ctk.CTkButton(btn_row, text="Cancel", fg_color=CARD_COLOR, hover_color="#333333",
                      command=dialog.destroy, width=110).pack(side="left")
        ctk.CTkButton(btn_row, text="🗑  Delete", fg_color="#5a2020", hover_color="#7a2a2a",
                      text_color="#ff5555", font=("Arial", 12, "bold"),
                      command=confirm, width=130).pack(side="right")

    # ------------------------------------------------------------------ #
    #  FRAME-COUNT RESET GUARD                                            #
    # ------------------------------------------------------------------ #
    def _resolve_project_path(self):
        name = self.project_combo.get().strip()
        if not self.base_path or not name or name == "New Project":
            return None
        return os.path.join(self.base_path, name)

    # ------------------------------------------------------------------ #
    #  SIZE ESTIMATE                                                       #
    # ------------------------------------------------------------------ #
    def _refresh_size_estimate(self):
        """Estimate disk usage: avg PNG size × number of frames in session."""
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

    # ------------------------------------------------------------------ #
    #  THUMBNAIL                                                           #
    # ------------------------------------------------------------------ #
    def _update_thumbnail(self, img_path: str):
        try:
            img = Image.open(img_path)
            img.thumbnail((90, 56), Image.LANCZOS)
            self._thumb_photo = ImageTk.PhotoImage(img)
            self.thumb_label.configure(image=self._thumb_photo, text="")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  CAPTURE LOOP                                                        #
    # ------------------------------------------------------------------ #
    def toggle_capture(self):
        if not self.is_recording:
            path = self._resolve_project_path()
            if not path:
                self.status_label.configure(text="Set a folder & project name first", text_color="red")
                return

            # Only reset count if switching to a different project
            if path != self.final_path:
                self.final_path = path
                os.makedirs(self.final_path, exist_ok=True)
                existing = [f for f in os.listdir(self.final_path) if f.endswith(".png")]
                self.count = len(existing) + 1
                self.frames_label.configure(text=f"Frames: {len(existing)}")

            self.is_recording = True
            self.start_btn.configure(text="⏸  PAUSE", fg_color="#333333", hover_color="#444444")
            self.stop_btn.pack_forget()   # hide stop while actively recording
            self.status_label.configure(text=f"Recording — frame {self.count}", text_color=ORANGE_THEME)
            self.warn_label.configure(text="")
            self.capture_loop()
        else:
            self.is_recording = False
            if self.after_id:
                self.after_cancel(self.after_id)
            self.start_btn.configure(text="▶  RESUME", fg_color=ORANGE_THEME, hover_color=ORANGE_DIM)
            self.stop_btn.pack(side="left", padx=(6, 0))   # show stop when paused
            self.status_label.configure(text="Paused", text_color="orange")

    def stop_and_reset(self):
        """Stop recording and fully reset the app for a new project."""
        self.is_recording = False
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

        self.final_path = ""
        self.count      = 1

        self.start_btn.configure(text="START", fg_color=ORANGE_THEME, hover_color=ORANGE_DIM)
        self.stop_btn.pack_forget()
        self.status_label.configure(text="Ready", text_color="gray")
        self.warn_label.configure(text="")
        self.frames_label.configure(text="Frames: 0")
        self.size_label.configure(text="Est. size: —")
        self.thumb_label.configure(image="", text="no preview")
        self._thumb_photo = None
        self.project_combo.configure(values=self.get_existing_projects())
        self.project_combo.set("")

    def capture_loop(self):
        if not self.is_recording:
            return

        target  = self.window_dropdown.get()
        windows = gw.getWindowsWithTitle(target)

        if not windows:
            self.warn_label.configure(text="⚠ Window not found — retrying…")
        else:
            win = windows[0]
            if win.isMinimized:
                self.warn_label.configure(text="⚠ Window is minimized — skipping frame")
            else:
                self.warn_label.configure(text="")
                region     = (win.left, win.top, win.width, win.height)
                screenshot = pyautogui.screenshot(region=region, allScreens=True)
                save_path  = os.path.join(self.final_path, f"shot_{self.count:04d}.png")
                screenshot.save(save_path)
                self.status_label.configure(text=f"Recording — frame {self.count}")
                self.frames_label.configure(text=f"Frames: {self.count}")
                self.count += 1
                self._update_thumbnail(save_path)
                self._refresh_size_estimate()

        interval_ms = int(float(self.slider_interval.get()) * 1000)
        self.after_id = self.after(interval_ms, self.capture_loop)

    # ------------------------------------------------------------------ #
    #  VIDEO COMPILATION                                                   #
    # ------------------------------------------------------------------ #
    def compile_video(self):
        path = self._resolve_project_path() or self.final_path
        if not path or not os.path.exists(path):
            self.status_label.configure(text="No project folder found", text_color="red")
            return

        if not shutil.which("ffmpeg"):
            self.status_label.configure(text="ffmpeg not found in PATH", text_color="red")
            return

        out_file = os.path.join(path, "timelapse.mp4")
        self.status_label.configure(text="Compiling MP4…", text_color="gray")
        self.ffmpeg_btn.configure(state="disabled")

        def run():
            cmd = [
                "ffmpeg", "-y",
                "-framerate", "24",
                "-i", os.path.join(path, "shot_%04d.png"),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                out_file
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self.after(0, lambda: self.status_label.configure(
                        text="MP4 saved ✓", text_color=ORANGE_THEME))
                    self.after(0, lambda: os.startfile(path))
                else:
                    self.after(0, lambda: self.status_label.configure(
                        text="ffmpeg error — check console", text_color="red"))
                    print(result.stderr)
            except Exception as e:
                self.after(0, lambda: self.status_label.configure(
                    text=str(e), text_color="red"))
            finally:
                self.after(0, lambda: self.ffmpeg_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  WINDOW DRAG                                                         #
    # ------------------------------------------------------------------ #
    def click_window(self, event):
        self._offsetx = event.x
        self._offsety = event.y

    def drag_window(self, event):
        x = self.winfo_x() + event.x - self._offsetx
        y = self.winfo_y() + event.y - self._offsety
        self.geometry(f"+{x}+{y}")


if __name__ == "__main__":
    app = ArtLapseApp()
    app.mainloop()
