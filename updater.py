"""
ArtLapse — auto-updater.

Flow:
    1. check_for_update() → (latest_version, download_url) or None
    2. download_and_swap(download_url, on_progress) — downloads new exe,
       writes a .bat launcher that swaps files after the app exits, then
       calls sys.exit() to trigger the swap.
"""

import os
import sys
import subprocess
import tempfile
import threading

import requests

from constants import APP_VERSION, GITHUB_REPO


def _parse_version(v: str) -> tuple:
    """'1.2.3' → (1, 2, 3)"""
    v = v.lstrip("v").strip()
    parts = v.split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    return tuple(result)


def check_for_update() -> "tuple[str, str] | None":
    """
    Returns (latest_version_str, exe_download_url) if a newer release exists,
    otherwise None.  Raises nothing — all errors are swallowed.
    """
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        resp = requests.get(url, timeout=5, headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        data = resp.json()

        latest_tag = data.get("tag_name", "")
        latest_ver = latest_tag.lstrip("v").strip()

        if _parse_version(latest_ver) <= _parse_version(APP_VERSION):
            return None  # already up to date

        # Find the .exe asset
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".exe"):
                return latest_ver, asset["browser_download_url"]

        return None  # release exists but no exe asset
    except Exception:
        return None


def download_and_swap(download_url: str, on_progress=None):
    """
    Downloads the new exe to a temp file, writes a .bat swap script, launches
    it, then exits the current process.

    on_progress(fraction: float) is called periodically during download.
    """
    current_exe = sys.executable if getattr(sys, "frozen", False) else None
    if not current_exe:
        # Running from source — can't self-replace; just open the URL
        import webbrowser
        webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")
        return

    # 1. Download to temp
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".exe", prefix="ArtLapse_update_")
    os.close(tmp_fd)
    try:
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress and total:
                            on_progress(downloaded / total)
    except Exception as e:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise RuntimeError(f"Download failed: {e}") from e

    if on_progress:
        on_progress(1.0)

    # 2. Write a .bat that waits for us to exit, swaps files, then relaunches
    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="ArtLapse_swap_")
    os.close(bat_fd)
    current_pid = os.getpid()
    exe_dir = os.path.dirname(os.path.abspath(current_exe))
    # Derive the new filename from the asset URL (e.g. ArtLapsev1.2.exe)
    # so the renamed file matches the release name.
    new_exe_name = download_url.rstrip("/").split("/")[-1]
    if not new_exe_name.lower().endswith(".exe"):
        new_exe_name = os.path.basename(current_exe)
    new_exe = os.path.join(exe_dir, new_exe_name)
    # PyInstaller extracts to this folder; we tell the bat to delete it after
    # the process exits so the new exe doesn't try to reuse a stale extraction.
    mei_dir = getattr(sys, "_MEIPASS", None)
    with open(bat_path, "w") as f:
        mei_cleanup = (
            f'if exist "{mei_dir}" (rmdir /s /q "{mei_dir}")\n'
            if mei_dir else ""
        )
        f.write(
            "@echo off\n"
            # Wait until the old process is fully gone before swapping
            f':wait\n'
            f'tasklist /fi "PID eq {current_pid}" 2>nul | find /i "{current_pid}" >nul\n'
            f'if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\n'
            + mei_cleanup +
            f'move /y "{tmp_path}" "{new_exe}"\n'
            f'powershell -Command "Unblock-File -LiteralPath \'{new_exe}\'" >nul 2>&1\n'
            # Delete the old exe if the name changed
            + (f'if exist "{current_exe}" (del /f /q "{current_exe}")\n'
               if new_exe.lower() != current_exe.lower() else "")
            + f'del "%~f0"\n'
        )

    # 3. Launch the bat (hidden) and exit
    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    # Signal the main process to exit after a short delay so the UI can show
    # the "relaunch" message before the window closes.
    import threading as _t
    def _delayed_exit():
        import time; time.sleep(2.5)
        os._exit(0)
    _t.Thread(target=_delayed_exit, daemon=True).start()


def check_in_background(callback):
    """
    Runs check_for_update() in a daemon thread.
    callback(result) is called on completion in the same thread (not main thread).
    Use .after(0, ...) in your callback to hop back to the Tk thread.
    """
    def _worker():
        result = check_for_update()
        callback(result)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
