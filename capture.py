import ctypes
import ctypes.wintypes
from PIL import Image


# ── Win32 structs ─────────────────────────────────────────────────────────────

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

class _MONITORINFOEX(ctypes.Structure):
    _fields_ = [
        ("cbSize",    ctypes.c_ulong),
        ("rcMonitor", ctypes.wintypes.RECT),
        ("rcWork",    ctypes.wintypes.RECT),
        ("dwFlags",   ctypes.c_ulong),
        ("szDevice",  ctypes.c_wchar * 32),
    ]


# ── Monitor helpers ───────────────────────────────────────────────────────────

def get_monitors() -> list[dict]:
    """Return list of {type, index, name, left, top, width, height, primary} for each monitor."""
    monitors = []

    def _cb(hMonitor, hdcMonitor, lprcMonitor, dwData):
        info = _MONITORINFOEX()
        info.cbSize = ctypes.sizeof(_MONITORINFOEX)
        ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info))
        r = info.rcMonitor
        monitors.append({
            "type":    "screen",
            "index":   len(monitors),
            "name":    f"Screen {len(monitors) + 1}",
            "left":    r.left,
            "top":     r.top,
            "width":   r.right  - r.left,
            "height":  r.bottom - r.top,
            "primary": bool(info.dwFlags & 0x1),
        })
        return True

    _MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_ulong, ctypes.c_ulong,
        ctypes.POINTER(ctypes.wintypes.RECT),
        ctypes.c_long,
    )
    ctypes.windll.user32.EnumDisplayMonitors(None, None, _MonitorEnumProc(_cb), 0)
    return monitors


# ── Window enumeration ────────────────────────────────────────────────────────

_SKIP_CLASSES = frozenset({
    "Progman", "WorkerW", "Shell_TrayWnd", "DV2ControlHost",
    "Windows.UI.Core.CoreWindow",
})

def get_visible_windows() -> list[dict]:
    """Return list of {type, hwnd, title, width, height} for visible, non-minimised app windows."""
    results = []
    user32  = ctypes.windll.user32

    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.IsIconic(hwnd):                      # minimised
            return True
        ex = user32.GetWindowLongW(hwnd, -20)          # GWL_EXSTYLE
        if ex & 0x00000080:                            # WS_EX_TOOLWINDOW
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True

        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        if cls_buf.value in _SKIP_CLASSES:
            return True

        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right  - rect.left
        h = rect.bottom - rect.top
        if w < 50 or h < 50:
            return True

        results.append({"type": "window", "hwnd": hwnd, "title": title, "width": w, "height": h})
        return True

    _WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_long)
    user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    return results


# ── Thumbnail helpers ─────────────────────────────────────────────────────────

def get_window_thumbnail(hwnd: int, width: int, height: int,
                         tw: int = 158, th: int = 89) -> "Image.Image | None":
    try:
        img = _printwindow_capture(hwnd, width, height)
        if img:
            return img.resize((tw, th), Image.LANCZOS)
    except Exception:
        pass
    return None


def get_screen_thumbnail(monitor: dict, tw: int = 158, th: int = 89) -> "Image.Image | None":
    try:
        img = _bitblt_capture(monitor["left"], monitor["top"],
                              monitor["width"], monitor["height"])
        if img:
            return img.resize((tw, th), Image.LANCZOS)
    except Exception:
        pass
    return None


# ── Icon helpers ──────────────────────────────────────────────────────────────

def get_window_icon(hwnd: int, size: int = 16) -> "Image.Image | None":
    try:
        hicon = _get_hicon(hwnd)
        if not hicon:
            return None
        return _hicon_to_pil(hicon, size)
    except Exception:
        return None


