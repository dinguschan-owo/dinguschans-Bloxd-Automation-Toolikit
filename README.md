# Dinguschan's Bloxd Automation Toolkit

A Windows desktop automation toolkit for Bloxd. The current application is the
single-file `dinguschansautomation.py` script. This toolkit IS a
cheat/hack/botting toolkit, but I do not condone using it on multiplayer servers.

## Features

[Jump to the screenshot gallery](#gallery)

### Combat

- **Autoeat** — Swaps to and uses the selected hotbar item when health reaches the configured threshold.
- **Autosprint** — Repeatedly activates sprint at the configured interval, keeping you permanently sprinting.
- **Clicks** — Repeats or holds the selected mouse click at the configured interval.
- **Hotbar Alert** — Watches selected hotbar slots and adds a little alert on the slot when an item count is at or below the threshold.

### Automation

- **Autofish** — Smart autofishing module that detects fishing bites and automates reeling and recasting. Supports random recasting in different spots as well as automatically chaining glowtide flares in the skyblock gamemode.
- **Grid Path** — Allows you to draw a route on a grid and bot your player movement in a loop, with an optional pause between spaces.
- **Keys** — Repeats or holds the selected key using the chosen mode and interval.
- **Pattern** — Runs a custom loop of key, click, pause, and camera-turn steps.
- **Anti AFK** — Performs periodic actions such as jumping, clicking, or moving.

### Overlays

- **Active Modules** — Shows which modules are currently active.
- **CPS Visualizer** — Displays recent clicks per second.
- **Keyboard Visualizer** — Shows keyboard input on screen.
- **Mouse Visualizer** — Shows mouse button input on screen.

### Misc

- **Input Blocker** — Blocks selected keyboard keys or mouse buttons that may interfere with automation.
- **Coordinates** — Store your named X, Y, and Z coordinates.
- **Spin** — Turns the camera continuously in the selected direction.
- **Align** — Looks down and rotates to line your player up with a cardinal direction. Useful for grid pathing to avoid wandering off course.
- **Center** — Centeres your player on your current block.

This toolkit also allows the creation of profiles to save and load different module combinations and settings, and multiple modules can be selected and started from Start Selected to launch compatible selected modules together.

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

## Gallery

https://github.com/user-attachments/assets/844fa07b-3da2-46f2-8fa2-365dd8f44a77

<img width="1919" height="977" alt="overlays" src="https://github.com/user-attachments/assets/99786bbb-318b-4785-aef8-2a03d85ae4aa" />

