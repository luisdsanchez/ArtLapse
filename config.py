import os
import json
from constants import CONFIG_FILE


def _load_raw() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_raw(data: dict):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)


def load_config() -> str:
    return _load_raw().get("base_path", "")


def save_config(base_path: str):
    data = _load_raw()
    data["base_path"] = base_path
    _save_raw(data)


def load_lang() -> str:
    return _load_raw().get("lang", "en")


def save_lang(code: str):
    data = _load_raw()
    data["lang"] = code
    _save_raw(data)


def load_capture_quality() -> str:
    return _load_raw().get("capture_quality", "High")


def save_capture_quality(value: str):
    data = _load_raw()
    data["capture_quality"] = value
    _save_raw(data)


def load_smart_capture() -> bool:
    return bool(_load_raw().get("smart_capture", True))


def save_smart_capture(value: bool):
    data = _load_raw()
    data["smart_capture"] = value
    _save_raw(data)


def load_default_interval_idx() -> int:
    return int(_load_raw().get("default_interval_idx", 2))  # 2 → 2.5s


def save_default_interval_idx(idx: int):
    data = _load_raw()
    data["default_interval_idx"] = idx
    _save_raw(data)


def load_auto_export() -> bool:
    return bool(_load_raw().get("auto_export", False))


def save_auto_export(value: bool):
    data = _load_raw()
    data["auto_export"] = value
    _save_raw(data)


def load_default_duration_idx() -> int:
    return int(_load_raw().get("default_duration_idx", 3))  # 3 → 1m


def save_default_duration_idx(idx: int):
    data = _load_raw()
    data["default_duration_idx"] = idx
    _save_raw(data)


def load_launch_behavior() -> str:
    return _load_raw().get("launch_behavior", "normal")  # "normal" | "minimized" | "tray"


def save_launch_behavior(value: str):
    data = _load_raw()
    data["launch_behavior"] = value
    _save_raw(data)


def load_default_export_quality_idx() -> int:
    return int(_load_raw().get("default_export_quality_idx", 4))  # 4 → Highest


def save_default_export_quality_idx(idx: int):
    data = _load_raw()
    data["default_export_quality_idx"] = idx
    _save_raw(data)


def load_theme() -> str:
    return _load_raw().get("theme", "dark")


def save_theme(value: str):
    data = _load_raw()
    data["theme"] = value
    _save_raw(data)


def get_short_path(base_path: str) -> str:
    if not base_path:
        return "Not Set"
    return f"…{base_path[-34:]}" if len(base_path) > 36 else base_path


def get_existing_projects(base_path: str) -> list:
    if base_path and os.path.exists(base_path):
        try:
            dirs = [d for d in os.listdir(base_path)
                    if os.path.isdir(os.path.join(base_path, d))]
            return dirs or ["New Project"]
        except Exception:
            pass
    return ["New Project"]
