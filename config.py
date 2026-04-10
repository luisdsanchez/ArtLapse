import os
import json
from constants import CONFIG_FILE


def load_config() -> str:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("base_path", "")
        except Exception:
            pass
    return ""


def save_config(base_path: str):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump({"base_path": base_path}, f)


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
