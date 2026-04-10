import os
import subprocess
import threading
from typing import Callable


def run_export(
    path:    str,
    pngs:    list,
    fps:     float,
    crf:     int,
    preset:  str,
    on_done:    Callable[[float, str], None],   # (size_mb, out_path)
    on_error:   Callable[[str], None],          # (error_message)
    on_finally: Callable[[], None],
):
    """
    Encodes frames in `path` into timelapse.mp4 using ffmpeg.
    Runs in a background daemon thread; call all callbacks from that thread
    (caller is responsible for dispatching to the UI thread via .after(0, ...)).
    """
    out_file = os.path.join(path, "timelapse.mp4")

    def run():
        concat_path = os.path.join(path, "_concat_list.txt")
        try:
            with open(concat_path, "w") as f:
                for png in pngs:
                    safe = os.path.join(path, png).replace("\\", "/").replace("'", "\\'")
                    f.write(f"file '{safe}'\n")
                    f.write("duration 1\n")

            cmd = [
                "ffmpeg", "-y",
                "-f",        "concat",
                "-safe",     "0",
                "-i",        concat_path,
                "-vf",       f"fps={fps}",
                "-c:v",      "libx264",
                "-preset",   preset,
                "-crf",      str(crf),
                "-pix_fmt",  "yuv420p",
                "-movflags", "+faststart",
                out_file,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                size_mb = os.path.getsize(out_file) / 1_048_576
                on_done(size_mb, path)
            else:
                on_error("ffmpeg error — check console")
                print(result.stderr)
        except Exception as e:
            on_error(str(e))
        finally:
            if os.path.exists(concat_path):
                os.remove(concat_path)
            on_finally()

    threading.Thread(target=run, daemon=True).start()
