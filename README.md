# ArtLapse

A lightweight Windows desktop app for recording timelapses of any open window on your screen. Capture your art process, coding sessions, or any creative workflow — then export it as an MP4 video with one click.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- Select any open window as the capture target
- Adjustable capture interval (1–60 seconds)
- Organized project folders — each session saves frames separately
- Export to MP4 via FFmpeg with configurable quality and speed settings
- Compact borderless UI with a custom orange theme

## Requirements

- Windows 10/11
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) installed and available in your system PATH

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/luisdsanchez/ArtLapse.git
   cd ArtLapse
   ```

2. Install dependencies:
   ```bash
   pip install customtkinter pillow pywin32
   ```

3. Make sure FFmpeg is installed and on your PATH.

4. Run the app:
   ```bash
   python ArtLapse.py
   ```

## Usage

1. Launch ArtLapse.
2. Set a **base path** where your project folders will be saved.
3. Enter a **project name** — a subfolder will be created automatically.
4. Select the **window** you want to capture from the dropdown.
5. Set the **capture interval** using the slider.
6. Press **Start** to begin recording.
7. When done, press **Stop**, then open the export panel to render your MP4.

Captured frames are saved as `shot_0001.png`, `shot_0002.png`, etc. inside `base_path/project_name/`.

## Project Structure

```
ArtLapse/
├── ArtLapse.py           # Main entry point and UI
├── capture.py            # Window capture logic
├── export.py             # FFmpeg export (runs in background thread)
├── config.py             # Config load/save helpers
└── constants.py          # Theme colors and layout constants
```

## License

MIT — see [LICENSE](LICENSE) for details.