def _get_hicon(hwnd: int) -> int:
    user32      = ctypes.windll.user32
    WM_GETICON  = 0x007F
    ICON_SMALL2 = 2
    ICON_SMALL  = 0
    GCL_HICONSM = -34
    GCL_HICON   = -14

    hicon = user32.SendMessageW(hwnd, WM_GETICON, ICON_SMALL2, 0)
    if not hicon:
        hicon = user32.SendMessageW(hwnd, WM_GETICON, ICON_SMALL, 0)
    if not hicon:
        hicon = user32.GetClassLongPtrW(hwnd, GCL_HICONSM)
    if not hicon:
        hicon = user32.GetClassLongPtrW(hwnd, GCL_HICON)
    return hicon


def _hicon_to_pil(hicon: int, size: int = 16) -> "Image.Image | None":
    gdi32  = ctypes.windll.gdi32
    user32 = ctypes.windll.user32

    screen_dc = user32.GetDC(0)
    mem_dc    = gdi32.CreateCompatibleDC(screen_dc)
    bitmap    = gdi32.CreateCompatibleBitmap(screen_dc, size, size)
    old_bmp   = gdi32.SelectObject(mem_dc, bitmap)

    brush = gdi32.CreateSolidBrush(0x00000000)
    rc    = ctypes.wintypes.RECT(0, 0, size, size)
    user32.FillRect(mem_dc, ctypes.byref(rc), brush)
    gdi32.DeleteObject(brush)

    user32.DrawIconEx(mem_dc, 0, 0, hicon, size, size, 0, None, 0x0003)  # DI_NORMAL

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth       = size
    bmi.bmiHeader.biHeight      = -size
    bmi.bmiHeader.biPlanes      = 1
    bmi.bmiHeader.biBitCount    = 32
    bmi.bmiHeader.biCompression = 0

    buf = (ctypes.c_uint8 * (size * size * 4))()
    gdi32.GetDIBits(mem_dc, bitmap, 0, size, buf, ctypes.byref(bmi), 0)

    gdi32.SelectObject(mem_dc, old_bmp)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, screen_dc)

    return Image.frombuffer("RGBA", (size, size), bytes(buf), "raw", "BGRA", 0, 1)


# ── Public capture API ────────────────────────────────────────────────────────

def get_window_titles() -> list:
    """Legacy helper: return visible window titles."""
    wins = get_visible_windows()
    return [w["title"] for w in wins] or ["No Windows Found"]


def capture_frame_raw(target) -> "tuple[Image.Image | None, str]":
    """
    Like capture_frame but returns the PIL image instead of saving it.
    Returns (image, warning_string).
    """
    if isinstance(target, str):
        target = _resolve_window_by_title(target)
        if target is None:
            return None, "⚠ Window not found — retrying…"

    if target.get("type") == "screen":
        img = _bitblt_capture(target["left"], target["top"],
                              target["width"], target["height"])
        if img is None:
            return None, "⚠ Screen capture failed"
        return img, ""

    hwnd = target.get("hwnd")
    if not hwnd:
        return None, "⚠ No window selected"

    user32 = ctypes.windll.user32
    if not user32.IsWindowVisible(hwnd):
        return None, "⚠ Window not found — retrying…"
    if user32.IsIconic(hwnd):
        return None, "⚠ Window is minimized — skipping frame"

    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width  = rect.right  - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None, "⚠ Window has no size"

    img = _printwindow_capture(hwnd, width, height)
    if img is None:
        return None, "⚠ Capture failed"
    return img, ""


def capture_frame(target, save_path: str, jpeg_quality: "int | None" = None) -> tuple[bool, str]:
    """
    Capture a frame to save_path.
      target: dict  {"type": "window", "hwnd": int, ...}
                 or {"type": "screen", "left": int, "top": int, "width": int, "height": int, ...}
      Also accepts a plain str (window title) for backward compatibility.
      jpeg_quality: if set, saves as JPEG at the given quality (1–95); otherwise PNG.
    """
    if isinstance(target, str):
        target = _resolve_window_by_title(target)
        if target is None:
            return False, "⚠ Window not found — retrying…"

    if target.get("type") == "screen":
        return _capture_screen_frame(target, save_path, jpeg_quality)

    # Window capture
    hwnd = target.get("hwnd")
    if not hwnd:
        return False, "⚠ No window selected"

    user32 = ctypes.windll.user32
    if not user32.IsWindowVisible(hwnd):
        return False, "⚠ Window not found — retrying…"
    if user32.IsIconic(hwnd):
        return False, "⚠ Window is minimized — skipping frame"

    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width  = rect.right  - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return False, "⚠ Window has no size"

    img = _printwindow_capture(hwnd, width, height)
    if img is None:
        return False, "⚠ Capture failed"

    _save_image(img, save_path, jpeg_quality)
    return True, ""


