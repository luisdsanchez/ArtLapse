import ctypes
import pygetwindow as gw
from PIL import Image


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize",          ctypes.c_uint32),
        ("biWidth",         ctypes.c_int32),
        ("biHeight",        ctypes.c_int32),
        ("biPlanes",        ctypes.c_uint16),
        ("biBitCount",      ctypes.c_uint16),
        ("biCompression",   ctypes.c_uint32),
        ("biSizeImage",     ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed",       ctypes.c_uint32),
        ("biClrImportant",  ctypes.c_uint32),
    ]

class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_uint32 * 3),
    ]


def get_window_titles() -> list:
    titles = [w.title for w in gw.getAllWindows() if w.title.strip()]
    return titles or ["No Windows Found"]


def capture_frame(window_title: str, save_path: str) -> tuple[bool, str]:
    """
    Captures a window using PrintWindow(PW_RENDERFULLCONTENT).
    Works for hardware-accelerated windows (browsers, GPU apps) that produce
    black frames with pyautogui's BitBlt approach.
    Returns (captured: bool, warning_message: str).
    """
    windows = gw.getWindowsWithTitle(window_title)
    if not windows:
        return False, "⚠ Window not found — retrying…"
    win = windows[0]
    if win.isMinimized:
        return False, "⚠ Window is minimized — skipping frame"

    img = _printwindow_capture(win._hWnd, win.width, win.height)
    if img is None:
        return False, "⚠ Capture failed"

    img.convert("RGB").save(save_path)
    return True, ""


def _printwindow_capture(hwnd: int, width: int, height: int) -> Image.Image | None:
    """
    Uses PrintWindow with PW_RENDERFULLCONTENT (flag=2) to render the window
    into a memory DC. Unlike BitBlt, this works for GPU-composited content.
    """
    gdi32  = ctypes.windll.gdi32
    user32 = ctypes.windll.user32

    window_dc = user32.GetWindowDC(hwnd)
    if not window_dc:
        return None

    mem_dc  = gdi32.CreateCompatibleDC(window_dc)
    bitmap  = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    old_bmp = gdi32.SelectObject(mem_dc, bitmap)

    # PW_RENDERFULLCONTENT = 2 — forces GPU-rendered content to blit into the DC
    user32.PrintWindow(hwnd, mem_dc, 2)

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth       = width
    bmi.bmiHeader.biHeight      = -height   # negative = top-down row order
    bmi.bmiHeader.biPlanes      = 1
    bmi.bmiHeader.biBitCount    = 32
    bmi.bmiHeader.biCompression = 0         # BI_RGB

    buf = (ctypes.c_uint8 * (width * height * 4))()
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(bmi), 0)

    gdi32.SelectObject(mem_dc, old_bmp)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, window_dc)

    return Image.frombuffer("RGBA", (width, height), bytes(buf), "raw", "BGRA", 0, 1)
