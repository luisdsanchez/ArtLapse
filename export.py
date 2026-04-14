import os
import re
import sys
import subprocess
import threading
from typing import Callable


def _ffmpeg_path() -> str:
    """Return path to ffmpeg — bundled exe if running from PyInstaller, else system PATH."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "ffmpeg.exe")
    return "ffmpeg"


def run_export(
    path:    str,
    pngs:    list,
    fps:     float,
    crf:     int,
    preset:  str,
    on_done:    Callable[[float, str], None],   # (size_mb, out_path)
    on_error:   Callable[[str], None],          # (error_message)
    on_finally: Callable[[], None],
    project_name:  str = "",
    quality_label: str = "",
    on_progress:   Callable[[float], None] = None,  # fraction 0.0–1.0
):
    """
    Encodes frames in `path` into a named timelapse .mp4 using ffmpeg.
    Runs in a background daemon thread; call all callbacks from that thread
    (caller is responsible for dispatching to the UI thread via .after(0, ...)).
    """
    def _safe(s: str) -> str:
        """Strip characters that are invalid in Windows filenames."""
        return "".join(c for c in s if c not in r'\/:*?"<>|').strip()

    name_part    = _safe(project_name)  if project_name  else "Project"
    quality_part = _safe(quality_label) if quality_label else "Export"
    out_file = os.path.join(path, f"Timelapse_{name_part}_{quality_part}.mp4")

    total_frames = len(pngs)

    def run():
        concat_path = os.path.join(path, "_concat_list.txt")
        try:
            frame_duration = round(1.0 / fps, 6)
            with open(concat_path, "w") as f:
                for png in pngs:
                    safe = os.path.join(path, png).replace("\\", "/").replace("'", "\\'")
                    f.write(f"file '{safe}'\n")
                    f.write(f"duration {frame_duration}\n")

            cmd = [
                _ffmpeg_path(), "-y",
                "-f",        "concat",
                "-safe",     "0",
                "-i",        concat_path,
                "-vf",       "fps=24",
                "-c:v",      "libx264",
                "-preset",   preset,
                "-crf",      str(crf),
                "-pix_fmt",  "yuv420p",
                "-movflags", "+faststart",
                out_file,
            ]

            # CREATE_NO_WINDOW suppresses the CMD flash on Windows
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True,
                creationflags=creation_flags,
            )

            stderr_buf = []
            partial = ""
            while True:
                chunk = process.stderr.read(256)
                if not chunk:
                    break
                partial += chunk
                # ffmpeg uses \r to overwrite the stats line — split on both
                parts = re.split(r'[\r\n]', partial)
                partial = parts[-1]  # keep incomplete last part
                for part in parts[:-1]:
                    stderr_buf.append(part)
                    if on_progress and total_frames > 0:
                        m = re.search(r'frame=\s*(\d+)', part)
                        if m:
                            fraction = min(int(m.group(1)) / total_frames, 1.0)
                            on_progress(fraction)

            process.wait()
            if partial:
                stderr_buf.append(partial)
            stderr_lines = stderr_buf

            if process.returncode == 0:
                size_mb = os.path.getsize(out_file) / 1_048_576
                on_done(size_mb, out_file)
            else:
                on_error("ffmpeg error — check console")
                print("\n".join(stderr_lines))
        except Exception as e:
            on_error(str(e))
        finally:
            if os.path.exists(concat_path):
                os.remove(concat_path)
            on_finally()

    threading.Thread(target=run, daemon=True).start()
