# Dinguschan's Bloxd Automation Toolkit

A Windows desktop automation toolkit for Bloxd. The current application is the
single-file `dinguschansautomation.py` script. This toolkit IS a
cheat/hack/botting toolkit, but I do not condone using it on multiplayer servers.

## Features

### Combat

- **Autoeat** — Uses the selected hotbar item when health reaches the configured threshold.
- **Autosprint** — Repeatedly activates sprint at the configured interval.
- **Clicks** — Repeats the selected mouse click at the configured interval.
- **Hotbar Alert** — Watches selected hotbar slots and alerts when an item count is at or below the threshold.

### Automation

- **Autofish** — Detects fishing bites and automates reeling and recasting.
- **Grid Path** — Draws a route on a grid and follows it, with an optional pause between spaces.
- **Keys** — Repeats the selected key using the chosen mode and interval.
- **Pattern** — Runs a custom loop of key, click, pause, and camera-turn steps.
- **Anti AFK** — Performs periodic actions such as jumping, clicking, or moving.

### Overlays

- **Active Modules** — Shows which modules are currently active.
- **CPS Visualizer** — Displays recent clicks per second.
- **Keyboard Visualizer** — Shows keyboard input on screen.
- **Mouse Visualizer** — Shows mouse button input on screen.

### Misc

- **Input Blocker** — Blocks selected keyboard keys or mouse buttons.
- **Coordinates** — Stores named X, Y, and Z coordinates.
- **Spin** — Turns the camera continuously in the selected direction.
- **Align** — Rotates the on-screen square to line it up with the screen.
- **Center** — Moves the on-screen square to the center of the screen.

Profiles let you save and load module settings. Start Selected launches compatible selected modules together.

## Requirements

- Windows 10 or 11.
- 64-bit CPython 3.15 is the current tested setup. Other Python versions have
  not been verified for this application.
- A Python installation that includes Tkinter/Tcl-Tk.
- A Windows OCR language installed and available to the current Windows user.
  Autoeat, Autofish, Hotbar Alert, Center, and Align use Windows OCR.

Install these pinned Python packages:

- Pillow 13.0.0
- winrt-runtime 4.1.0
- winrt-Windows.Graphics.Imaging 4!10.0.28000.2957
- winrt-Windows.Media.Ocr 4!10.0.28000.2957
- winrt-Windows.Storage.Streams 4!10.0.28000.2957

## Install and run from source

Download the repository ZIP from GitHub and extract it. The extracted folder
contains `dinguschansautomation.py` and `icon.png`. Open PowerShell in that
folder and run:

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install `
    Pillow==13.0.0 `
    winrt-runtime==4.1.0 `
    "winrt-Windows.Graphics.Imaging==4!10.0.28000.2957" `
    "winrt-Windows.Media.Ocr==4!10.0.28000.2957" `
    "winrt-Windows.Storage.Streams==4!10.0.28000.2957"
.\.venv\Scripts\python.exe .\dinguschansautomation.py
```

If `py -3.15` is unavailable, install 64-bit CPython 3.15 and create the
environment with that interpreter. Keep `icon.png` beside `dinguschansautomation.py`;
the application loads it from its own folder.

Settings and profiles are stored under:

```text
%APPDATA%\dinguschan-tools\
```

