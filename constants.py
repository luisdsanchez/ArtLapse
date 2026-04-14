import os
import customtkinter as ctk

APP_VERSION  = "1.1.0"
GITHUB_REPO  = "luisdsanchez/ArtLapse"

CONFIG_FILE  = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ArtLapse", "config.json")

APP_W, APP_H = 400, 780

# ── Theme palettes ────────────────────────────────────────────────────────────
THEMES = {
    "dark": {
        "bg":           "#1e2123",
        "card":         "#262a2d",
        "popup_bg":     "#181a1b",
        "accent":       "#e85c25",
        "accent_dim":   "#bc4a1e",
        "hover":        "#333333",
        "label":        "#aaaaaa",
        "subtext":      "#666666",
        "muted":        "#555555",
        "primary":      "#dddddd",
        "title_bar":    "#666666",
        "card_inner":   "#161819",
        "card_border":  "#2d3133",
        "tooltip_bg":   "#2a2d2f",
        "tooltip_fg":   "#cccccc",
        "appearance":   "dark",
    },
    "light": {
        "bg":           "#F2EBD9",
        "card":         "#E5DDD0",
        "popup_bg":     "#DBCDBA",
        "accent":       "#2A8B7A",
        "accent_dim":   "#1E6B5E",
        "hover":        "#D6CEBC",
        "label":        "#3B4E7A",
        "subtext":      "#556080",
        "muted":        "#7080A8",
        "primary":      "#1A2744",
        "title_bar":    "#556080",
        "card_inner":   "#DDD5C5",
        "card_border":  "#C8C0B2",
        "tooltip_bg":   "#E8E0D0",
        "tooltip_fg":   "#1A2744",
        "appearance":   "light",
    },
}

# Mutable active-theme dict — mutated in-place by set_theme()
T: dict = dict(THEMES["dark"])

CURRENT_THEME_NAME = "dark"


def set_theme(name: str):
    """Update T in-place. CTk appearance mode is set once at startup only."""
    global CURRENT_THEME_NAME
    CURRENT_THEME_NAME = name
    T.update(THEMES[name])
