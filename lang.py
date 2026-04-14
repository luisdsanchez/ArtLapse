"""
ArtLapse — UI string translations.

Usage:
    import lang
    lang.set_lang("es")
    lang.t("btn_start")            # → "INICIAR"
    lang.t("status_recording", 5)  # → "Grabando — fotograma 5"
"""

_STRINGS = {
    "en": {
        # ── Main section headers ──────────────────────────────────────────
        "section_target":   "Capture Target",
        "section_folder":   "Output Folder",
        "section_project":  "Project Name",
        "section_interval": "Capture Interval",

        # ── Capture Quality ───────────────────────────────────────────────
        "capture_quality": "Capture Quality",
        "cq_low":  "Low",
        "cq_med":  "Med",
        "cq_high": "High",
        "cq_tip_low":  "JPEG 55% — smallest files",
        "cq_tip_med":  "JPEG 75% — balanced",
        "cq_tip_high": "PNG lossless — full quality",

        # ── Placeholders ──────────────────────────────────────────────────
        "target_placeholder":  "  Click to select a window or screen\u2026",
        "project_placeholder": "  Click to name or pick a project\u2026",
        "project_placeholder_short": "  type new or pick existing\u2026",

        # ── Smart Capture ─────────────────────────────────────────────────
        "smart_capture": "Smart Capture",
        "smart_caption": "— skips saving identical frames",
        "smart_tooltip": "Skips saving a frame if the screen\nhasn't changed for 5 consecutive shots.",

        # ── Status / guidance ─────────────────────────────────────────────
        "status_step1":       "\u25b2 Pick a capture target to begin",
        "status_step3":       "\u25b2 Step 3 \u2014 name your project to continue",
        "status_ready":       "Ready \u2014 press START",
        "status_recording": "Recording \u2014 frame {n}",
        "status_smart_pause": "Smart pause \u2014 frame {n}",
        "status_exporting": "Exporting\u2026",
        "status_no_target": "Select a capture target first",
        "status_no_project_rec": "Set a folder & project name first",
        "status_no_folder": "No folder to open",
        "status_no_project_del": "No project selected to delete",
        "status_folder_not_found": "Folder not found",
        "status_cant_delete": "Can't delete \u2014 currently recording",
        "status_deleted": '"{name}" deleted',
        "status_delete_failed": "Delete failed: {err}",
        "status_select_export": "Select a project to export",
        "status_no_frames": "No frames found in folder",
        "status_no_ffmpeg": "ffmpeg not found in PATH",

        # ── Main buttons ──────────────────────────────────────────────────
        "btn_start":  "START",
        "btn_pause":  "\u23f8  PAUSE",
        "btn_resume": "\u25b6  RESUME",
        "btn_paused_hint": "Paused \u2014 press \u25b6 to resume or \u23f9 to stop",

        # ── Export panel ──────────────────────────────────────────────────
        "btn_export":    "\u25b6  Export Timelapse MP4",
        "auto_export":   "Auto-export on Stop",
        "lbl_duration":  "Duration",
        "lbl_quality":   "Quality",
        "hint_smallest": "Smallest",
        "hint_highest":  "Highest",
        "hint_15s":      "15 sec",
        "hint_realtime": "Realtime",

        # ── Frames counter ────────────────────────────────────────────────
        "frames_zero":  "Frames: 0",
        "frames_n":     "Frames: {n}",
        "frame_single": "{n} frame",
        "frame_plural": "{n} frames",
        "thumb_no_preview": "no\npreview",

        # ── Tooltips ──────────────────────────────────────────────────────
        "tip_minimize":    "Minimize",
        "tip_tray":        "Hide to system tray",
        "tip_quit":        "Quit ArtLapse",
        "tip_browse":      "Browse for output folder",
        "tip_open_folder": "Open folder in Explorer",

        # ── Settings tooltips ─────────────────────────────────────────────
        "tip_settings_cq":         "Low = JPEG 55% (smallest)\nMed = JPEG 75% (balanced)\nHigh = PNG lossless (full quality)",
        "tip_settings_smart":      "Skips saving a frame if the screen\nhasn't changed for 5 consecutive shots.",
        "tip_settings_auto_export":"Automatically exports a timelapse MP4\nwhen you stop a recording.",

        # ── Export popup ──────────────────────────────────────────────────
        "export_title":    "EXPORT OPTIONS",
        "export_success":  "Exported successfully!",
        "btn_open_folder": "Open Folder",
        "btn_close":       "Close",

        # ── Settings popup ────────────────────────────────────────────────
        "settings_title":    "SETTINGS",
        "settings_language": "Language",
        "settings_capture_quality": "Capture Quality",
        "settings_smart_capture":   "Smart Capture",
        "settings_interval":        "Default Interval",
        "settings_auto_export":     "Auto-export on Stop",
        "settings_duration":        "Default Duration",
        "settings_launch":          "Launch as",
        "launch_normal":    "Window",
        "launch_minimized": "Minimized",
        "launch_tray":      "Tray",
        "settings_theme":   "Theme",
        "theme_dark":       "Dark",
        "theme_light":      "Light",

        # ── Window/target picker popup ────────────────────────────────────
        "picker_title":      "SELECT CAPTURE TARGET",
        "picker_loading":    "Loading\u2026",
        "picker_screens":    "SCREENS",
        "picker_apps":       "APPLICATIONS",
        "picker_no_windows": "No visible windows found.",

        # ── Project picker popup ──────────────────────────────────────────
        "proj_title":       "SELECT PROJECT",
        "proj_new":         "NEW PROJECT",
        "proj_new_ph":      "type a new project name\u2026",
        "proj_existing":    "EXISTING PROJECTS",
        "proj_no_projects": "No existing projects.",

        # ── Delete confirmation dialog ────────────────────────────────────
        "dlg_del_title":  "Delete project?",
        "dlg_del_body":   '"{name}" and all its files\nwill be permanently deleted.',
        "btn_cancel":     "Cancel",
        "btn_delete":     "\U0001f5d1  Delete",

        # ── Update popup ──────────────────────────────────────────────────
        "update_title":       "Update Available",
        "update_current_ver": "Current version: v{ver}",
        "update_available":   "v{ver} is ready to install",
        "update_now":         "Update now",
        "update_later":       "Later",
        "update_downloading": "Downloading… {pct}%",
        "update_error":       "Download failed — try again later",
        "update_relaunch":    "Updated! Relaunch to apply.",
    },

    "es": {
        # ── Encabezados de sección ────────────────────────────────────────
        "section_target":   "Destino de captura",
        "section_folder":   "Carpeta de salida",
        "section_project":  "Nombre del proyecto",
        "section_interval": "Intervalo de captura",

        # ── Calidad de captura ────────────────────────────────────────────
        "capture_quality": "Calidad de captura",
        "cq_low":  "Baja",
        "cq_med":  "Med",
        "cq_high": "Alta",
        "cq_tip_low":  "JPEG 55% — archivos m\u00e1s peque\u00f1os",
        "cq_tip_med":  "JPEG 75% — equilibrado",
        "cq_tip_high": "PNG sin p\u00e9rdida — m\u00e1xima calidad",

        # ── Marcadores de posici\u00f3n ──────────────────────────────────────────
        "target_placeholder":  "  Clic para seleccionar ventana o pantalla\u2026",
        "project_placeholder": "  Clic para nombrar o elegir un proyecto\u2026",
        "project_placeholder_short": "  escribí o elegí un proyecto\u2026",

        # ── Captura inteligente ───────────────────────────────────────────
        "smart_capture": "Captura inteligente",
        "smart_caption": "— omite fotogramas id\u00e9nticos",
        "smart_tooltip": "Omite guardar un fotograma si la pantalla\nno cambi\u00f3 en 5 capturas consecutivas.",

        # ── Estado / orientaci\u00f3n ────────────────────────────────────────────
        "status_step1":       "\u25b2 Seleccioná un destino de captura para comenzar",
        "status_step3":       "\u25b2 Paso 3 \u2014 nombr\u00e1 tu proyecto para continuar",
        "status_ready":       "Listo \u2014 presion\u00e1 INICIAR",
        "status_recording": "Grabando \u2014 fotograma {n}",
        "status_smart_pause": "Pausa inteligente \u2014 fotograma {n}",
        "status_exporting": "Exportando\u2026",
        "status_no_target": "Seleccion\u00e1 un destino primero",
        "status_no_project_rec": "Configur\u00e1 carpeta y proyecto primero",
        "status_no_folder": "Sin carpeta para abrir",
        "status_no_project_del": "Sin proyecto seleccionado",
        "status_folder_not_found": "Carpeta no encontrada",
        "status_cant_delete": "No se puede \u2014 grabando",
        "status_deleted": '"{name}" eliminado',
        "status_delete_failed": "Error al eliminar: {err}",
        "status_select_export": "Seleccion\u00e1 un proyecto para exportar",
        "status_no_frames": "Sin fotogramas en la carpeta",
        "status_no_ffmpeg": "ffmpeg no encontrado en PATH",

        # ── Botones principales ───────────────────────────────────────────
        "btn_start":  "INICIAR",
        "btn_pause":  "\u23f8  PAUSAR",
        "btn_resume": "\u25b6  CONTINUAR",
        "btn_paused_hint": "Pausado \u2014 presion\u00e1 \u25b6 para continuar o \u23f9 para detener",

        # ── Panel de exportaci\u00f3n ────────────────────────────────────────────
        "btn_export":    "\u25b6  Exportar Timelapse MP4",
        "auto_export":   "Exportar al detener",
        "lbl_duration":  "Duraci\u00f3n",
        "lbl_quality":   "Calidad",
        "hint_smallest": "Menor",
        "hint_highest":  "Mayor",
        "hint_15s":      "15 seg",
        "hint_realtime": "Tiempo real",

        # ── Contador de fotogramas ────────────────────────────────────────
        "frames_zero":  "Fotogramas: 0",
        "frames_n":     "Fotogramas: {n}",
        "frame_single": "{n} fotograma",
        "frame_plural": "{n} fotogramas",
        "thumb_no_preview": "sin\npreview",

        # ── Informaci\u00f3n emergente ──────────────────────────────────────────
        "tip_minimize":    "Minimizar",
        "tip_tray":        "Ocultar en la bandeja",
        "tip_quit":        "Salir de ArtLapse",
        "tip_browse":      "Buscar carpeta de salida",
        "tip_open_folder": "Abrir en el Explorador",

        # ── Tooltips de ajustes ───────────────────────────────────────────
        "tip_settings_cq":         "Baja = JPEG 55% (más liviano)\nMed = JPEG 75% (equilibrado)\nAlta = PNG sin pérdida (máx. calidad)",
        "tip_settings_smart":      "Omite guardar un fotograma si la pantalla\nno cambió en 5 capturas consecutivas.",
        "tip_settings_auto_export":"Exporta automáticamente un MP4\ncuando detenés la grabación.",

        # ── Ventana de exportación ────────────────────────────────────────
        "export_title":    "OPCIONES DE EXPORTACIÓN",
        "export_success":  "¡Exportado exitosamente!",
        "btn_open_folder": "Abrir carpeta",
        "btn_close":       "Cerrar",

        # ── Ventana de ajustes ────────────────────────────────────────────
        "settings_title":    "AJUSTES",
        "settings_language": "Idioma",
        "settings_capture_quality": "Calidad de captura",
        "settings_smart_capture":   "Captura inteligente",
        "settings_interval":        "Intervalo predeterminado",
        "settings_auto_export":     "Exportar al detener",
        "settings_duration":        "Duración predeterminada",
        "settings_launch":          "Iniciar como",
        "launch_normal":    "Ventana",
        "launch_minimized": "Minimizado",
        "launch_tray":      "Bandeja",
        "settings_theme":   "Tema",
        "theme_dark":       "Oscuro",
        "theme_light":      "Claro",

        # ── Selector de ventana/pantalla ──────────────────────────────────
        "picker_title":      "SELECCIONAR DESTINO",
        "picker_loading":    "Cargando\u2026",
        "picker_screens":    "PANTALLAS",
        "picker_apps":       "APLICACIONES",
        "picker_no_windows": "No hay ventanas visibles.",

        # ── Selector de proyectos ─────────────────────────────────────────
        "proj_title":       "SELECCIONAR PROYECTO",
        "proj_new":         "NUEVO PROYECTO",
        "proj_new_ph":      "escrib\u00ed un nombre de proyecto\u2026",
        "proj_existing":    "PROYECTOS EXISTENTES",
        "proj_no_projects": "Sin proyectos existentes.",

        # ── Di\u00e1logo de eliminaci\u00f3n ────────────────────────────────────────────
        "dlg_del_title":  "\u00bfEliminar proyecto?",
        "dlg_del_body":   '"{name}" y todos sus archivos\nser\u00e1n eliminados permanentemente.',
        "btn_cancel":     "Cancelar",
        "btn_delete":     "\U0001f5d1  Eliminar",

        # ── Popup de actualización ────────────────────────────────────────
        "update_title":       "Actualización disponible",
        "update_current_ver": "Versión actual: v{ver}",
        "update_available":   "v{ver} está lista para instalar",
        "update_now":         "Actualizar",
        "update_later":       "Después",
        "update_downloading": "Descargando… {pct}%",
        "update_error":       "Error de descarga — inténtalo más tarde",
        "update_relaunch":    "¡Actualizado! Reinicia para aplicar.",
    },
}

_current_lang: str = "en"


def set_lang(code: str) -> None:
    global _current_lang
    if code in _STRINGS:
        _current_lang = code


def get_lang() -> str:
    return _current_lang


def t(key: str, *args, **kwargs) -> str:
    """Return the translated string for *key* in the current language.

    Optional positional/keyword args are forwarded to str.format(), e.g.:
        t("status_recording", n=42)  → "Recording — frame 42"
    """
    raw = _STRINGS[_current_lang].get(key, _STRINGS["en"].get(key, key))
    if args or kwargs:
        try:
            return raw.format(*args, **kwargs)
        except (KeyError, IndexError):
            return raw
    return raw