def _save_image(img: "Image.Image", save_path: str, jpeg_quality: "int | None"):
    rgb = img.convert("RGB")
    if jpeg_quality is not None:
        rgb.save(save_path, "JPEG", quality=jpeg_quality)
    else:
        rgb.save(save_path)


def _capture_screen_frame(monitor: dict, save_path: str, jpeg_quality: "int | None" = None) -> tuple[bool, str]:
    img = _bitblt_capture(monitor["left"], monitor["top"],
                          monitor["width"], monitor["height"])
    if img is None:
        return False, "⚠ Screen capture failed"
    _save_image(img, save_path, jpeg_quality)
    return True, ""


def _resolve_window_by_title(title: str) -> "dict | None":
    for w in get_visible_windows():
        if w["title"] == title:
            return w
    return None


# ── Low-level BitBlt / PrintWindow ────────────────────────────────────────────

def _bitblt_capture(left: int, top: int, width: int, height: int) -> "Image.Image | None":
    """Capture a screen region via GDI BitBlt (works for the desktop/all monitors)."""
    gdi32  = ctypes.windll.gdi32
    user32 = ctypes.windll.user32

    screen_dc = user32.GetDC(0)
    if not screen_dc:
        return None

    mem_dc  = gdi32.CreateCompatibleDC(screen_dc)
    bitmap  = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    old_bmp = gdi32.SelectObject(mem_dc, bitmap)

    SRCCOPY = 0x00CC0020
    gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top, SRCCOPY)

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth       = width
    bmi.bmiHeader.biHeight      = -height
    bmi.bmiHeader.biPlanes      = 1
    bmi.bmiHeader.biBitCount    = 32
    bmi.bmiHeader.biCompression = 0

    buf = (ctypes.c_uint8 * (width * height * 4))()
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(bmi), 0)

    gdi32.SelectObject(mem_dc, old_bmp)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, screen_dc)

    return Image.frombuffer("RGBA", (width, height), bytes(buf), "raw", "BGRA", 0, 1)


def _printwindow_capture(hwnd: int, width: int, height: int) -> "Image.Image | None":
    """
    Uses PrintWindow with PW_RENDERFULLCONTENT (flag=2) to render the window
    into a memory DC. Works for GPU-composited/hardware-accelerated windows.
    """
    gdi32  = ctypes.windll.gdi32
    user32 = ctypes.windll.user32

    window_dc = user32.GetWindowDC(hwnd)
    if not window_dc:
        return None

    mem_dc  = gdi32.CreateCompatibleDC(window_dc)
    bitmap  = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    old_bmp = gdi32.SelectObject(mem_dc, bitmap)

    user32.PrintWindow(hwnd, mem_dc, 2)  # PW_RENDERFULLCONTENT = 2

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth       = width
    bmi.bmiHeader.biHeight      = -height
    bmi.bmiHeader.biPlanes      = 1
    bmi.bmiHeader.biBitCount    = 32
    bmi.bmiHeader.biCompression = 0

    buf = (ctypes.c_uint8 * (width * height * 4))()
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(bmi), 0)

    gdi32.SelectObject(mem_dc, old_bmp)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, window_dc)

    return Image.frombuffer("RGBA", (width, height), bytes(buf), "raw", "BGRA", 0, 1)
