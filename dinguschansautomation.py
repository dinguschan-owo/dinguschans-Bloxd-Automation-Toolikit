import asyncio
import ctypes
import io
import json
import math
import os
import random
import re
import statistics
import struct
import threading
import time
import tkinter as tk
from collections import deque
from ctypes import wintypes
from tkinter import colorchooser
from tkinter import ttk
from tkinter import font as tkfont

try:
    from PIL import Image, ImageGrab, ImageFilter, ImageTk
except ImportError:
    Image = ImageGrab = ImageFilter = ImageTk = None

try:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
except ImportError:
    BitmapDecoder = DataWriter = InMemoryRandomAccessStream = OcrEngine = None

OCR_AVAILABLE = all((BitmapDecoder, DataWriter, InMemoryRandomAccessStream, OcrEngine))

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp_hex(a, b, t):
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


FONT_DIR = os.path.dirname(os.path.abspath(__file__))


def font_family_name(path):
    """Reads the family name stored inside a font file. Windows matches fonts by this
    name, which can differ from the file name."""
    with open(path, "rb") as f:
        data = f.read()
    num_tables = struct.unpack(">H", data[4:6])[0]
    name_offset = None
    for i in range(num_tables):
        rec = 12 + 16 * i
        if data[rec:rec + 4] == b"name":
            name_offset = struct.unpack(">I", data[rec + 8:rec + 12])[0]
            break
    if name_offset is None:
        return None
    count, string_offset = struct.unpack(">HH", data[name_offset + 2:name_offset + 6])
    found = {}
    for i in range(count):
        p = name_offset + 6 + 12 * i
        platform, _enc, _lang, name_id, length, offset = struct.unpack(">HHHHHH",
                                                                       data[p:p + 12])
        if platform not in (1, 3) or name_id not in (1, 16):
            continue
        start = name_offset + string_offset + offset
        raw = data[start:start + length]
        text = raw.decode("utf-16-be" if platform == 3 else "mac_roman",
                          errors="ignore").strip()
        if platform == 3 or name_id not in found:
            found[name_id] = text
    return found.get(1) or found.get(16)


def load_huninn():
    """Loads a Huninn font file from the script's folder for this app only.
    Returns the family name Tk should use, or None."""
    try:
        gdi32 = ctypes.windll.gdi32
        for name in sorted(os.listdir(FONT_DIR)):
            low = name.lower()
            if "huninn" in low and low.endswith((".ttf", ".otf")):
                path = os.path.join(FONT_DIR, name)
                if gdi32.AddFontResourceExW(path, 0x10, 0):
                    return font_family_name(path)
    except Exception:
        pass
    return None


FONT_FAMILY = load_huninn() or "Helvetica"

APP_TITLE = "dinguschan's Bloxd Automation Toolkit"
DEFAULT_GROUP = "Simultaneous"
DEFAULT_PROFILE_NAME = "Default Profile"
LEGACY_DEFAULT_PROFILE_NAME = "Default"
PROFILE_VERSION = 2
PROFILE_AUTOSAVE_INTERVAL_MS = 500
DELAY_SECONDS = 3
TILES_PER_SECOND = 4
TILE_SECONDS = 1 / TILES_PER_SECOND
DEFAULT_GRID = 10
MAX_GRID_SIZE = 50
MIN_GRID_CELL_PX = 18
GRID_VIEWPORT_PX = 460
TAP_SECONDS = 0.02
MAX_PATTERN_STEPS = 8
MAX_INPUT_BLOCKS = 12
LOOK_TICK = 0.01
LOOK_PIXELS_PER_TICK = 12
LOOK_SETTLE_SECONDS = 0.3
MISS_RETRY_SECONDS = 0.1
MAX_MISSES = 15
SEARCH_FRACTION = 0.8
DETECT_SCALE = 2
MIN_BLOB_PIXELS = 30
MAX_FILL_RATIO = 0.5
MAX_INNER_LIT = 0.5
INNER_RADIUS_RATIO = 0.3
THRESHOLD_STEP = 15
THRESHOLD_FLOOR = 100
SIZE_TOLERANCE = 0.50
TRACK_FRACTION = 0.25
READ_SAMPLES = 3
READ_SAMPLE_GAP = 0.04
ALIGN_PROBE_PX = 60
ALIGN_MIN_CHANGE = 0.05
ALIGN_SAFETY = 0.8
ALIGN_MIN_PX = 1
ALIGN_MAX_PX = 200
ALIGN_CHUNK_PX = 1
ALIGN_MAX_STEPS = 40
STABLE_READS = 2
CAL_TAP_SECONDS = 0.12
CHANGE_MIN_PX = 2
POS_SAFETY = 0.6
POS_MIN_TAP = 0.015
SPIN_MAX_SPEED = 15000
MOUSE_STREAM_TICK = 0.001
GRID_WHEEL_SCROLL_UNITS = 30
SCROLL_STEP_PX = 24

AUTOEAT_SLOT_ORDER = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")
DEFAULT_SCREEN_POLL_INTERVAL_MS = 50
MIN_SCREEN_POLL_INTERVAL_MS = 10
MAX_SCREEN_POLL_INTERVAL_MS = 1000
HOTBAR_SLOT_COUNT = 10
HOTBAR_DEFAULT_THRESHOLD = 5
HOTBAR_ALERT_INFERRED_ITEM_READS = 3
HOTBAR_ALERT_CLEAR_READS = 3
HOTBAR_ALERT_STATUS_CONFIRM_READS = 2
AUTOFISH_CLICK_INTERVAL_SECONDS = 0.125
AUTOFISH_RECAST_SETTLE_SECONDS = 0.1
AUTOFISH_CLEAR_CONFIRM_READS = 3
AUTOFISH_ROD_SWAP_SETTLE_SECONDS = 0.3
AUTOFISH_FLARE_THROW_SECONDS = 0.4
AUTOFISH_TURN_PIXELS_PER_SECOND = 1200
SPOT_MAX_PX = 3000
SPOT_VERTICAL_MAX_PX = 400


def parse_vertical_range(min_text, max_text, limit_text):
    """Returns (minimum, maximum, drift limit) for the up-or-down change, in whole pixels. A maximum
    of 0 turns the change off. Raises ValueError for anything else out of range."""
    high = int(max_text)
    if high == 0:
        return 0, 0, 0
    low, limit = int(min_text), int(limit_text)
    if not 1 <= low <= high <= SPOT_VERTICAL_MAX_PX or not low <= limit <= SPOT_VERTICAL_MAX_PX:
        raise ValueError
    return low, high, limit


def parse_no_bite_timeout(text):
    """Returns how many seconds to wait for a bite before recasting, from 10 to 300, or raises
    ValueError."""
    seconds = int(text)
    if not 10 <= seconds <= 300:
        raise ValueError
    return seconds


def parse_flare_interval(text):
    """Returns the seconds between Glowtide Flare throws, from 10 to 3600, or raises ValueError."""
    seconds = int(text)
    if not 10 <= seconds <= 3600:
        raise ValueError
    return seconds


def parse_spot_range(min_text, max_text, limit_text):
    """Returns (minimum, maximum, drift limit) whole-pixel amounts for switching spots, or raises
    ValueError. The drift limit is how far the view may end up from its starting heading."""
    low, high, limit = int(min_text), int(max_text), int(limit_text)
    if not 1 <= low <= high <= SPOT_MAX_PX or not low <= limit <= SPOT_MAX_PX:
        raise ValueError
    return low, high, limit
AUTOEAT_SLOT_SETTLE_SECONDS = 0.1
AUTOEAT_EMPTY_EDGE_THRESHOLD = 2.0
TRACKING_PAD_X_LINES = 12
TRACKING_PAD_Y_LINES = 4

HORIZ_POS_KEY = 0x44
HORIZ_NEG_KEY = 0x41
VERT_POS_KEY = 0x53
VERT_NEG_KEY = 0x57

ACT_TAP = "Tap Key"
ACT_DOWN = "Key Down"
ACT_UP = "Key Up"
ACT_LEFT = "Left Click"
ACT_MIDDLE = "Middle Click"
ACT_RIGHT = "Right Click"
ACT_PAUSE = "Pause"
ACT_CAMERA = "Turn Camera"
PATTERN_ACTIONS = [
    ACT_TAP, ACT_DOWN, ACT_UP, ACT_LEFT, ACT_MIDDLE, ACT_RIGHT, ACT_PAUSE, ACT_CAMERA,
]
PATTERN_CLICK_OPTIONS = ("None", "Left", "Middle", "Right")
PATTERN_CAMERA_DIRECTIONS = ("Clockwise", "Counterclockwise")
PATTERN_CAMERA_DEFAULT_PIXELS = "100"
PATTERN_CAMERA_MAX_PIXELS = 2_147_483_647
INPUT_BLOCKER_TYPES = ("Key", "Mouse button")
KEY_ACTIONS = (ACT_TAP, ACT_DOWN, ACT_UP)

DEFAULT_PATTERN = [
    (ACT_DOWN, "w", 0.0),
    (ACT_TAP, "space", 0.02),
    (ACT_RIGHT, "", 10.98),
]

EXCLUSIVE_GROUPS = ("Independent", "Run Once")
GROUP_TAGS = {"Simultaneous": "S", "Independent": "I", "Run Once": "R", "EXTRAS": "E"}

GROUP_INFO = {
    "Simultaneous": "Runs alongside any number of Simultaneous tools and one Independent "
                    "tool. Cannot run alongside Run Once tools.",
    "Independent": "Runs alongside any number of Simultaneous tools, but only one "
                   "Independent tool can run at a time. Cannot run alongside Run Once tools.",
    "Run Once": "Runs once from start to finish, then turns off. Cannot run alongside "
                "Simultaneous, Independent, or other Run Once tools.",
    "EXTRAS": "Utility pages and on-screen overlays. These modules do not run tools.",
}

TYPE_CATEGORY_ORDER = ("Combat", "Automation", "Overlays", "Misc")
TYPE_CATEGORY_INFO = {
    "Combat": "Tools for combat-related actions.",
    "Automation": "Tools that automate movement, input, and routine actions.",
    "Overlays": "On-screen visualizers and status displays.",
    "Misc": "Utility tools that do not fit the other types.",
}
MODULE_TYPE_BY_NAME = {
    "Autoeat": "Combat",
    "Autosprint": "Combat",
    "Clicks": "Combat",
    "Hotbar Alert": "Combat",
    "Autofish": "Automation",
    "Grid Path": "Automation",
    "Keys": "Automation",
    "Pattern": "Automation",
    "Anti AFK": "Automation",
    "Active Modules": "Overlays",
    "CPS": "Overlays",
    "Keyboard Visualizer": "Overlays",
    "Mouse Visualizer": "Overlays",
    "Input Blocker": "Misc",
    "Coordinates": "Misc",
    "Spin": "Misc",
    "Align": "Misc",
    "Center": "Misc",
}

START_SELECTED_DESCRIPTION = (
    "Starts the checked Simultaneous tools and at most one Independent tool together after "
    "one countdown. Run Once tools are not included; start them from their own page only "
    "when no other tool is running. Stop here stops tools started by this page. Individual "
    "tool delays are ignored.")

DEFAULT_GREEN = "#42d499"
DEFAULT_GROUP_TAG_COLOR = "#8f4cf5"
DEFAULT_RED = "#e5484d"
GREEN = DEFAULT_GREEN
YELLOW = "#e8b339"
RED = DEFAULT_RED
ON_GREEN = "#06130d"
ON_YELLOW = "#1a1400"
ON_RED = "#ffffff"
RESET_BUTTON_FG = "#ffffff"

BG = "#121212"
HEADER_BG = "#181c1b"
SIDEBAR = "#171717"
NAV_HOVER = "#1f1f1f"
PANEL = "#1c1c1c"
INPUT = "#262626"
DISABLED_BG = "#202020"
DISABLED_FG = "#4f4f4f"
BORDER = "#5a5a5a"
OVERLAY_TRANSPARENT = "#010203"
OVERLAY_POSITIONS = ("Top left", "Top right", "Bottom left", "Bottom right")
OVERLAY_STACK_GAP = 8
OFF_BG = "#2a2a2a"
OFF_HOVER = "#333333"
TEXT = "#e6e6e6"
MUTED = "#8b8b8b"

GREEN_HOVER = lerp_hex(GREEN, "#ffffff", 0.18)
YELLOW_HOVER = lerp_hex(YELLOW, "#ffffff", 0.18)
RED_HOVER = lerp_hex(RED, "#ffffff", 0.15)
GREEN_DIM = lerp_hex(GREEN, BG, 0.5)
GROUP_TAG_COLOR = DEFAULT_GROUP_TAG_COLOR


def valid_hex_color(value):
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


def text_color_for(color):
    channels = [component / 255 for component in hex_to_rgb(color)]
    linear = [
        channel / 12.92 if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    return "#06130d" if luminance > 0.179 else "#ffffff"


def set_theme_palette(accent, group_color, red_color):
    global GREEN, GREEN_HOVER, GREEN_DIM, ON_GREEN, GROUP_TAG_COLOR
    global RED, RED_HOVER, ON_RED
    previous = (GREEN, GREEN_HOVER, GREEN_DIM, ON_GREEN, GROUP_TAG_COLOR,
                RED, RED_HOVER, ON_RED)
    GREEN = accent
    GREEN_HOVER = lerp_hex(GREEN, "#ffffff", 0.18)
    GREEN_DIM = lerp_hex(GREEN, BG, 0.5)
    ON_GREEN = text_color_for(GREEN)
    GROUP_TAG_COLOR = group_color
    RED = red_color
    RED_HOVER = lerp_hex(RED, "#ffffff", 0.15)
    ON_RED = text_color_for(RED)
    current = (GREEN, GREEN_HOVER, GREEN_DIM, ON_GREEN, GROUP_TAG_COLOR,
               RED, RED_HOVER, ON_RED)
    return dict(zip(previous, current))


def set_windows_titlebar_colors(window, background, foreground):
    get_ancestor = ctypes.windll.user32.GetAncestor
    get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
    get_ancestor.restype = wintypes.HWND
    hwnd = get_ancestor(wintypes.HWND(window.winfo_id()), 2)
    if not hwnd:
        raise OSError("Could not find the Windows title bar handle.")

    set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
    set_attribute.argtypes = (
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
    set_attribute.restype = ctypes.c_long

    def apply(attribute, value):
        value = ctypes.c_uint32(value)
        result = set_attribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
        if result < 0:
            return result
        return 0

    result = apply(20, 1)
    if result < 0:
        result = apply(19, 1)
    if result < 0:
        raise OSError(f"Could not enable the dark title bar (HRESULT 0x{result & 0xFFFFFFFF:08X}).")

    def colorref(color):
        red, green, blue = hex_to_rgb(color)
        return red | (green << 8) | (blue << 16)

    for attribute, color in ((35, background), (36, foreground)):
        result = apply(attribute, colorref(color))
        if result < 0:
            raise OSError(
                f"Could not set the title bar color (HRESULT 0x{result & 0xFFFFFFFF:08X}).")

RADIUS_BTN = 9
RADIUS_FIELD = 7
RADIUS_CARD = 12

FONT_HEAD = (FONT_FAMILY, 12, "bold")
FONT_TITLE = (FONT_FAMILY, 13, "bold")
FONT_BUTTON = (FONT_FAMILY, 10, "bold")
FONT_NAV = (FONT_FAMILY, 10)
FONT_BODY = (FONT_FAMILY, 10)
FONT_SMALL = (FONT_FAMILY, 9)

user32 = ctypes.windll.user32
try:
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
KEYEVENTF_KEYUP = 0x0002
VK_SPACE = 0x20
VK_SHIFT = 0x10
VK_C = 0x43
VK_W = 0x57
VK_A = 0x41
VK_S = 0x53
VK_D = 0x44
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04
VK_OEM_3 = 0xC0

BUTTON_FLAGS = {
    "Left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "Middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    "Right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t))


class INPUTUNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT),)


class WinInput(ctypes.Structure):
    _fields_ = (("type", ctypes.c_ulong),
                ("union", INPUTUNION))


user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(WinInput), ctypes.c_int)
user32.SendInput.restype = ctypes.c_uint

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
KEYBOARD_MESSAGES = {WM_KEYDOWN, WM_SYSKEYDOWN}
MOUSE_MESSAGES = {
    "Left": {WM_LBUTTONDOWN},
    "Right": {WM_RBUTTONDOWN},
    "Middle": {WM_MBUTTONDOWN},
}
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                              ctypes.c_size_t, ctypes.c_ssize_t)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t))


user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD)
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = (
    ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, wintypes.UINT, wintypes.UINT)
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = ctypes.c_ssize_t
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = (
    ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.PeekMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
    wintypes.UINT)
user32.PeekMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostThreadMessageW.restype = wintypes.BOOL
ctypes.windll.kernel32.GetCurrentThreadId.restype = wintypes.DWORD
ctypes.windll.kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
ctypes.windll.kernel32.GetModuleHandleW.restype = ctypes.c_void_p


def move_rel(dx, dy):
    """Send relative movement with SendInput, which is steadier than mouse_event for games."""
    mouse = MOUSEINPUT(int(dx), int(dy), 0, MOUSEEVENTF_MOVE, 0, 0)
    inp = WinInput(0, INPUTUNION(mi=mouse))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def stream_mouse(dx, dy, pixels_per_second, alive=None):
    """Send axis-aligned movement at a steady rate, batching pixels per input event."""
    remaining_x = abs(int(round(dx)))
    remaining_y = abs(int(round(dy)))
    sx = 0 if remaining_x == 0 else (1 if dx > 0 else -1)
    sy = 0 if remaining_y == 0 else (1 if dy > 0 else -1)
    remaining = remaining_x + remaining_y
    if remaining == 0:
        return True
    pending = 0.0
    last = time.perf_counter()
    speed = max(1.0, float(pixels_per_second))
    while remaining > 0:
        if alive is not None and not alive():
            return False
        now = time.perf_counter()
        pending += speed * (now - last)
        last = now
        n = min(remaining, int(pending))
        if n:
            pending -= n
            remaining -= n
            move_rel(sx * n, sy * n)
        else:
            delay = MOUSE_STREAM_TICK - (time.perf_counter() - now)
            if delay > 0:
                time.sleep(delay)
    return True

SPECIAL_KEYS = {
    "backspace": 0x08,
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "pause": 0x13, "caps lock": 0x14, "page up": 0x21, "page down": 0x22,
    "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27,
    "down": 0x28, "insert": 0x2D, "delete": 0x2E,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "f11": 0x7A, "f12": 0x7B,
}

MOVE_KEYS = [VK_W, VK_A, VK_S, VK_D]


def screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def button_down(name):
    user32.mouse_event(BUTTON_FLAGS[name][0], 0, 0, 0, 0)


def button_up(name):
    user32.mouse_event(BUTTON_FLAGS[name][1], 0, 0, 0, 0)


def button_click(name):
    button_down(name)
    button_up(name)


def key_down(vk):
    user32.keybd_event(vk, 0, 0, 0)


def key_up(vk):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def tap_key(vk):
    key_down(vk)
    try:
        time.sleep(0.03)
    finally:
        key_up(vk)


def tilde_pressed():
    return bool(user32.GetAsyncKeyState(VK_OEM_3) & 0x8000
                and user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)


def parse_key(text):
    """Turns a single character or a special key name into a Windows key code."""
    t = text.strip().casefold()
    if len(t) == 1:
        result = user32.VkKeyScanW(ord(t))
        return None if result == -1 else result & 0xFF
    return SPECIAL_KEYS.get(t)


def parse_screen_poll_interval(value):
    interval_ms = int(value)
    if not MIN_SCREEN_POLL_INTERVAL_MS <= interval_ms <= MAX_SCREEN_POLL_INTERVAL_MS:
        raise ValueError
    return interval_ms / 1000


def parse_grid_space_pause(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError
    return seconds


def parse_pattern_camera_pixels(value):
    pixels = int(value)
    if not 1 <= pixels <= PATTERN_CAMERA_MAX_PIXELS:
        raise ValueError
    return pixels


def parse_hotbar_slots(value, slot_options):
    slots = tuple(dict.fromkeys(slot.strip() for slot in value.split(",")))
    if not slots or any(slot not in slot_options for slot in slots):
        raise ValueError
    return slots


def key_display(text):
    """Display form of a key name: E, Space, Enter."""
    t = text.strip()
    return t.upper() if len(t) == 1 else t.title()


def grab_search_area(cross):
    """Captures an area around the crosshair. Returns (image, left, top).

    The area is centered on the crosshair and kept inside the screen, so the square is
    searched for where the game actually draws the crosshair, not just the middle of the
    monitor."""
    sw, sh = screen_size()
    half_w = sw * SEARCH_FRACTION / 2
    half_h = sh * SEARCH_FRACTION / 2
    left = max(0, int(cross[0] - half_w))
    right = min(sw, int(cross[0] + half_w))
    top = max(0, int(cross[1] - half_h))
    bottom = min(sh, int(cross[1] + half_h))
    shot = screen_grab((left, top, right, bottom)).convert("L")
    return shot, left, top


class OcrRect:
    """A text box in pixels, with the same fields the OCR results have always used."""

    def __init__(self, x, y, width, height):
        self.x, self.y, self.width, self.height = x, y, width, height


class OcrWord:
    def __init__(self, text, bounding_rect):
        self.text = text
        self.bounding_rect = bounding_rect


class OcrLine:
    """One line of text read from the screen. Its words carry the same text as one box."""

    def __init__(self, text, words):
        self.text = text
        self.words = words


_OCR_ENGINE = None
_OCR_LOCK = threading.Lock()


def get_ocr_engine():
    """Creates the shared Windows OCR engine on first use."""
    global _OCR_ENGINE
    with _OCR_LOCK:
        if _OCR_ENGINE is None:
            if not OCR_AVAILABLE:
                raise RuntimeError("Windows OCR support is unavailable in this Python environment.")
            _OCR_ENGINE = OcrEngine.try_create_from_user_profile_languages()
            if _OCR_ENGINE is None:
                raise RuntimeError(
                    "Windows OCR couldn't be initialized. Install a supported OCR language "
                    "in Windows Settings.")
        return _OCR_ENGINE


async def recognize_ocr_lines(image, engine):
    """Uses Windows OCR to read text and image-relative word bounds from a PIL image."""
    encoded_image = io.BytesIO()
    image.save(encoded_image, format="PNG")
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(encoded_image.getvalue())
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)
    lines = []
    for recognized_line in result.lines:
        words = []
        for recognized_word in recognized_line.words:
            bounds = recognized_word.bounding_rect
            rect = OcrRect(bounds.x, bounds.y, bounds.width, bounds.height)
            words.append(OcrWord(recognized_word.text, rect))
        lines.append(OcrLine(recognized_line.text, words))
    return lines


def screen_grab(box=None):
    """Captures the screen or the given (left, top, right, bottom) box with Pillow."""
    if box is None:
        return ImageGrab.grab()
    return ImageGrab.grab(bbox=box)


def grab_screen(box=None):
    """Captures the whole screen (box is None) or one box of it. Returns (image, origin),
    where origin is the screen position of the image's top-left corner."""
    if box is None:
        return screen_grab(), (0, 0)
    return screen_grab(box), (box[0], box[1])


async def read_hotbar_quantity(slot_image, engine):
    """Reads the stack count from the lower-right of one captured slot."""
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    nearest = getattr(Image, "Resampling", Image).NEAREST

    async def read_crop(crop, scale, min_x_ratio=0.3, min_y_ratio=0.5,
                        resize_filter=None):
        enlarged = crop.resize((crop.width * scale, crop.height * scale),
                               resampling if resize_filter is None else resize_filter)
        lines = await recognize_ocr_lines(enlarged, engine)
        quantities = []
        for line in lines:
            for word in line.words:
                match = re.search(r"\d+", word.text)
                if match:
                    rect = word.bounding_rect
                    if (rect.x >= enlarged.width * min_x_ratio
                            and rect.y >= enlarged.height * min_y_ratio):
                        quantities.append((rect.y, rect.x, int(match.group())))
        return max(quantities)[2] if quantities else None

    quantity = await read_crop(slot_image, 2)
    high_resolution_quantity = await read_crop(
        slot_image, 4, resize_filter=nearest)
    if high_resolution_quantity is not None:
        if quantity is None or high_resolution_quantity == quantity:
            return high_resolution_quantity
        confirmation = await read_crop(slot_image, 6, resize_filter=nearest)
        if confirmation == quantity:
            return confirmation
        return high_resolution_quantity
    if quantity is not None and slot_image.width >= 55:
        return quantity
    if quantity is None:
        quantity = await read_crop(slot_image, 2, resize_filter=nearest)
        if quantity is not None:
            return quantity
    lower_right = slot_image.crop((round(slot_image.width * 0.3),
                                   round(slot_image.height * 0.35),
                                   slot_image.width, slot_image.height))
    fallback = await read_crop(lower_right, 4, 0.05, 0.05)
    best = quantity
    if fallback is not None and (best is None or len(str(fallback)) > len(str(best))):
        best = fallback
    if slot_image.width < 55 and (best is None or fallback is None):
        lower_right = slot_image.crop((round(slot_image.width * 0.4),
                                       round(slot_image.height * 0.4),
                                       slot_image.width, slot_image.height))
        secondary = await read_crop(lower_right, 5, 0, 0, nearest)
        if secondary is not None and (
                best is None or len(str(secondary)) > len(str(best))):
            best = secondary
    return best


async def read_hotbar_quantities_from_row(
        row_image, engine, first_slot_left, slot_width, wanted_slots):
    """Reads stack counts from a thresholded image of the whole hotbar row."""
    scale = 2
    wanted_slots = set(wanted_slots)
    quantities = {}
    nearest = getattr(Image, "Resampling", Image).NEAREST
    for threshold in (220, 160):
        binary = row_image.convert("L").point(
            lambda value, limit=threshold: 255 if value > limit else 0)
        enlarged = binary.resize((binary.width * scale, binary.height * scale), nearest)
        for line in await recognize_ocr_lines(enlarged, engine):
            for word in line.words:
                match = re.search(r"\d+", word.text)
                if match:
                    rect = word.bounding_rect
                    slot_offset = rect.x / scale + rect.width / (2 * scale) - first_slot_left
                    slot_index = int(slot_offset // slot_width)
                    if (slot_index in wanted_slots and slot_index not in quantities
                            and rect.y >= enlarged.height * 0.35):
                        quantities[slot_index] = int(match.group())
        if wanted_slots.issubset(quantities):
            break
    return quantities


def hotbar_slot_has_item(slot_image):
    """Distinguishes an empty slot from a single-item slot with no displayed count."""
    left = round(slot_image.width * 0.5)
    top = round(slot_image.height * 0.35)
    right = round(slot_image.width * 0.9)
    bottom = round(slot_image.height * 0.9)
    inner = slot_image.crop((left, top, right, bottom)).convert("L")
    edges = inner.filter(ImageFilter.FIND_EDGES)
    histogram = edges.crop((1, 1, edges.width - 1, edges.height - 1)).histogram()
    edge_average = sum(value * count for value, count in enumerate(histogram))
    return edge_average / sum(histogram) >= 4


def clamp_to_screen(box):
    screen_w, screen_h = screen_size()
    left, top, right, bottom = box
    return (max(0, round(left)), max(0, round(top)),
            min(screen_w, round(right)), min(screen_h, round(bottom)))


def union_box(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def offset_box(box, origin):
    ox, oy = origin
    return (box[0] + ox, box[1] + oy, box[2] + ox, box[3] + oy)


def ocr_line_box(line):
    rects = [word.bounding_rect for word in line.words]
    return (min(r.x for r in rects), min(r.y for r in rects),
            max(r.x + r.width for r in rects), max(r.y + r.height for r in rects))


def tracking_box(boxes, text_height):
    """The area the next read looks in: the given boxes plus generous padding measured in text
    heights, so the text stays inside it when it shifts a little. Returns None if unusable."""
    text_height = max(1, text_height)
    left, top, right, bottom = union_box(boxes)
    pad_x = text_height * TRACKING_PAD_X_LINES
    pad_y = text_height * TRACKING_PAD_Y_LINES
    box = clamp_to_screen((left - pad_x, top - pad_y, right + pad_x, bottom + pad_y))
    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
        return None
    return box


async def read_auto_eat_hud(shot, engine, origin=(0, 0)):
    """Finds the health text and its bar in a captured image whose top-left corner sits at
    origin on screen. Returns (health, max_health, health_bar, text_box) with both boxes in
    screen coordinates, or None if no health reading is in the image."""
    rgb = shot if shot.mode == "RGB" else shot.convert("RGB")
    candidates = []
    for line in await recognize_ocr_lines(shot, engine):
        health_values = parse_auto_eat_health(line.text)
        if health_values is None or not line.words:
            continue
        health, max_health = health_values
        text_box = ocr_line_box(line)
        health_bar = find_auto_eat_health_bar(rgb, text_box)
        if health_bar is not None:
            candidates.append((health, max_health, health_bar, text_box))
    if not candidates:
        return None
    health, max_health, health_bar, text_box = max(
        candidates, key=lambda item: item[2][2] - item[2][0])
    return (health, max_health, offset_box(health_bar, origin),
            offset_box(text_box, origin))


def is_autofish_notification(text):
    words = re.findall(r"[a-z]+", text.lower())
    has_click = any(word.startswith("click") for word in words)
    has_reel_instruction = ("reel" in words
                            and (has_click or "repeatedly" in words))
    has_bite_notice = (any(word.endswith("biting") for word in words)
                       and has_click
                       and bool({"fish", "rare", "special"}.intersection(words)))
    return has_reel_instruction or has_bite_notice


def is_notice_word(word):
    """True for the words that make up the bite notice, so its lines can be tracked."""
    return (word.startswith("click") or word.endswith("biting")
            or word in ("reel", "repeatedly", "fish", "rare", "special"))


async def find_autofish_notice(shot, engine, origin=(0, 0)):
    """Looks for the bite notice in a captured image whose top-left corner sits at origin on
    screen. Returns (boxes, text_height) in screen coordinates, or None if it isn't there."""
    lines = await recognize_ocr_lines(shot, engine)
    if not is_autofish_notification(" ".join(line.text for line in lines)):
        return None
    relevant = [line for line in lines if line.words and any(
        is_notice_word(word) for word in re.findall(r"[a-z]+", line.text.lower()))]
    if not relevant:
        relevant = [line for line in lines if line.words]
    if not relevant:
        return None
    boxes = [offset_box(ocr_line_box(line), origin) for line in relevant]
    text_height = max(box[3] - box[1] for box in boxes)
    return boxes, text_height


def parse_auto_eat_health(text):
    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    return (int(match.group(1)), int(match.group(2))) if match else None


def find_auto_eat_health_bar(shot, text_box):
    left, top, right, bottom = text_box
    text_height = max(1, round(bottom - top))
    center_x = round((left + right) / 2)
    center_y = round((top + bottom) / 2)
    band_top = max(0, center_y - round(text_height * 2.2))
    band_bottom = min(shot.height, center_y + round(text_height * 2.2))
    search_left = max(0, center_x - text_height * 12)
    search_right = min(shot.width, center_x + text_height * 12)
    pixels = shot.load()

    red_counts = []
    minimum_count = max(2, round((band_bottom - band_top) * 0.14))
    for x in range(search_left, search_right):
        red_count = 0
        for y in range(band_top, band_bottom):
            red, green, blue = pixels[x, y]
            if red > 50 and red > green * 1.4 and red > blue * 1.4:
                red_count += 1
        red_counts.append(red_count)

    runs = []
    run_start = None
    for offset, count in enumerate(red_counts + [0]):
        x = search_left + offset
        if count >= minimum_count and run_start is None:
            run_start = x
        elif count < minimum_count and run_start is not None:
            if (x - run_start >= text_height * 7
                    and run_start < right and x > left):
                runs.append((run_start, x))
            run_start = None
    if not runs:
        return None


    bar_left, bar_right = max(
        runs, key=lambda run: min(run[1], right) - max(run[0], left))
    bar_height = text_height * 3
    bar_top = max(0, round(center_y - text_height * 1.65))
    bar_bottom = min(shot.height, bar_top + bar_height)
    return bar_left, bar_top, bar_right, bar_bottom


def find_hotbar_grid_near(image, expected_top, expected_step, expected_slot_size,
                          health_bar_bottom):
    """Finds the screen-centered hotbar borders below the health bar."""
    width, height = image.size
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES).load()
    best = None
    step_min = max(36, round(expected_step * 0.84))
    step_max = min(110, round(expected_step * 1.16))
    x_radius = max(8, round(expected_slot_size * 0.4))
    y_radius = max(6, round(expected_slot_size * 0.4))

    for step in range(step_min, step_max + 1, 2):
        centered_left = (width - HOTBAR_SLOT_COUNT * step) / 2
        x_low = max(2, round(centered_left - x_radius))
        x_high = min(width - HOTBAR_SLOT_COUNT * step - 3,
                     round(centered_left + x_radius))
        top_low = max(2, round(health_bar_bottom))
        top_high = min(height - step - 3, round(expected_top + y_radius))
        for top in range(top_low, top_high + 1, 2):
            for left in range(x_low, x_high + 1, max(2, step // 25)):
                vertical = []
                for index in range(HOTBAR_SLOT_COUNT + 1):
                    x = left + index * step
                    samples = [
                        max(edges[edge_x, y]
                            for edge_x in range(x - 2, x + 3))
                        for y in range(top + 5, top + step - 5, 6)
                    ]
                    vertical.append(sum(samples) / len(samples))

                horizontal = []
                for y in (top, top + step):
                    samples = [
                        max(edges[x, edge_y] for edge_y in range(y - 2, y + 3))
                        for x in range(left + 5, left + HOTBAR_SLOT_COUNT * step - 5, 8)
                    ]
                    horizontal.append(sum(samples) / len(samples))

                score = sum(vertical) / len(vertical) + sum(horizontal) / 2
                if best is None or score > best[0]:
                    best = (score, left, top, step, vertical, horizontal)

    if best is None:
        return None
    score, left, top, step, vertical, horizontal = best
    if (score < 65 or sum(value >= 25 for value in vertical) < 10
            or min(horizontal) < 20):
        return None
    return left - 1, top, step


def hotbar_slot_center(slot_index, health_bar):
    bar_top, bar_right, bar_bottom = health_bar[1:]
    slot_size = (bar_bottom - bar_top) * 1.55
    center_x = round(bar_right - slot_size * 0.62
                     - (len(AUTOEAT_SLOT_ORDER) - 1 - slot_index) * slot_size * 1.06)
    center_y = round(bar_bottom + slot_size * 0.62)
    return center_x, center_y, slot_size


def auto_eat_slot_is_empty(slot, health_bar):
    """Detects a blank hotbar slot from its flat interior, independent of its color.
    Captures only the slot itself, so it doesn't depend on what the health tracker is using."""
    slot_index = AUTOEAT_SLOT_ORDER.index(slot)
    center_x, center_y, slot_size = hotbar_slot_center(slot_index, health_bar)
    screen_w, screen_h = screen_size()
    half = max(2, round(slot_size * 0.32))
    left, top = max(0, center_x - half), max(0, center_y - half)
    right, bottom = min(screen_w, center_x + half), min(screen_h, center_y + half)
    if right <= left or bottom <= top:
        return True
    crop = screen_grab((left, top, right, bottom)).convert("L")
    pixels = crop.tobytes()
    crop_width, crop_height = crop.size
    edge_total = 0
    for y in range(crop_height):
        row = y * crop_width
        edge_total += sum(abs(pixels[row + x] - pixels[row + x + 1])
                          for x in range(crop_width - 1))
    for y in range(crop_height - 1):
        row = y * crop_width
        next_row = row + crop_width
        edge_total += sum(abs(pixels[row + x] - pixels[next_row + x])
                          for x in range(crop_width))
    edge_count = crop_height * (crop_width - 1) + (crop_height - 1) * crop_width
    return edge_count == 0 or edge_total / edge_count <= AUTOEAT_EMPTY_EDGE_THRESHOLD


def wrap45(deg):
    """Maps an angle difference into [-45, 45). A square looks the same every 90 degrees."""
    return ((deg + 45.0) % 90.0) - 45.0


def min_rect_tilt(xs, ys):
    """Finds how far a set of points is rotated, using the smallest bounding rectangle.

    Searches for the smallest bounding rectangle, then refines the best angle in 0.05-degree
    increments. For a square this happens when its edges line up with the rectangle, so the
    returned tilt is 0 when the square is upright. Returns (tilt_degrees, side_length), in
    the same units as the input.
    """
    def rectangle(deg):
        a = math.radians(deg)
        c = math.cos(a)
        s = math.sin(a)
        us = [x * c + y * s for x, y in zip(xs, ys)]
        vs = [-x * s + y * c for x, y in zip(xs, ys)]
        width = max(us) - min(us)
        height = max(vs) - min(vs)
        return width * height, width, height

    best_area = None
    best_angle = 0.0
    best_size = 0.0
    for deg in range(-45, 45):
        area, width, height = rectangle(float(deg))
        if best_area is None or area < best_area:
            best_area = area
            best_angle = float(deg)
            best_size = (width + height) / 2

    coarse_angle = best_angle
    for step in range(-20, 21):
        angle = coarse_angle + step * 0.05
        area, width, height = rectangle(angle)
        if area < best_area:
            best_area = area
            best_angle = angle
            best_size = (width + height) / 2

    return wrap45(best_angle), best_size


def find_outlines(shot, left, top, threshold):
    """Finds square-shaped outlines at one brightness level.

    An outline is a bright ring with a mostly dark inside. Text, tile edges, and bright
    filled shapes are rejected. Each result records the square's center (from its geometric
    bounds), its tilt (0 when upright), and its side length.

    Each box is (x0, y0, x1, y1, cx, cy, tilt, side) in screen coordinates.
    """
    small = shot.reduce(DETECT_SCALE)
    mask = small.point(lambda p: 255 if p >= threshold else 0)
    mask = mask.filter(ImageFilter.MaxFilter(3))
    w, h = mask.size
    px = mask.tobytes()
    seen = bytearray(w * h)

    boxes = []

    for start in range(w * h):
        if not px[start] or seen[start]:
            continue
        seen[start] = 1
        stack = [start]
        pts = []
        minx = maxx = start % w
        miny = maxy = start // w
        while stack:
            i = stack.pop()
            pts.append(i)
            x = i % w
            y = i // w
            if x < minx:
                minx = x
            if x > maxx:
                maxx = x
            if y < miny:
                miny = y
            if y > maxy:
                maxy = y
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    j = ny * w + nx
                    if px[j] and not seen[j]:
                        seen[j] = 1
                        stack.append(j)

        count = len(pts)
        bw = maxx - minx + 1
        bh = maxy - miny + 1
        if count < MIN_BLOB_PIXELS or bw < 6 or bh < 6:
            continue
        if not 0.5 <= bw / bh <= 2.0:
            continue
        if count / (bw * bh) > MAX_FILL_RATIO:
            continue

        cxs = (minx + maxx) / 2
        cys = (miny + maxy) / 2

        radius = INNER_RADIUS_RATIO * min(bw, bh)
        inner_total = inner_lit = 0
        for y in range(miny, maxy + 1):
            for x in range(minx, maxx + 1):
                if (x - cxs) ** 2 + (y - cys) ** 2 <= radius * radius:
                    inner_total += 1
                    inner_lit += 1 if px[y * w + x] else 0
        if inner_total and inner_lit / inner_total > MAX_INNER_LIT:
            continue

        step = max(1, count // 300)
        sample = pts[::step]
        xs = [(i % w) + 0.5 for i in sample]
        ys = [(i // w) + 0.5 for i in sample]
        tilt, side_small = min_rect_tilt(xs, ys)

        boxes.append((left + minx * DETECT_SCALE, top + miny * DETECT_SCALE,
                      left + (maxx + 1) * DETECT_SCALE, top + (maxy + 1) * DETECT_SCALE,
                      left + (cxs + 0.5) * DETECT_SCALE, top + (cys + 0.5) * DETECT_SCALE,
                      tilt, side_small * DETECT_SCALE))

    return boxes


def detect_squares(base_threshold, cross):
    """Finds square outlines around the crosshair, trying brightness levels downward."""
    if ImageGrab is None:
        raise RuntimeError("Pillow is not installed for screen capture.")
    try:
        shot, left, top = grab_search_area(cross)
    except Exception as e:
        raise RuntimeError(f"Screen capture failed: {e}") from e

    floor = min(THRESHOLD_FLOOR, base_threshold)
    level = base_threshold
    while level >= floor:
        boxes = find_outlines(shot, left, top, level)
        if boxes:
            return boxes
        level -= THRESHOLD_STEP
    return []


def box_center(box):
    return box[4], box[5]


def box_tilt(box):
    return box[6]


def box_size(box):
    return box[7]


def pick_square(boxes, near, ref, size_ref=None):
    """Chooses one square.

    With no previous position, it's the square closest to the crosshair (ref). Otherwise
    it's the one closest to where the square was last seen, and it must be about the same
    size as the square the tool locked onto. Returns None if nothing matches.
    """
    if not boxes:
        return None
    if size_ref:
        boxes = [b for b in boxes if abs(box_size(b) - size_ref) <= SIZE_TOLERANCE * size_ref]
        if not boxes:
            return None
    if near is None:
        return min(boxes, key=lambda b: math.hypot(box_center(b)[0] - ref[0],
                                                   box_center(b)[1] - ref[1]))
    best = min(boxes, key=lambda b: math.hypot(box_center(b)[0] - near[0],
                                               box_center(b)[1] - near[1]))
    sw, _sh = screen_size()
    if math.hypot(box_center(best)[0] - near[0], box_center(best)[1] - near[1]) \
            > TRACK_FRACTION * sw:
        return None
    return best


def tween(widget, key, start, end, setter, steps=8, delay=16):
    """Smoothly moves a color from start to end, calling setter on each frame.
    A new tween for the same key cancels the old one, so animations never fight."""
    jobs = widget.__dict__.setdefault("_tween_jobs", {})
    pending = jobs.pop(key, None)
    if pending is not None:
        try:
            widget.after_cancel(pending)
        except tk.TclError:
            pass
    if start == end:
        setter(end)
        return

    def frame(i):
        t = i / steps
        eased = t * t * (3 - 2 * t)
        setter(lerp_hex(start, end, eased))
        if i < steps:
            jobs[key] = widget.after(delay, frame, i + 1)
        else:
            jobs.pop(key, None)

    frame(1)


def rounded_points(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def outer_bg(widget):
    """The background color of a widget, so rounded shapes blend into their parent."""
    try:
        return widget.cget("bg")
    except tk.TclError:
        return PANEL


def get_screen_work_area():
    work_area = wintypes.RECT()
    get_work_area = ctypes.windll.user32.SystemParametersInfoW
    get_work_area.argtypes = (
        ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(wintypes.RECT), ctypes.c_uint)
    get_work_area.restype = ctypes.c_int
    if not get_work_area(0x0030, 0, ctypes.byref(work_area), 0):
        raise ctypes.WinError()
    return work_area


def make_window_clickthrough(window, transparent_color):
    user32 = ctypes.windll.user32
    get_ancestor = user32.GetAncestor
    get_ancestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    get_ancestor.restype = ctypes.c_void_p
    hwnd = get_ancestor(ctypes.c_void_p(window.winfo_id()), 2)

    pointer_api = ctypes.sizeof(ctypes.c_void_p) == 8
    get_style = getattr(user32, "GetWindowLongPtrW" if pointer_api else "GetWindowLongW")
    get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style = getattr(user32, "SetWindowLongPtrW" if pointer_api else "SetWindowLongW")
    set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    ex_style = get_style(hwnd, -20)
    set_style(hwnd, -20, ex_style | 0x20 | 0x80000 | 0x08000000)

    set_layered_attributes = user32.SetLayeredWindowAttributes
    set_layered_attributes.argtypes = (
        ctypes.c_void_p, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD)
    set_layered_attributes.restype = wintypes.BOOL
    red, green, blue = hex_to_rgb(transparent_color)
    color_key = red | (green << 8) | (blue << 16)
    if not set_layered_attributes(hwnd, color_key, 255, 0x1 | 0x2):
        raise ctypes.WinError()

    set_position = user32.SetWindowPos
    set_position.argtypes = (
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint)
    set_position.restype = wintypes.BOOL
    if not set_position(
            hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020):
        raise ctypes.WinError()


def set_initial_window_geometry(root, width, height, min_width, min_height):
    class Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    get_work_area = ctypes.windll.user32.SystemParametersInfoW
    get_work_area.argtypes = [ctypes.c_uint, ctypes.c_uint,
                              ctypes.POINTER(Rect), ctypes.c_uint]
    get_work_area.restype = ctypes.c_int
    work_area = Rect()
    if not get_work_area(0x0030, 0, ctypes.byref(work_area), 0):
        raise ctypes.WinError()

    area_width = work_area.right - work_area.left
    area_height = work_area.bottom - work_area.top
    width = min(width, max(1, area_width - 16))
    height = min(height, max(1, area_height - 40))
    root.minsize(min(min_width, width), min(min_height, height))
    x = work_area.left + (area_width - width) // 2
    y = work_area.top + (area_height - height) // 2
    root.geometry(f"{width}x{height}+{x}+{y}")


def route(a, b):
    """Cells from a to b (excluding a, including b), moving sideways first, then up/down."""
    cells = []
    x, y = a
    while x != b[0]:
        x += 1 if b[0] > x else -1
        cells.append((x, y))
    while y != b[1]:
        y += 1 if b[1] > y else -1
        cells.append((x, y))
    return cells


def move_key(a, b):
    """Key and name for moving one tile from cell a to the adjacent cell b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 1:
        return VK_D, "D"
    if dx == -1:
        return VK_A, "A"
    if dy == 1:
        return VK_S, "S"
    return VK_W, "W"


def build_runs(path):
    """Turns a path of cells into (key, name, tiles) runs, looping back to the start.
    Consecutive moves in the same direction are merged into one hold."""
    cells = list(path) + route(path[-1], path[0])
    runs = []
    for a, b in zip(cells, cells[1:]):
        vk, name = move_key(a, b)
        if runs and runs[-1][0] == vk:
            runs[-1][2] += 1
        else:
            runs.append([vk, name, 1])
    return [tuple(r) for r in runs]


class RoundBox(tk.Frame):
    """A frame with a rounded background. Put content in .inner."""

    def __init__(self, parent, fill=PANEL, outline=BORDER, radius=RADIUS_CARD, pad=10):
        super().__init__(parent, bg=outer_bg(parent))
        self.box_fill = fill
        self.box_outline = outline
        self.box_radius = radius
        self.bg_canvas = tk.Canvas(self, bg=outer_bg(parent), highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.inner = tk.Frame(self, bg=fill)
        self.inner.pack(fill="both", expand=True, padx=pad, pady=pad)
        self.bind("<Configure>", self._draw_box)

    def _draw_box(self, _event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8 or h < 8:
            return
        cv = self.bg_canvas
        cv.delete("all")
        cv.create_polygon(rounded_points(1, 1, w - 2, h - 2, self.box_radius),
                          smooth=True, fill=self.box_fill, outline=self.box_outline,
                          width=1)

    def set_colors(self, fill=None, outline=None):
        if fill is not None:
            self.box_fill = fill
            self.inner.configure(bg=fill)
        if outline is not None:
            self.box_outline = outline
        self._draw_box()


class RoundEntry(RoundBox):
    """A rounded text field. Its border turns green while typing."""

    def __init__(self, parent, var, width=8, placeholder=None):
        super().__init__(parent, fill=INPUT, outline=BORDER, radius=RADIUS_FIELD, pad=4)
        self.var = var
        self.placeholder = placeholder
        self.placeholder_active = bool(placeholder and not var.get())
        if self.placeholder_active:
            var.set(placeholder)
        self.enabled = None
        self.entry = tk.Entry(self.inner, textvariable=var, width=width, justify="center",
                              bg=INPUT, fg=MUTED if self.placeholder_active else TEXT,
                              insertbackground=TEXT, relief="flat",
                              bd=0, highlightthickness=0, font=FONT_BODY,
                              disabledbackground=DISABLED_BG, disabledforeground=DISABLED_FG)
        self.entry.pack(padx=6, pady=3)
        self.entry.bind("<FocusIn>", self._on_entry_focus_in)
        self.entry.bind("<FocusOut>", self._on_entry_focus_out)
        self.entry.bind("<Button-1>", self._refocus_entry, add="+")
        for widget in (self, self.bg_canvas, self.inner):
            widget.bind("<Button-1>", self._focus_entry_on_click)

    def _on_entry_focus_in(self, _event=None):
        if self.placeholder_active:
            self.placeholder_active = False
            self.var.set("")
        self.entry.configure(fg=TEXT)
        self.set_colors(outline=GREEN)

    def _on_entry_focus_out(self, _event=None):
        if self.placeholder and not self.var.get():
            self.placeholder_active = True
            self.var.set(self.placeholder)
        self.entry.configure(fg=MUTED if self.placeholder_active else TEXT)
        self.set_colors(outline=BORDER)

    def set_value(self, value):
        self.placeholder_active = False
        self.var.set(value)
        self.entry.configure(fg=TEXT)

    def set_enabled(self, enabled):
        if enabled == self.enabled:
            return
        self.enabled = enabled
        fill = INPUT if enabled else DISABLED_BG
        self.set_colors(fill=fill)
        self.entry.configure(state="normal" if enabled else "disabled", bg=fill)

    def _focus_entry_on_click(self, _event=None):
        if self.enabled is not False:
            self.after_idle(self._focus_entry)
        return "break"

    def _focus_entry(self):
        if self.enabled is not False:
            self.entry.focus_set()
            self.entry.icursor("end")

    def _refocus_entry(self, _event=None):
        if self.enabled is not False:
            self.entry.after_idle(self.entry.focus_set)


DROPDOWN_OPEN_MS = 160
DROPDOWN_CLOSE_MS = 110
DROPDOWN_SLIDE_PX = 10
ANIMATION_FRAME_MS = 16


def ease_out_cubic(t):
    """Fast at first, then settling. t runs from 0 to 1."""
    return 1 - (1 - t) ** 3


def popup_slide(opens_above):
    """How far a menu moves while it appears. A menu that opens above its dropdown (a drop-up, like
    Load Profile) rises from just below its final spot. One that opens below descends from just above."""
    return DROPDOWN_SLIDE_PX if opens_above else -DROPDOWN_SLIDE_PX


def run_animation(widget, duration_ms, step, done=None):
    """Calls step(progress) from 0 to 1 over duration_ms on the Tk loop, then done(). Stops quietly
    if the widget is destroyed part way through."""
    started = time.perf_counter()

    def frame():
        try:
            if not widget.winfo_exists():
                return
            progress = min(1.0, (time.perf_counter() - started) * 1000 / duration_ms)
            step(progress)
            if progress < 1.0:
                widget.after(ANIMATION_FRAME_MS, frame)
            elif done is not None:
                done()
        except tk.TclError:
            return

    frame()


def popup_corner_points(width, height, radius):
    """Outline of a menu with all four corners rounded, as (x, y) points around the edge."""
    right, bottom = width - 1, height - 1
    points = []

    def arc(cx, cy, start, end):
        for step in range(9):
            angle = start + (end - start) * step / 8
            points.append((round(cx + radius * math.cos(angle)),
                           round(cy + radius * math.sin(angle))))

    arc(radius, radius, math.pi, 1.5 * math.pi)
    arc(right - radius, radius, 1.5 * math.pi, 2 * math.pi)
    arc(right - radius, bottom - radius, 0, 0.5 * math.pi)
    arc(radius, bottom - radius, 0.5 * math.pi, math.pi)
    return points


def fit_text(text, font, max_px):
    """Shortens text with an ellipsis so it fits in max_px pixels."""
    if font.measure(text) <= max_px:
        return text
    for end in range(len(text) - 1, 0, -1):
        candidate = text[:end].rstrip() + "\u2026"
        if font.measure(candidate) <= max_px:
            return candidate
    return "\u2026"


def popup_layout(choices, measure, dropdown_width, screen_width, scrollable, scrollbar_px):
    """Width of a dropdown's menu, and how many pixels its labels may use. The menu is at least as
    wide as its dropdown and wide enough for its longest choice, but never wider than the screen."""
    item_pad = 2 * 8 + 2 * 4 + 6
    scroll_pad = scrollbar_px if scrollable else 0
    widest = max((measure(choice) for choice in choices), default=0)
    width = min(max(dropdown_width, widest + item_pad + scroll_pad), screen_width - 16)
    return width, width - item_pad - scroll_pad


class RoundDropdown(RoundBox):
    """A rounded dropdown with a custom popup sized to match its button."""

    def __init__(self, parent, variable, choices, width=10, open_above=False,
                 command=None):
        super().__init__(parent, fill=INPUT, outline=BORDER, radius=RADIUS_FIELD, pad=4)
        self.var = variable
        self.choices = list(choices)
        self.enabled = None
        self.open_above = open_above
        self.command = command
        self.popup = None
        self.popup_items = []
        self.popup_index = 0
        self.popup_canvas = None
        self.popup_rows_frame = None
        self._focus_before_popup = None
        self._pressed_item = None
        self._popup_anchor = None
        self._label_chars = width
        self.label = tk.Label(self.inner, text="", font=FONT_BODY, fg=TEXT,
                              bg=INPUT, width=width, anchor="w", padx=6, cursor="hand2")
        self.label.pack(side="left", pady=3)
        variable.trace_add("write", lambda *_: self._refresh_label())
        self.label.bind("<Configure>", lambda _event: self._refresh_label())
        self._refresh_label()
        self.arrow = tk.Label(self.inner, text="\u25BE", font=FONT_SMALL, fg=GREEN,
                              bg=INPUT, padx=6, cursor="hand2")
        self.arrow.pack(side="left", pady=3)
        for w in (self, self.inner, self.label, self.arrow):
            w.bind("<Button-1>", self.open_menu)

    def _refresh_label(self):
        font = tkfont.Font(font=FONT_BODY)
        label_px = self.label.winfo_width()
        if label_px <= 1:
            label_px = font.measure("0") * self._label_chars
        self.label.configure(text=fit_text(self.var.get(), font, label_px - 12))

    def set_choices(self, choices):
        self.choices = list(choices)
        self.close_menu()
        if self.var.get() not in self.choices:
            self.var.set("")

    def open_menu(self, _event=None, anchor=None, align_right=False):
        if not self.enabled:
            return "break"
        if self.popup is not None:
            self.close_menu()
            return "break"
        if not self.choices:
            return "break"

        anchor_widget = anchor if anchor is not None else self
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=BORDER)
        popup.transient(self.winfo_toplevel())
        self.popup = popup
        self._popup_anchor = anchor_widget
        self._focus_before_popup = self.focus_get()

        row_height = tkfont.Font(font=FONT_BODY).metrics("linespace") + 14
        max_rows = max(1, (self.winfo_screenheight() - 24) // row_height)
        visible_rows = min(len(self.choices), max_rows)
        scrollable = len(self.choices) > visible_rows
        font = tkfont.Font(font=FONT_BODY)
        popup_width, text_px = popup_layout(
            self.choices, font.measure, anchor_widget.winfo_width(), self.winfo_screenwidth(),
            scrollable, SmoothScrollBar.THICKNESS + 4)
        frame = tk.Frame(popup, bg=BORDER)
        frame.pack(fill="both", expand=True)
        surface = tk.Frame(frame, bg=INPUT)
        surface.pack(fill="both", expand=True, padx=1, pady=1)
        if len(self.choices) > visible_rows:
            self.popup_canvas = tk.Canvas(
                surface, bg=INPUT, highlightthickness=0, bd=0,
                height=visible_rows * row_height, yscrollincrement=row_height)
            self.popup_canvas.pack(side="left", fill="both", expand=True)
            scrollbar = SmoothScrollBar(surface, command=self.popup_canvas.yview,
                                        length=visible_rows * row_height, orient="vertical",
                                        background=INPUT)
            scrollbar.pack(side="right", fill="y", padx=(2, 0))
            self.popup_canvas.configure(yscrollcommand=scrollbar.set)
            self.popup_rows_frame = tk.Frame(self.popup_canvas, bg=INPUT)
            window = self.popup_canvas.create_window(
                (0, 0), window=self.popup_rows_frame, anchor="nw")
            self.popup_rows_frame.bind(
                "<Configure>",
                lambda _event: self.popup_canvas.configure(
                    scrollregion=self.popup_canvas.bbox("all")))
            self.popup_canvas.bind(
                "<Configure>",
                lambda event: self.popup_canvas.itemconfigure(window, width=event.width))
            self.popup_canvas.bind("<MouseWheel>", self._scroll_popup)
            row_parent = self.popup_rows_frame
        else:
            row_parent = surface

        self.popup_index = self.choices.index(self.var.get()) if self.var.get() in self.choices else 0
        self.popup_items = []
        for index, choice in enumerate(self.choices):
            item = tk.Label(row_parent, text=fit_text(choice, font, text_px), font=FONT_BODY, fg=TEXT,
                            bg=INPUT, anchor="w", padx=8, pady=5, cursor="hand2")
            item.pack(fill="x", padx=4, pady=2)
            item.bind("<Enter>", lambda _event, i=index: self._set_popup_index(i))
            item.bind("<ButtonPress-1>", lambda _event, i=index: self._press_popup_item(i))
            item.bind("<ButtonRelease-1>",
                      lambda _event, i=index: self._release_popup_item(i))
            item.bind("<MouseWheel>", self._scroll_popup)
            self.popup_items.append(item)
        self._paint_popup_items()

        popup.bind("<Up>", self._move_popup_selection)
        popup.bind("<Down>", self._move_popup_selection)
        popup.bind("<Return>", self._choose_popup_selection)
        popup.bind("<Escape>", lambda _event: self.close_menu())
        popup.bind("<MouseWheel>", self._scroll_popup)
        popup.bind("<Button-1>", self._dismiss_popup_if_outside)

        popup.update_idletasks()
        if self.var.get() in self.choices:
            self._ensure_popup_item_visible(self.popup_index)
        top = anchor_widget.winfo_rooty()
        x = anchor_widget.winfo_rootx()
        if align_right:
            x += anchor_widget.winfo_width() - popup_width
        x = max(0, min(x, self.winfo_screenwidth() - popup_width - 8))
        popup_height = popup.winfo_reqheight()
        if self.open_above:
            y = top - popup_height
        else:
            y = top + anchor_widget.winfo_height()
            screen_height = self.winfo_screenheight()
            if y + popup_height > screen_height:
                y = top - popup_height if top >= popup_height else screen_height - popup_height
        final_y = max(0, y)
        opens_above = final_y < top
        width = popup_width
        slide = popup_slide(opens_above)
        popup.attributes("-alpha", 0.0)
        popup.geometry(f"{width}x{popup_height}+{x}+{final_y + slide}")
        popup.update_idletasks()
        popup.lift()
        popup.grab_set()
        popup.focus_force()
        popup.after_idle(self._round_popup_corners, popup, surface)

        def open_step(progress):
            if self.popup is not popup:
                return
            eased = ease_out_cubic(progress)
            popup.attributes("-alpha", max(0.02, eased))
            popup.geometry(f"{width}x{popup_height}+{x}+{round(final_y + slide * (1 - eased))}")

        run_animation(popup, DROPDOWN_OPEN_MS, open_step)
        return "break"

    @staticmethod
    def _round_popup_corners(popup, surface):
        if (not hasattr(ctypes, "windll") or not popup.winfo_exists()
                or not surface.winfo_exists()):
            return
        width, height = popup.winfo_width(), popup.winfo_height()
        radius = min(8, width // 2, height // 2)
        if radius < 1:
            return

        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        gdi32 = ctypes.windll.gdi32
        create_region = gdi32.CreatePolygonRgn
        create_region.argtypes = [ctypes.POINTER(Point), ctypes.c_int, ctypes.c_int]
        create_region.restype = ctypes.c_void_p

        user32 = ctypes.windll.user32
        get_ancestor = user32.GetAncestor
        get_ancestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        get_ancestor.restype = ctypes.c_void_p
        set_region = user32.SetWindowRgn
        set_region.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        set_region.restype = ctypes.c_int

        def apply_region(hwnd, width, height, corner_radius):
            corner_radius = min(corner_radius, width // 2, height // 2)
            if corner_radius < 1:
                return
            points = popup_corner_points(width, height, corner_radius)
            point_array = (Point * len(points))(*(Point(x, y) for x, y in points))
            region = create_region(point_array, len(points), 1)
            if region and not set_region(hwnd, region, True):
                gdi32.DeleteObject(region)

        popup_hwnd = get_ancestor(ctypes.c_void_p(popup.winfo_id()), 2)
        apply_region(popup_hwnd, width, height, radius)
        surface.update_idletasks()
        surface_width, surface_height = surface.winfo_width(), surface.winfo_height()
        surface_hwnd = ctypes.c_void_p(surface.winfo_id())
        apply_region(surface_hwnd, surface_width, surface_height, radius - 1)

    def _paint_popup_items(self):
        for index, item in enumerate(self.popup_items):
            active = index == self.popup_index
            item.configure(bg=GREEN if active else INPUT,
                           fg=ON_GREEN if active else TEXT)

    def _ensure_popup_item_visible(self, index):
        if self.popup_canvas is None or not self.popup_items:
            return
        canvas = self.popup_canvas
        canvas.update_idletasks()
        item = self.popup_items[index]
        top = item.winfo_y()
        bottom = top + item.winfo_height()
        view_top = canvas.canvasy(0)
        view_bottom = view_top + canvas.winfo_height()
        content_height = max(1, self.popup_rows_frame.winfo_height())
        if top < view_top:
            canvas.yview_moveto(top / content_height)
        elif bottom > view_bottom:
            canvas.yview_moveto(max(0, (bottom - canvas.winfo_height()) / content_height))

    def _set_popup_index(self, index):
        self.popup_index = index
        self._paint_popup_items()
        self._ensure_popup_item_visible(index)

    def _move_popup_selection(self, event):
        direction = -1 if event.keysym == "Up" else 1
        index = min(max(self.popup_index + direction, 0), len(self.popup_items) - 1)
        self._set_popup_index(index)
        return "break"

    def _scroll_popup(self, event):
        if self.popup_canvas is not None:
            self.popup_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _press_popup_item(self, index):
        self._pressed_item = index

    def _release_popup_item(self, index):
        if self._pressed_item == index:
            self._choose_popup_selection(index=index)
        self._pressed_item = None
        return "break"

    def _choose_popup_selection(self, _event=None, index=None):
        if self.popup is None:
            return "break"
        if index is None:
            index = self.popup_index
        changed = False
        if 0 <= index < len(self.choices):
            value = self.choices[index]
            changed = self.var.get() != value
            self.var.set(value)
        self.close_menu()
        if changed and self.command is not None:
            self.command()
        return "break"

    def _dismiss_popup_if_outside(self, event):
        if self.popup is None:
            return
        left = self.popup.winfo_rootx()
        top = self.popup.winfo_rooty()
        right = left + self.popup.winfo_width()
        bottom = top + self.popup.winfo_height()
        if not (left <= event.x_root < right and top <= event.y_root < bottom):
            self.close_menu()

    def close_menu(self):
        popup = self.popup
        anchor = self._popup_anchor
        self.popup = None
        self._popup_anchor = None
        self._pressed_item = None
        self.popup_items = []
        self.popup_canvas = None
        self.popup_rows_frame = None
        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.grab_release()
                    self._fade_out_popup(popup, anchor)
            except tk.TclError:
                pass
        focus_target = self._focus_before_popup
        self._focus_before_popup = None
        try:
            if (focus_target is not None and focus_target.winfo_exists()
                    and focus_target.winfo_viewable()):
                focus_target.focus_force()
            else:
                self.winfo_toplevel().focus_force()
        except tk.TclError:
            self.winfo_toplevel().focus_force()

    def _fade_out_popup(self, popup, anchor=None):
        """Fades the menu out while it slides back the way it came, then destroys it."""
        x, y = popup.winfo_rootx(), popup.winfo_rooty()
        width, height = popup.winfo_width(), popup.winfo_height()
        anchor_y = anchor.winfo_rooty() if anchor is not None else self.winfo_rooty()
        slide = popup_slide(y < anchor_y)

        def fade_step(progress):
            eased = ease_out_cubic(progress)
            popup.attributes("-alpha", max(0.0, 1.0 - eased))
            popup.geometry(f"{width}x{height}+{x}+{round(y + slide * eased)}")

        def destroy_popup():
            try:
                popup.destroy()
            except tk.TclError:
                pass

        run_animation(popup, DROPDOWN_CLOSE_MS, fade_step, destroy_popup)

    def set_enabled(self, enabled):
        if enabled == self.enabled:
            return
        self.enabled = enabled
        fill = INPUT if enabled else DISABLED_BG
        self.set_colors(fill=fill)
        self.label.configure(bg=fill, fg=TEXT if enabled else DISABLED_FG)
        self.arrow.configure(bg=fill, fg=GREEN if enabled else DISABLED_FG,
                             cursor="hand2" if enabled else "arrow")
        if not enabled:
            self.close_menu()


class RoundButton(tk.Canvas):
    """A button with rounded corners. The background fades on hover.

    Buttons match the height of RoundEntry fields. Pass fixed_h to override that height.
    """

    def __init__(self, parent, text="", command=None, font=FONT_BODY, bg=PANEL, fg=TEXT,
                 hover=None, padx=12, pady=5, anchor="center", fixed_h=None, icon=None,
                 square=False):
        self.rb_font = tkfont.Font(font=font)
        self.rb_text = text
        self.rb_icon = icon
        self.rb_square = square
        self.rb_icon_width = 22 if icon == "settings" else 0
        self.rb_command = command
        self.rb_bg = bg
        self.rb_target = bg
        self.rb_fg = fg
        self.rb_hover = hover or bg
        self.rb_radius = RADIUS_BTN
        self.rb_padx = padx
        self.rb_anchor = anchor
        self.rb_fixed_h = fixed_h
        self.base_bg = bg
        self.fg_color = fg
        self.hover_bg = self.rb_hover
        self.enabled = True
        self.hovered = False
        self.rb_look = None
        self.rb_size = None
        self.rb_background = None
        self.rb_label = None
        h = fixed_h or (tkfont.Font(font=FONT_BODY).metrics("linespace") + 16)
        w = h if square else self.rb_font.measure(text) + 2 * padx + self.rb_icon_width
        super().__init__(parent, width=w, height=h, bg=outer_bg(parent),
                         highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Configure>", lambda _e: self._redraw(), add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")

    def set_text(self, text):
        if text == self.rb_text:
            return
        self.rb_text = text
        self.configure(width=self.rb_font.measure(text) + 2 * self.rb_padx
                       + self.rb_icon_width)
        self._redraw()

    def set_height(self, h):
        """Gives the button an exact height, for example to line up with a text box."""
        if h < 2 or h == self.rb_fixed_h:
            return
        self.rb_fixed_h = h
        self.configure(height=h)
        self._redraw()

    def set_style(self, bg, fg, hover, enabled=True):
        self.enabled = enabled
        self.base_bg = bg
        self.fg_color = fg
        self.hover_bg = hover
        self.rb_fg = fg
        self.configure(cursor="hand2" if enabled else "arrow")
        self._fade(hover if (self.hovered and enabled) else bg)
        self._redraw()

    def _fade(self, color):
        if color == self.rb_target:
            return
        self.rb_target = color
        tween(self, "bg", self.rb_bg, color, self._set_bg)

    def _set_bg(self, color):
        self.rb_bg = color
        self._redraw()

    def _on_enter(self, _event=None):
        self.hovered = True
        if self.enabled:
            self._fade(self.hover_bg)

    def _on_leave(self, _event=None):
        self.hovered = False
        self._fade(self.base_bg)

    def _on_release(self, event):
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if self.enabled and self.rb_command and inside:
            self.rb_command()

    def _redraw(self):
        w = self.winfo_width()
        h = self.rb_fixed_h or self.winfo_height()
        if w < 2:
            w = int(float(self.cget("width")))
        if h < 2:
            h = int(float(self.cget("height")))
        look = (w, h, self.rb_bg, self.rb_fg, self.rb_text)
        if look == self.rb_look:
            return
        resized = (w, h) != self.rb_size
        self.rb_look = look
        if resized or self.rb_background is None or self.rb_icon == "settings":
            self._build_items(w, h)
        else:
            self.itemconfigure(self.rb_background, fill=self.rb_bg)
            self.itemconfigure(self.rb_label, text=self.rb_text, fill=self.rb_fg)

    def _build_items(self, w, h):
        radius = min(self.rb_radius, max(2, h // 2))
        self.delete("all")
        self.rb_size = (w, h)
        self.rb_background = self.create_polygon(rounded_points(0, 0, w - 1, h - 1, radius),
                                                 smooth=True, fill=self.rb_bg, outline="")
        if self.rb_anchor == "w":
            x, anchor = self.rb_padx, "w"
            if self.rb_icon == "settings":
                self._draw_settings_gear(self.rb_padx + 8, h / 2)
                x += self.rb_icon_width
        else:
            x, anchor = w / 2, "center"
        self.rb_label = self.create_text(x, h / 2, text=self.rb_text, font=self.rb_font,
                                         fill=self.rb_fg, anchor=anchor)

    def _draw_settings_gear(self, center_x, center_y):
        for tooth in range(8):
            angle = tooth * math.pi / 4
            self.create_line(
                center_x + 4.5 * math.cos(angle),
                center_y + 4.5 * math.sin(angle),
                center_x + 7.2 * math.cos(angle),
                center_y + 7.2 * math.sin(angle),
                fill=self.rb_fg, width=2, capstyle=tk.ROUND)
        self.create_oval(center_x - 5, center_y - 5,
                         center_x + 5, center_y + 5,
                         outline=self.rb_fg, width=2)
        self.create_oval(center_x - 2, center_y - 2,
                         center_x + 2, center_y + 2,
                         fill=self.rb_bg, outline=self.rb_bg)


class SmoothScrollBar(tk.Canvas):
    """A compact rounded scrollbar. Thumb is a round-capped line so the ends stay clean."""

    THICKNESS = 12
    THUMB = 7
    TRACK = 3

    def __init__(self, parent, command, length, orient="horizontal", background=INPUT):
        self.orient = orient
        self.horizontal = orient == "horizontal"
        if self.horizontal:
            super().__init__(parent, width=length, height=self.THICKNESS, bg=background,
                             highlightthickness=0, bd=0, cursor="hand2")
        else:
            super().__init__(parent, width=self.THICKNESS, height=length, bg=background,
                             highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.first = 0.0
        self.last = 1.0
        self.drag_offset = None
        self.hovered = False
        self.bind("<Configure>", lambda _event: self.redraw(), add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<B1-Motion>", self._on_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.redraw()

    def set(self, first, last):
        self.first = float(first)
        self.last = float(last)
        self.redraw()

    def _axis(self, event):
        return event.x if self.horizontal else event.y

    def _track(self):
        size = self.winfo_width() if self.horizontal else self.winfo_height()
        return 6.0, max(6.0, size - 6.0)

    def _thumb(self):
        start, end = self._track()
        track = end - start
        visible = max(0.0, min(1.0, self.last - self.first))
        thumb = min(track, max(28.0, min(56.0, track * visible)))
        max_start = end - thumb
        max_first = max(0.0, 1.0 - visible)
        fraction = min(1.0, max(0.0, self.first / max_first)) if max_first else 0.0
        thumb_start = start + (max_start - start) * fraction
        return thumb_start, thumb_start + thumb

    def redraw(self):
        self.delete("all")
        start, end = self._track()
        if end <= start:
            return
        self._capsule(start, end, self.TRACK, BORDER)
        if self.last - self.first >= 1.0:
            return
        thumb_start, thumb_end = self._thumb()
        self._capsule(thumb_start, thumb_end, self.THUMB,
                      GREEN_HOVER if self.hovered else GREEN)

    def _capsule(self, start, end, thickness, color):
        """Filled rounded rect so vertical and horizontal thumbs match (line width
        on a vertical create_line is often ignored on Windows)."""
        r = max(1.0, thickness / 2.0)
        if self.horizontal:
            mid = self.winfo_height() / 2.0
            x1, y1, x2, y2 = start, mid - r, end, mid + r
        else:
            mid = self.winfo_width() / 2.0
            x1, y1, x2, y2 = mid - r, start, mid + r, end
        self.create_polygon(rounded_points(x1, y1, x2, y2, r),
                            smooth=True, fill=color, outline="")

    def _move_thumb(self, pos, offset):
        if self.last - self.first >= 1.0:
            return
        start, end = self._track()
        thumb_start, thumb_end = self._thumb()
        thumb = thumb_end - thumb_start
        travel = end - start - thumb
        if travel <= 0:
            return
        new_start = min(end - thumb, max(start, pos - offset))
        visible = self.last - self.first
        max_first = max(0.0, 1.0 - visible)
        self.command("moveto", (new_start - start) / travel * max_first)

    def _on_press(self, event):
        if self.last - self.first >= 1.0:
            return
        pos = self._axis(event)
        thumb_start, thumb_end = self._thumb()
        if thumb_start <= pos <= thumb_end:
            self.drag_offset = pos - thumb_start
        else:
            self.drag_offset = (thumb_end - thumb_start) / 2
        self._move_thumb(pos, self.drag_offset)

    def _on_drag(self, event):
        if self.drag_offset is not None:
            self._move_thumb(self._axis(event), self.drag_offset)

    def _on_release(self, _event):
        self.drag_offset = None

    def _on_enter(self, _event):
        self.hovered = True
        self.redraw()

    def _on_leave(self, _event):
        self.hovered = False
        self.redraw()


class Checkbox(tk.Frame):
    """A custom rounded checkbox with an animated fill and check mark."""

    SIZE = 18

    def __init__(self, parent, text, variable, bg=PANEL):
        super().__init__(parent, bg=bg, cursor="hand2")
        self.var = variable
        s = self.SIZE
        self.canvas = tk.Canvas(self, width=s, height=s, bg=bg, highlightthickness=0,
                                bd=0, cursor="hand2")
        self.canvas.pack(side="left")
        self.box = self.canvas.create_polygon(rounded_points(1, 1, s - 1, s - 1, 4),
                                              smooth=True, fill=INPUT, outline=BORDER,
                                              width=1)
        self.tick = self.canvas.create_line(5, 9.5, 8, 12.5, 13, 6, width=2,
                                            capstyle="round", joinstyle="round",
                                            fill=INPUT)
        self.label = tk.Label(self, text=text, font=FONT_SMALL, fg=TEXT, bg=bg,
                              cursor="hand2")
        self.label.pack(side="left", padx=(8, 0))
        for widget in (self, self.canvas, self.label):
            widget.bind("<Button-1>", self.flip)
        self.var.trace_add("write", lambda *_: self.render(True))
        self.render(False)

    def flip(self, _event=None):
        self.var.set(not self.var.get())

    def render(self, animate=True):
        on = bool(self.var.get())
        cv = self.canvas
        fill_t = GREEN if on else INPUT
        line_t = GREEN if on else BORDER
        tick_t = ON_GREEN if on else INPUT
        if not animate:
            cv.itemconfigure(self.box, fill=fill_t, outline=line_t)
            cv.itemconfigure(self.tick, fill=tick_t)
            return
        tween(self, "fill", cv.itemcget(self.box, "fill"), fill_t,
              lambda c: cv.itemconfigure(self.box, fill=c))
        tween(self, "line", cv.itemcget(self.box, "outline"), line_t,
              lambda c: cv.itemconfigure(self.box, outline=c))
        tween(self, "tick", cv.itemcget(self.tick, "fill"), tick_t,
              lambda c: cv.itemconfigure(self.tick, fill=c))


def prep(widget):
    """Remembers a label's normal text color so it can be restored after locking."""
    if isinstance(widget, tk.Label):
        widget._on_fg = widget.cget("fg")
    return widget


def paint(widget, enabled):
    """Turns a setting on or off visually and functionally."""
    if isinstance(widget, RoundButton):
        widget.set_style(widget.base_bg, widget.fg_color if enabled else DISABLED_FG,
                         widget.hover_bg, enabled)
    elif isinstance(widget, (RoundEntry, RoundDropdown)):
        widget.set_enabled(enabled)
    elif isinstance(widget, tk.Label):
        widget.configure(fg=widget._on_fg if enabled else DISABLED_FG)


def align_grid_columns(frames, columns):
    """Gives separate header and data frames the same measured column widths."""
    if not frames:
        return
    frames[0].winfo_toplevel().update_idletasks()
    widths = [
        max((widget.winfo_reqwidth() + padding for widget, padding in cells), default=0)
        for cells in columns
    ]
    for frame in frames:
        for column, width in enumerate(widths):
            frame.grid_columnconfigure(column, minsize=width)


class InfoIcon(tk.Canvas):
    """A small (i) circle. Hovering fades it to green and shows the description."""

    def __init__(self, parent, text, bg=PANEL, open_above=False):
        super().__init__(parent, width=18, height=18, bg=bg, highlightthickness=0,
                         bd=0, cursor="question_arrow")
        self.text = text
        self.open_above = open_above
        self.tip = None
        self.ring = self.create_oval(2, 2, 16, 16, outline=MUTED, width=1)
        self.glyph = self.create_text(9, 9, text="i", fill=MUTED,
                                      font=(FONT_FAMILY, 9, "bold"))
        self.bind("<Enter>", self.show)
        self.bind("<Leave>", self.hide)

    def _paint(self, color):
        tween(self, "ring", self.itemcget(self.ring, "outline"), color,
              lambda c: self.itemconfigure(self.ring, outline=c))
        tween(self, "glyph", self.itemcget(self.glyph, "fill"), color,
              lambda c: self.itemconfigure(self.glyph, fill=c))

    def show(self, _event=None):
        self._paint(GREEN)
        if self.tip is None:
            self.tip = tk.Toplevel(self)
            self.tip.wm_overrideredirect(True)
            tk.Label(self.tip, text=self.text, justify="left", bg=INPUT, fg=TEXT,
                     font=FONT_SMALL, wraplength=320, padx=10, pady=8,
                     relief="solid", bd=1).pack()
            self.tip.update_idletasks()
            if self.open_above:
                x = self.winfo_rootx()
                y = self.winfo_rooty() - self.tip.winfo_reqheight()
                x = max(0, min(x, self.winfo_screenwidth() - self.tip.winfo_reqwidth()))
                y = max(0, min(y, self.winfo_screenheight() - self.tip.winfo_reqheight()))
                self.tip.wm_geometry(f"+{x}+{y}")
            else:
                self.tip.wm_geometry(
                    f"+{self.winfo_rootx() + 22}+{self.winfo_rooty() + 22}")

    def hide(self, _event=None):
        self._paint(MUTED)
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class GroupTag(tk.Canvas):
    def __init__(self, parent, group):
        super().__init__(parent, width=22, height=22, bg=outer_bg(parent),
                         highlightthickness=0, bd=0)
        self.create_polygon(rounded_points(2, 2, 20, 20, 6), smooth=True,
                            fill=GROUP_TAG_COLOR, outline=GROUP_TAG_COLOR, width=2)
        self.create_text(11, 11, text=GROUP_TAGS[group], fill="#ffffff",
                         font=(FONT_FAMILY, 9, "bold"))


class NavItem(tk.Frame):
    """A sidebar entry with a rounded green bar on the left and an optional (i) icon."""

    def __init__(self, parent, text, command, pad_left=14, info=None, tag_group=None,
                 info_open_above=False):
        super().__init__(parent, bg=SIDEBAR)
        self.bar = tk.Canvas(self, width=4, height=1, bg=SIDEBAR, highlightthickness=0, bd=0)
        self.bar.pack(side="left", fill="y", padx=(0, 2))
        self._cur_bar = SIDEBAR
        self._bar_item = None
        self._bar_h = None
        self.bar.bind("<Configure>", lambda _e: self._draw_bar(self._cur_bar))
        if tag_group is not None:
            tag = GroupTag(self, tag_group)
            tag.pack(side="left", padx=(6, 2), pady=2)
            tag.bind("<Button-1>", lambda _event: command())
        if info:
            InfoIcon(self, info, bg=SIDEBAR,
                     open_above=info_open_above).pack(side="right", padx=8)
        self.button = RoundButton(self, text=text, command=command, font=FONT_NAV,
                                  bg=SIDEBAR, fg=TEXT, hover=NAV_HOVER, padx=pad_left,
                                  pady=7, anchor="w")
        self.button.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=2)

    def _draw_bar(self, color):
        h = self.bar.winfo_height()
        if h < 4:
            return
        if self._bar_item is None or self._bar_h != h:
            self.bar.delete("all")
            self._bar_item = self.bar.create_polygon(rounded_points(0, 0, 4, h - 1, 2),
                                                     smooth=True, fill=color, outline="")
            self._bar_h = h
        else:
            self.bar.itemconfigure(self._bar_item, fill=color)

    def _set_bar(self, color):
        self._cur_bar = color
        self._draw_bar(color)

    def update_look(self, selected, text, fg):
        self.button.set_text(text)
        self.button.set_style(bg=PANEL if selected else SIDEBAR, fg=fg,
                              hover=PANEL if selected else NAV_HOVER, enabled=True)
        target = GREEN if selected else SIDEBAR
        if target != self._cur_bar:
            tween(self.bar, "bar", self._cur_bar, target, self._set_bar)


class CategoryFilterButton(tk.Canvas):
    def __init__(self, parent, command):
        super().__init__(parent, width=28, height=28, bg=SIDEBAR,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.hovered = False
        self.active = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._redraw()

    def set_active(self, active):
        if self.active != active:
            self.active = active
            self._redraw()

    def _on_enter(self, _event=None):
        self.hovered = True
        self._redraw()

    def _on_leave(self, _event=None):
        self.hovered = False
        self._redraw()

    def _on_release(self, _event=None):
        self.command()

    def _redraw(self):
        self.configure(bg=NAV_HOVER if self.hovered else SIDEBAR)
        self.delete("all")
        color = GREEN if self.active else MUTED
        self.create_line(6, 6, 22, 6, 16, 13, 16, 19, 12, 22, 12, 13, 6, 6,
                         fill=color, width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)


class Controller:
    """Enforces the run rules.

    Simultaneous tools can run together, and alongside one Independent tool.
    Run Once tools require every other tool to be stopped.
    """

    def __init__(self):
        self.running_simultaneous = set()
        self.exclusive = None
        self.others_paused = threading.Event()

    def blocked_by(self, module):
        """The active tool blocking this module from starting, or None."""
        if self.exclusive not in (None, module):
            if (self.exclusive.GROUP == "Run Once"
                    or module.GROUP in EXCLUSIVE_GROUPS):
                return self.exclusive
        if module.GROUP == "Run Once" and self.running_simultaneous:
            return next(iter(self.running_simultaneous))
        return None

    def claim(self, module):
        if self.blocked_by(module) is not None:
            return False
        if module.GROUP == "Simultaneous":
            self.running_simultaneous.add(module)
        else:
            self.exclusive = module
        return True

    def release(self, module):
        self.running_simultaneous.discard(module)
        if self.exclusive is module:
            self.exclusive = None


class ModuleFrame(tk.Frame):
    """One tool's page. Scrolls vertically. The Start/Stop button sits beside the title."""

    GROUP = "Simultaneous"
    INCLUDABLE = True
    PAUSABLE = True
    RUNNABLE = True
    RESETTABLE = True

    def __init__(self, parent, controller, module_name, description):
        super().__init__(parent, bg=PANEL)
        self.controller = controller
        self.module_name = module_name
        self.display_name = getattr(type(self), "DISPLAY_NAME", module_name)
        self.running = False
        self.session = 0
        self.countdown_job = None
        self.countdown_left = 0
        self.delay_seconds = float(DELAY_SECONDS)
        self.note_var = tk.StringVar(value="")
        self.include_var = tk.BooleanVar(value=False)
        self.reset_defaults_callback = None
        self.reset_confirmation_pending = False
        self.reset_confirmation_job = None
        self.reset_button = None
        self._showing_conflict = False
        self._input_lock = threading.Lock()
        self._controls = []

        self.scroll_canvas = tk.Canvas(self, bg=PANEL, highlightthickness=0, bd=0,
                                       yscrollincrement=SCROLL_STEP_PX)
        scrollbar = SmoothScrollBar(self, command=self.scroll_canvas.yview, length=400,
                                    orient="vertical", background=PANEL)
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.scroll_canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.scroll_canvas, bg=PANEL)
        self._window = self.scroll_canvas.create_window(0, 0, window=self.inner,
                                                        anchor="nw")
        self.inner.bind("<Configure>", self._update_scrollregion)
        self.scroll_canvas.bind("<Configure>", self._match_width)

        header = tk.Frame(self.inner, bg=PANEL)
        header.pack(fill="x", padx=18, pady=(12, 0))
        title = tk.Frame(header, bg=PANEL)
        title.pack(side="left")
        if self.GROUP in GROUP_TAGS:
            GroupTag(title, self.GROUP).pack(side="left", padx=(0, 8))
        tk.Label(title, text=self.display_name, font=FONT_TITLE, fg=GREEN,
                 bg=PANEL).pack(side="left")
        InfoIcon(title, description, bg=PANEL).pack(side="left", padx=(8, 0))

        if self.RUNNABLE:
            self.toggle_btn = RoundButton(header, text="\u25B6  Start", command=self.toggle,
                                          font=FONT_BUTTON, bg=GREEN, fg=ON_GREEN,
                                          hover=GREEN_HOVER, padx=16, pady=5)
            self.toggle_btn.pack(side="right")

        if self.RESETTABLE:
            options_row = tk.Frame(self.inner, bg=PANEL)
            options_row.pack(fill="x", padx=18, pady=(10, 0))
            if self.INCLUDABLE:
                Checkbox(options_row, "Include in Start Selected", self.include_var,
                         bg=PANEL).pack(side="left")
            self.reset_button = RoundButton(
                options_row, text="Reset to Default", command=self.reset_to_defaults,
                font=FONT_SMALL, bg=RED, fg=RESET_BUTTON_FG, hover=RED_HOVER,
                padx=10, pady=3)
            self.track(self.reset_button).pack(side="right")

        tk.Frame(self.inner, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(8, 0))

        card = RoundBox(self.inner, fill=PANEL, outline=BORDER, radius=RADIUS_CARD, pad=10)
        card.pack(fill="x", padx=18, pady=(6, 14))
        self.card = card
        self.settings = card.inner

        self.note_label = tk.Label(self.inner, textvariable=self.note_var, font=FONT_SMALL,
                                   fg=RED, bg=PANEL, wraplength=440, justify="left")
        self._note_shown = False
        self.note_var.trace_add("write", lambda *_: self._sync_note())

        if self.RUNNABLE:
            self.delay_var = self.add_setting("Start delay (seconds)", str(DELAY_SECONDS),
                                              rule=self.delay_enabled)
        else:
            self.delay_var = tk.StringVar(value=str(DELAY_SECONDS))
        self.build_settings()

        self.after(150, self._refresh)

    def _sync_note(self):
        """Shows the red message line only while it has text, so it doesn't leave a gap."""
        want = bool(self.note_var.get())
        if want and not self._note_shown:
            self.note_label.pack(anchor="w", padx=18, pady=(6, 0), before=self.card)
            self._note_shown = True
        elif not want and self._note_shown:
            self.note_label.pack_forget()
            self._note_shown = False

    def _update_scrollregion(self, event=None):
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def _match_width(self, event):
        self.scroll_canvas.itemconfigure(self._window, width=event.width)

    def scroll(self, event):
        """Called by the app's mouse wheel handler for the visible tool."""
        bbox = self.scroll_canvas.bbox("all")
        if not bbox or bbox[3] - bbox[1] <= self.scroll_canvas.winfo_height():
            return
        step = -1 if event.delta > 0 else 1
        self.scroll_canvas.yview_scroll(step, "units")

    def track(self, widget, rule=None):
        """Registers a widget to be locked when not editable. rule() can lock it further."""
        self._controls.append((prep(widget), rule))
        return widget

    def iter_controls(self):
        return self._controls

    def add_setting(self, label, default, rule=None):
        var = tk.StringVar(value=default)
        row = tk.Frame(self.settings, bg=PANEL)
        row.pack(fill="x", pady=3)
        self.track(tk.Label(row, text=label, font=FONT_BODY, fg=TEXT, bg=PANEL),
                   rule).pack(side="left")
        self.track(RoundEntry(row, var), rule).pack(side="right")
        return var

    def add_dropdown(self, label, values, default, rule=None):
        var = tk.StringVar(value=default)
        row = tk.Frame(self.settings, bg=PANEL)
        row.pack(fill="x", pady=3)
        self.track(tk.Label(row, text=label, font=FONT_BODY, fg=TEXT, bg=PANEL),
                   rule).pack(side="left")
        self.track(RoundDropdown(row, var, values), rule).pack(side="right")
        return var

    def build_settings(self):
        pass

    def prepare(self):
        """Checks this tool's settings before it starts. Return False to refuse."""
        return True

    def reset_to_defaults(self):
        if not self.editable():
            return
        if self.reset_defaults_callback is None:
            self.note_var.set("Default settings are unavailable.")
            return
        if self.reset_confirmation_pending:
            if self.reset_confirmation_job is not None:
                self.after_cancel(self.reset_confirmation_job)
                self.reset_confirmation_job = None
            self.reset_confirmation_pending = False
            self.reset_button.set_text("Reset to Default")
            self.reset_defaults_callback(self)
            return
        self.reset_confirmation_pending = True
        self.reset_button.set_text("Are You Sure?")
        self.reset_confirmation_job = self.after(
            4000, self._expire_reset_confirmation)

    def _expire_reset_confirmation(self):
        self.reset_confirmation_pending = False
        self.reset_confirmation_job = None
        if self.reset_button is not None and self.reset_button.winfo_exists():
            self.reset_button.set_text("Reset to Default")

    def on_begin(self):
        pass

    def on_stop(self):
        pass

    def worker(self, sid):
        pass

    def idle_check(self):
        """Called every refresh. Subclasses can react to other tools stopping."""
        pass

    def delay_enabled(self):
        """The tool's own start delay is ignored while it's ticked for Start Selected."""
        return not (self.INCLUDABLE and self.include_var.get())

    def is_locked(self):
        """True while this tool runs or counts down, or while another tool blocks it."""
        if not self.RUNNABLE:
            return False
        return (self.running or self.countdown_job is not None
                or self.controller.blocked_by(self) is not None)

    def editable(self):
        return not self.is_locked()

    def _apply_locks(self):
        locked = self.is_locked()
        for widget, rule in self.iter_controls():
            enabled = (not locked) and (rule is None or rule())
            paint(widget, enabled)

    def toggle(self):
        if not self.RUNNABLE:
            return
        if self.running or self.countdown_job is not None:
            self.stop()
        else:
            self.start()

    def acquire(self):
        """Takes this tool's run slot. Start Selected overrides this, since it holds no slot."""
        return self.controller.claim(self)

    def alive(self, sid):
        return self.running and self.session == sid

    def paused_now(self):
        """True while Autoeat is eating and this tool should hold still."""
        return self.PAUSABLE and self.controller.others_paused.is_set()

    def pause_point(self, sid):
        """Call before each input and during waits. While Autoeat eats, releases any input
        this tool is holding, waits for eating to finish, then presses it again. Returns
        False if the tool was stopped, so the caller should return."""
        if not self.paused_now():
            return self.alive(sid)
        with self._input_lock:
            if not self.alive(sid):
                return False
            self.pause_inputs()
        while self.alive(sid) and self.controller.others_paused.is_set():
            time.sleep(0.02)
        with self._input_lock:
            if not self.alive(sid):
                return False
            self.resume_inputs()
        return True

    def pause_inputs(self):
        """Releases any key or button this tool holds. Tools that hold input override this."""
        pass

    def resume_inputs(self):
        """Presses again whatever pause_inputs released. Tools that hold input override this."""
        pass

    def sleep_while_alive(self, sid, seconds):
        """Sleeps for the given time. Time spent paused by Autoeat does not count toward it."""
        remaining = seconds
        last = time.perf_counter()
        while self.alive(sid):
            if self.paused_now():
                if not self.pause_point(sid):
                    return False
                last = time.perf_counter()
                continue
            now = time.perf_counter()
            remaining -= now - last
            last = now
            if remaining <= 0:
                return True
            time.sleep(min(0.02, remaining))
        return False

    def hold_until_stopped(self, sid):
        while self.alive(sid):
            if not self.pause_point(sid):
                return
            time.sleep(0.02)

    def parse_delay(self):
        if not self.delay_enabled():
            self.delay_seconds = float(DELAY_SECONDS)
            return True
        try:
            value = float(self.delay_var.get())
            if value < 0:
                raise ValueError
        except ValueError:
            self.note_var.set("Start delay must be a number, 0 or more.")
            return False
        self.delay_seconds = value
        return True

    def start(self):
        """Starts with the countdown from this tool's own delay."""
        if not self.RUNNABLE:
            return
        if self.running or self.countdown_job is not None:
            return
        if not self.parse_delay():
            return
        if not self.prepare():
            return
        if not self.acquire():
            blocker = self.controller.blocked_by(self)
            if blocker is not None:
                self._show_conflict(blocker)
            return
        self.session += 1
        self.countdown_left = int(round(self.delay_seconds))
        self.note_var.set("")
        self.tick()

    def launch_now(self):
        """Starts right away with no countdown. Used by Start Selected. Returns True if running."""
        if not self.RUNNABLE:
            return False
        if self.running:
            return True
        if not self.prepare():
            return False
        if not self.acquire():
            return False
        self.session += 1
        self.note_var.set("")
        self.begin()
        return True

    def tick(self):
        if self.countdown_left > 0:
            self.countdown_left -= 1
            self.countdown_job = self.after(1000, self.tick)
        else:
            self.countdown_job = None
            self.begin()

    def begin(self):
        self.running = True
        self.on_begin()
        threading.Thread(target=self.worker, args=(self.session,), daemon=True).start()

    def stop(self):
        if not (self.running or self.countdown_job is not None):
            return
        if self.countdown_job is not None:
            self.after_cancel(self.countdown_job)
            self.countdown_job = None
        with self._input_lock:
            self.running = False
            self.countdown_left = 0
            self.on_stop()
        self.controller.release(self)

    def _style_toggle(self, text, bg, fg, hover, enabled):
        self.toggle_btn.set_text(text)
        self.toggle_btn.set_style(bg, fg, hover, enabled)

    def _conflict_message(self, blocker):
        if self.GROUP == "Run Once":
            if self.controller.exclusive is not None:
                if self.controller.exclusive.GROUP == "Run Once":
                    return "Stop the active Run Once tool before starting another Run Once tool."
                active_groups = [self.controller.exclusive.GROUP]
            else:
                active_groups = []
            if self.controller.running_simultaneous:
                active_groups.insert(0, "Simultaneous")
            groups = " and ".join(active_groups)
            unit = "module" if len(active_groups) == 1 else "modules"
            return (f"Stop the active {groups} {unit} before starting a Run Once tool."
                    if active_groups else f"{blocker.module_name} is running.")
        if blocker.GROUP == "Run Once":
            return f"Stop {blocker.module_name} before starting other tools."
        return (f"{blocker.module_name} is running. "
                "Only one Independent tool can run at a time.")

    def _show_conflict(self, blocker):
        self.note_var.set(self._conflict_message(blocker))
        self._showing_conflict = True

    def _refresh(self):
        blocker = self.controller.blocked_by(self)
        if self.RUNNABLE:
            if self.running:
                self._style_toggle("\u25A0  Stop", RED, ON_RED, RED_HOVER, True)
            elif self.countdown_job is not None:
                self._style_toggle(f"Cancel  {self.countdown_left + 1}s", YELLOW, ON_YELLOW,
                                   YELLOW_HOVER, True)
            elif blocker is not None:
                self._show_conflict(blocker)
                self._style_toggle("Locked", OFF_BG, MUTED, OFF_BG, False)
            else:
                if self._showing_conflict:
                    self.note_var.set("")
                    self._showing_conflict = False
                self._style_toggle("\u25B6  Start", GREEN, ON_GREEN, GREEN_HOVER, True)
        self.idle_check()
        self._apply_locks()
        self.after(150, self._refresh)


def ease_in(t):
    """Starts slow and speeds up. t runs from 0 to 1."""
    return t * t


def ease_out(t):
    """Starts fast and slows down. t runs from 0 to 1."""
    return 1 - (1 - t) * (1 - t)


def ease_in_out(t):
    """Slow at both ends, fast in the middle. t runs from 0 to 1."""
    return t * t * (3 - 2 * t)


class AutofishTab(ModuleFrame):
    """Right-clicks while the fish-bite notice is visible, then once more to recast."""

    GROUP = "Independent"

    def __init__(self, parent, controller):
        self._worker_error = None
        self.poll_interval = DEFAULT_SCREEN_POLL_INTERVAL_MS / 1000
        self.crouch_enabled = False
        self.crouch_vk = parse_key("c")
        self._crouch_lock = threading.Lock()
        self._crouch_held = False
        self.spot_enabled = False
        self.swap_enabled = False
        self.rod_slot_vk = None
        self.no_bite_timeout = 45
        self.flare_enabled = False
        self.flare_interval = 70
        self.flare_slot_vk = None
        self.last_flare_at = 0.0
        self.spot_min = 0
        self.spot_max = 0
        self.spot_limit = 0
        self.spot_offset = 0
        self.spot_vertical_min = 0
        self.spot_vertical_max = 0
        self.spot_vertical_limit = 0
        self.spot_vertical_offset = 0
        super().__init__(parent, controller, "Autofish",
                         "Watches for the fish-bite notification near the center of the "
                         "screen, repeatedly right-clicks while it is visible, then "
                         "right-clicks once more to recast after it disappears. Casts once "
                         "when started and waits for the screen to clear before watching "
                         "for another bite. Optionally turns the view sideways by a random "
                         "amount after each catch, so the next cast lands in a different spot, "
                         "never further than the drift limit from where the run started. Each "
                         "new spot is reached in one smooth diagonal motion, with a random "
                         "up or down change within its own drift limit. Optionally swaps to the fishing rod slot "
                         "once when started.")

    def build_settings(self):
        self.poll_var = self.add_setting(
            "Screen poll interval (ms)", str(DEFAULT_SCREEN_POLL_INTERVAL_MS))
        self.crouch_var = self.add_dropdown("Crouch while fishing", ("No", "Yes"), "No")
        self.no_bite_var = self.add_setting("No-bite recast after (seconds)", "45")
        self.swap_var = self.add_dropdown("Swap to fishing rod at start", ("No", "Yes"), "No")
        self.rod_slot_var = self.add_dropdown("Fishing rod slot", AUTOEAT_SLOT_ORDER, "8",
                                              rule=self.swap_on)
        self.flare_var = self.add_dropdown("Throw Glowtide Flare (Skyblock)", ("No", "Yes"), "No",
                                           rule=self.swap_on)
        self.flare_interval_var = self.add_setting("Flare interval (seconds)", "70",
                                                   rule=self.flare_settings_on)
        self.flare_slot_var = self.add_dropdown("Flare slot", AUTOEAT_SLOT_ORDER, "9",
                                                rule=self.flare_settings_on)
        self.spot_var = self.add_dropdown("Switch spots after each catch", ("No", "Yes"), "No")
        self.spot_min_var = self.add_setting("Spot turn minimum (px)", "150",
                                             rule=self.spot_switching_on)
        self.spot_max_var = self.add_setting("Spot turn maximum (px)", "500",
                                             rule=self.spot_switching_on)
        self.spot_limit_var = self.add_setting("Max drift from start (px)", "600",
                                               rule=self.spot_switching_on)
        self.spot_vertical_min_var = self.add_setting("Vertical change minimum (px)", "40",
                                                      rule=self.spot_switching_on)
        self.spot_vertical_max_var = self.add_setting("Vertical change maximum (px)", "160",
                                                      rule=self.spot_switching_on)
        self.spot_vertical_limit_var = self.add_setting(
            "Max vertical drift from start (px)", "240", rule=self.spot_switching_on)

    def spot_switching_on(self):
        """The spot turn settings only apply while switching spots is set to Yes."""
        return self.spot_var.get() == "Yes"

    def swap_on(self):
        """The fishing rod slot only applies while swapping to the rod is set to Yes."""
        return self.swap_var.get() == "Yes"

    def flare_settings_on(self):
        """The flare interval and slot only apply while the flare is on, and that needs the rod swap."""
        return self.swap_var.get() == "Yes" and self.flare_var.get() == "Yes"

    def prepare(self):
        if Image is None or ImageGrab is None:
            self.note_var.set("Autofish needs Pillow for screen capture. Run: pip install pillow")
            return False
        if not OCR_AVAILABLE:
            self.note_var.set("Autofish needs Windows OCR support.")
            return False
        try:
            self.poll_interval = parse_screen_poll_interval(self.poll_var.get())
        except ValueError:
            self.note_var.set("Screen poll interval must be a whole number from "
                              f"{MIN_SCREEN_POLL_INTERVAL_MS} to "
                              f"{MAX_SCREEN_POLL_INTERVAL_MS} milliseconds.")
            return False
        if self.crouch_var.get() not in ("No", "Yes"):
            self.note_var.set("Choose Yes or No for crouching while fishing.")
            return False
        if self.spot_var.get() not in ("No", "Yes"):
            self.note_var.set("Choose Yes or No for switching spots.")
            return False
        spot_enabled = self.spot_var.get() == "Yes"
        if spot_enabled:
            try:
                self.spot_min, self.spot_max, self.spot_limit = parse_spot_range(
                    self.spot_min_var.get(), self.spot_max_var.get(),
                    self.spot_limit_var.get())
            except ValueError:
                self.note_var.set("Spot settings must be whole pixels: minimum at least 1, no "
                                  "more than the maximum, drift limit at least the minimum, "
                                  f"all up to {SPOT_MAX_PX}.")
                return False
            try:
                (self.spot_vertical_min, self.spot_vertical_max,
                 self.spot_vertical_limit) = parse_vertical_range(
                    self.spot_vertical_min_var.get(), self.spot_vertical_max_var.get(),
                    self.spot_vertical_limit_var.get())
            except ValueError:
                self.note_var.set("Vertical settings must be whole pixels: minimum at least 1, no "
                                  "more than the maximum, drift limit at least the minimum, all up "
                                  f"to {SPOT_VERTICAL_MAX_PX}. A maximum of 0 turns it off.")
                return False
        try:
            self.no_bite_timeout = parse_no_bite_timeout(self.no_bite_var.get())
        except ValueError:
            self.note_var.set("No-bite recast time must be a whole number of seconds from 10 to 300.")
            return False
        if self.swap_var.get() not in ("No", "Yes"):
            self.note_var.set("Choose Yes or No for swapping to the fishing rod.")
            return False
        self.swap_enabled = self.swap_var.get() == "Yes"
        if self.swap_enabled:
            if self.rod_slot_var.get() not in AUTOEAT_SLOT_ORDER:
                self.note_var.set("Choose a hotbar slot from 1 to 9 or 0 for the fishing rod.")
                return False
            self.rod_slot_vk = parse_key(self.rod_slot_var.get())
        if self.flare_var.get() not in ("No", "Yes"):
            self.note_var.set("Choose Yes or No for throwing the Glowtide Flare.")
            return False
        self.flare_enabled = self.swap_enabled and self.flare_var.get() == "Yes"
        if self.flare_enabled:
            try:
                self.flare_interval = parse_flare_interval(self.flare_interval_var.get())
            except ValueError:
                self.note_var.set("Flare interval must be a whole number of seconds from 10 to 3600.")
                return False
            flare_slot = self.flare_slot_var.get()
            if flare_slot not in AUTOEAT_SLOT_ORDER or flare_slot == self.rod_slot_var.get():
                self.note_var.set("Choose a flare slot from 1 to 9 or 0, different from the "
                                  "fishing rod slot.")
                return False
            self.flare_slot_vk = parse_key(flare_slot)
        self.spot_enabled = spot_enabled
        self.crouch_enabled = self.crouch_var.get() == "Yes"
        return True

    def on_begin(self):
        self._worker_error = None
        self.spot_offset = 0
        self.last_flare_at = time.perf_counter()
        self.spot_vertical_offset = 0

    def on_stop(self):
        self._release_crouch()

    def pause_inputs(self):
        self._release_crouch()

    def resume_inputs(self):
        if self.crouch_enabled:
            with self._crouch_lock:
                key_down(self.crouch_vk)
                self._crouch_held = True

    def _release_crouch(self):
        with self._crouch_lock:
            if self._crouch_held:
                key_up(self.crouch_vk)
                self._crouch_held = False

    def idle_check(self):
        if self._worker_error is not None:
            message = self._worker_error
            self._worker_error = None
            if self.running:
                self.stop()
            self.note_var.set(message)

    @staticmethod
    def _bounded_turn(low, high, limit, offset):
        """Picks a signed turn of low to high whole pixels that keeps the view within limit of its
        starting angle, given how far it already is at offset. Never zero."""
        rooms = {1: limit - offset, -1: limit + offset}
        directions = [d for d in (1, -1) if rooms[d] >= low]
        direction = random.choice(directions)
        return direction * random.randint(low, min(high, rooms[direction]))

    def pick_spot_turn(self):
        """Picks the next sideways turn, left or right, within the horizontal drift limit."""
        return self._bounded_turn(self.spot_min, self.spot_max, self.spot_limit, self.spot_offset)

    def pick_vertical_turn(self):
        """Picks the next up-or-down change, within the vertical drift limit, or 0 when it is off."""
        if self.spot_vertical_max <= 0:
            return 0
        return self._bounded_turn(self.spot_vertical_min, self.spot_vertical_max,
                                  self.spot_vertical_limit, self.spot_vertical_offset)

    def move_view_diagonal(self, sid, dx, dy):
        """Moves the view in one straight diagonal line, dx sideways and dy up or down, with a
        random ease in, out, or both. Pauses with Autoeat like the other inputs. Returns False if
        the run was stopped."""
        length = math.hypot(dx, dy)
        if length < 1:
            return True
        ease = random.choice((ease_in, ease_out, ease_in_out))
        duration = length / AUTOFISH_TURN_PIXELS_PER_SECOND
        moved_x = moved_y = 0
        elapsed = 0.0
        last = time.perf_counter()
        while self.alive(sid):
            if self.paused_now():
                if not self.pause_point(sid):
                    return False
                last = time.perf_counter()
                continue
            now = time.perf_counter()
            elapsed += now - last
            last = now
            progress = min(1.0, elapsed / duration)
            eased = ease(progress)
            target_x, target_y = round(dx * eased), round(dy * eased)
            if (target_x, target_y) != (moved_x, moved_y):
                move_rel(target_x - moved_x, target_y - moved_y)
                moved_x, moved_y = target_x, target_y
            if progress >= 1.0:
                return True
            time.sleep(MOUSE_STREAM_TICK)
        return False

    def flare_due(self, now):
        """True when the flare is on and its interval has passed since the last throw."""
        return self.flare_enabled and now - self.last_flare_at >= self.flare_interval

    def throw_flare(self, sid):
        """Switches to the flare slot, throws it with a right click, and switches back to the rod.
        Each step waits for Autoeat to be done, like the other inputs. Returns False if stopped."""
        if not self.pause_point(sid):
            return False
        tap_key(self.flare_slot_vk)
        if not self.sleep_while_alive(sid, AUTOFISH_ROD_SWAP_SETTLE_SECONDS):
            return False
        if not self.pause_point(sid):
            return False
        button_click("Right")
        if not self.sleep_while_alive(sid, AUTOFISH_FLARE_THROW_SECONDS):
            return False
        if not self.pause_point(sid):
            return False
        tap_key(self.rod_slot_vk)
        return self.sleep_while_alive(sid, AUTOFISH_ROD_SWAP_SETTLE_SECONDS)

    def turn_to_new_spot(self, sid):
        """Moves the view to a new spot in one diagonal motion: sideways within the horizontal drift
        limit and up or down within the vertical one. Returns False if stopped."""
        dx = self.pick_spot_turn()
        dy = self.pick_vertical_turn()
        if not self.move_view_diagonal(sid, dx, dy):
            return False
        self.spot_offset += dx
        self.spot_vertical_offset += dy
        return self.sleep_while_alive(sid, LOOK_SETTLE_SECONDS)

    async def watch(self, sid):
        engine = get_ocr_engine()

        notice = None
        notification_was_visible = False
        clear_reads = 0
        waiting_for_rearm = True
        rearm_clear_reads = 0
        last_spam_click_at = None
        if self.flare_enabled:
            if not self.throw_flare(sid):
                return
            self.last_flare_at = time.perf_counter()
        elif self.swap_enabled:
            if not self.pause_point(sid):
                return
            tap_key(self.rod_slot_vk)
            if not self.sleep_while_alive(sid, AUTOFISH_ROD_SWAP_SETTLE_SECONDS):
                return
        if self.pause_point(sid):
            button_click("Right")
        cast_at = time.perf_counter()
        while self.alive(sid):
            if not self.pause_point(sid):
                return
            poll_started = time.perf_counter()
            found = None
            if notice is not None:
                shot, origin = grab_screen(notice)
                found = await find_autofish_notice(shot, engine, origin)
            if found is None:
                shot, origin = grab_screen()
                found = await find_autofish_notice(shot, engine, origin)
            if not self.alive(sid):
                return
            visible = found is not None
            notice = tracking_box(*found) if visible else None
            if waiting_for_rearm:
                if visible:
                    rearm_clear_reads = 0
                else:
                    rearm_clear_reads += 1
                if rearm_clear_reads >= AUTOFISH_CLEAR_CONFIRM_READS:
                    waiting_for_rearm = False
                    rearm_clear_reads = 0
                clear_reads = 0
            elif visible:
                clear_reads = 0
                notification_was_visible = True
                now = time.perf_counter()
                if (last_spam_click_at is None
                        or now - last_spam_click_at >= AUTOFISH_CLICK_INTERVAL_SECONDS):
                    if not self.pause_point(sid):
                        return
                    button_click("Right")
                    last_spam_click_at = time.perf_counter()
            elif notification_was_visible:
                clear_reads += 1
                if clear_reads >= AUTOFISH_CLEAR_CONFIRM_READS:
                    await asyncio.sleep(AUTOFISH_RECAST_SETTLE_SECONDS)
                    if self.flare_due(time.perf_counter()):
                        if not self.throw_flare(sid):
                            return
                        self.last_flare_at = time.perf_counter()
                    if self.spot_enabled and not self.turn_to_new_spot(sid):
                        return
                    if self.pause_point(sid):
                        button_click("Right")
                        cast_at = time.perf_counter()
                        waiting_for_rearm = True
                        rearm_clear_reads = 0
                    notification_was_visible = False
                    clear_reads = 0
                    last_spam_click_at = None
            else:
                clear_reads = 0
                if time.perf_counter() - cast_at >= self.no_bite_timeout:
                    if self.flare_due(time.perf_counter()):
                        if not self.throw_flare(sid):
                            return
                        self.last_flare_at = time.perf_counter()
                    if self.pause_point(sid):
                        button_click("Right")
                        cast_at = time.perf_counter()
                        waiting_for_rearm = True
                        rearm_clear_reads = 0
            await asyncio.sleep(max(
                0, self.poll_interval - (time.perf_counter() - poll_started)))

    def worker(self, sid):
        try:
            with self._crouch_lock:
                if self.alive(sid) and self.crouch_enabled:
                    key_down(self.crouch_vk)
                    self._crouch_held = True
            asyncio.run(self.watch(sid))
        except Exception as error:
            if self.alive(sid):
                detail = str(error) or type(error).__name__
                self._worker_error = f"Autofish stopped: {detail}"
        finally:
            self._release_crouch()


class GridPathTab(ModuleFrame):
    """Draw a path on a grid by dragging. The movement keys walk it and loop."""

    GROUP = "Independent"
    CANVAS_PX = 300
    VIEWPORT_PX = GRID_VIEWPORT_PX
    MIN_CELL_PX = MIN_GRID_CELL_PX

    def __init__(self, parent, controller):
        self.cols = DEFAULT_GRID
        self.rows = DEFAULT_GRID
        self.path = []
        self.runs = []
        self.space_pause_seconds = 0.0
        self.held_vk = None
        self._last_btn_state = None
        super().__init__(parent, controller, "Grid Path",
                         "Drag on the grid to draw the path. Uses WASD to walk "
                         "and loop back to the start. I recommend using Align to "
                         "align your player to a cardinal direction before"
                         "starting to prevent drifting off path. ")

    def build_settings(self):
        size_row = tk.Frame(self.settings, bg=PANEL)
        size_row.pack(fill="x", pady=3)
        self.track(tk.Label(size_row, text="Grid size (cols x rows)", font=FONT_BODY,
                            fg=TEXT, bg=PANEL)).pack(side="left")

        self.set_btn = RoundButton(size_row, text="Set", font=FONT_SMALL, bg=OFF_BG, fg=TEXT,
                                   hover=OFF_HOVER, padx=10, command=self.apply_size)
        self.set_btn.pack(side="right")
        self.clear_btn = RoundButton(size_row, text="Clear", font=FONT_SMALL, bg=OFF_BG,
                                     fg=TEXT, hover=OFF_HOVER, padx=10,
                                     command=self.clear_path)
        self.clear_btn.pack(side="right", padx=6)

        self.rows_var = tk.StringVar(value=str(self.rows))
        self.cols_var = tk.StringVar(value=str(self.cols))
        self.rows_entry = RoundEntry(size_row, self.rows_var, width=4)
        self.track(self.rows_entry).pack(side="right")
        self.track(tk.Label(size_row, text="x", font=FONT_BODY, fg=MUTED,
                            bg=PANEL)).pack(side="right", padx=4)
        self.cols_entry = RoundEntry(size_row, self.cols_var, width=4)
        self.track(self.cols_entry).pack(side="right")

        self.rows_entry.bind("<Configure>", lambda _e: self._match_size_row(), add="+")
        self.after_idle(self._match_size_row)

        self.space_pause_var = self.add_setting("Pause between grid spaces (seconds)", "0")

        grid_box = RoundBox(self.settings, fill=INPUT, outline=BORDER,
                            radius=RADIUS_CARD, pad=8)
        grid_box.pack(fill="x", pady=(10, 4))
        self.grid_box = grid_box
        self._grid_resize_job = None
        self.grid_row = tk.Frame(grid_box.inner, bg=INPUT)
        self.grid_row.pack(fill="x")
        self.canvas = tk.Canvas(self.grid_row, width=self.CANVAS_PX + 1,
                                height=self.CANVAS_PX + 1, bg=INPUT, highlightthickness=0,
                                xscrollincrement=1, yscrollincrement=1)
        self.canvas.pack(side="left")
        self.grid_vbar = SmoothScrollBar(
            self.grid_row, command=self.canvas.yview, length=self.CANVAS_PX,
            orient="vertical")
        self.grid_hbar = SmoothScrollBar(
            grid_box.inner, command=self.canvas.xview, length=self.CANVAS_PX,
            orient="horizontal")
        self.grid_hbar.pack(anchor="w", pady=(8, 2))
        self.canvas.configure(xscrollcommand=self.grid_hbar.set,
                              yscrollcommand=self.grid_vbar.set)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonPress-3>", self.on_clear)
        self.canvas.bind("<MouseWheel>", self.on_grid_wheel, add="+")
        grid_box.inner.bind("<Configure>", self._on_grid_resize, add="+")

        self.info_var = tk.StringVar(value="")
        tk.Label(self.settings, textvariable=self.info_var, font=FONT_SMALL,
                 fg=MUTED, bg=PANEL).pack(anchor="w")
        self.draw()

    def _match_size_row(self):
        h = self.rows_entry.winfo_reqheight()
        if h > 1:
            self.set_btn.set_height(h)
            self.clear_btn.set_height(h)

    def _apply_locks(self):
        super()._apply_locks()
        on = self.editable()
        if on != self._last_btn_state:
            self._last_btn_state = on
            for btn in (self.set_btn, self.clear_btn):
                btn.set_style(OFF_BG, TEXT if on else DISABLED_FG, OFF_HOVER, on)

    def cell_size(self):
        return max(self.MIN_CELL_PX,
                   min(self.CANVAS_PX // self.cols, self.CANVAS_PX // self.rows))

    def cell_at(self, event):
        size = self.cell_size()
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        c, r = int(x // size), int(y // size)
        if 0 <= c < self.cols and 0 <= r < self.rows:
            return (c, r)
        return None

    def on_grid_wheel(self, event):
        horizontal = bool(event.state & 0x0001)
        first, last = self.canvas.xview() if horizontal else self.canvas.yview()
        if last - first >= 1.0 or not event.delta:
            return
        step = (-GRID_WHEEL_SCROLL_UNITS if event.delta > 0
                else GRID_WHEEL_SCROLL_UNITS)
        if horizontal:
            self.canvas.xview_scroll(step, "units")
        else:
            self.canvas.yview_scroll(step, "units")
        return "break"

    def _on_grid_resize(self, _event=None):
        if self._grid_resize_job is None:
            self._grid_resize_job = self.after_idle(self._redraw_after_resize)

    def _redraw_after_resize(self):
        self._grid_resize_job = None
        self._update_viewport()

    def _update_viewport(self):
        cv = self.canvas
        size = self.cell_size()
        grid_width = self.cols * size + 1
        grid_height = self.rows * size + 1
        viewport_height = min(self.VIEWPORT_PX, grid_height)
        available_width = self.grid_box.inner.winfo_width()
        if available_width <= 1:
            available_width = self.VIEWPORT_PX
        vertical_bar_width = (SmoothScrollBar.THICKNESS + 8
                              if grid_height > viewport_height else 0)
        viewport_width = min(grid_width, max(1, available_width - vertical_bar_width))
        cv.configure(width=viewport_width, height=viewport_height,
                     scrollregion=(0, 0, grid_width, grid_height))
        self.grid_hbar.configure(width=viewport_width)
        self.grid_vbar.configure(width=SmoothScrollBar.THICKNESS, height=viewport_height)
        if grid_width > viewport_width:
            if not self.grid_hbar.winfo_manager():
                self.grid_hbar.pack(anchor="w", pady=(8, 2))
        else:
            self.grid_hbar.pack_forget()
        if grid_height > viewport_height:
            if not self.grid_vbar.winfo_manager():
                self.grid_vbar.pack(side="left", fill="y", padx=(8, 0))
        else:
            self.grid_vbar.pack_forget()

    def draw(self):
        cv = self.canvas
        self._update_viewport()
        cv.delete("all")
        size = self.cell_size()
        for c in range(self.cols):
            for r in range(self.rows):
                x0, y0 = c * size, r * size
                cv.create_rectangle(x0, y0, x0 + size, y0 + size,
                                    outline=BORDER, fill=INPUT)
        self.draw_path(size)

    def draw_path(self, size=None):
        cv = self.canvas
        cv.delete("path")
        if size is None:
            size = self.cell_size()
        if self.path:
            def mid(cell):
                return cell[0] * size + size / 2, cell[1] * size + size / 2

            width = max(2, size // 6)
            if len(self.path) > 1:
                pts = []
                for cell in self.path:
                    pts.extend(mid(cell))
                cv.create_line(*pts, fill=GREEN, width=width,
                               capstyle="round", joinstyle="round", tags=("path",))
            closing = [self.path[-1]] + route(self.path[-1], self.path[0])
            if len(closing) > 1:
                pts = []
                for cell in closing:
                    pts.extend(mid(cell))
                cv.create_line(*pts, fill=GREEN, width=max(1, width - 1),
                               dash=(4, 4), tags=("path",))
            sx, sy = mid(self.path[0])
            rad = size / 4
            cv.create_oval(sx - rad, sy - rad, sx + rad, sy + rad,
                           fill=TEXT, outline=GREEN, width=2, tags=("path",))
        self.update_info()

    def update_info(self):
        if len(self.path) < 2:
            self.info_var.set("Drag on the grid to draw a path (at least 2 cells).")
            return
        runs = build_runs(self.path)
        tiles = sum(t for _, _, t in runs)
        self.info_var.set(f"{len(self.path)} cells  |  {tiles} tiles per loop  |  "
                          f"{tiles * TILE_SECONDS:.2f}s per loop")

    def on_press(self, event):
        if not self.editable():
            return
        cell = self.cell_at(event)
        if cell is None:
            return
        self.note_var.set("")
        self.path = [cell]
        self.draw_path()

    def on_drag(self, event):
        if not self.editable() or not self.path:
            return
        cell = self.cell_at(event)
        if cell is None or cell == self.path[-1]:
            return
        self.path += route(self.path[-1], cell)
        self.draw_path()

    def on_clear(self, event):
        self.clear_path()

    def clear_path(self):
        if not self.editable():
            return
        self.path = []
        self.note_var.set("")
        self.draw_path()

    def apply_size(self):
        if not self.editable():
            return
        try:
            cols = int(self.cols_var.get())
            rows = int(self.rows_var.get())
            if not (2 <= cols <= MAX_GRID_SIZE and 2 <= rows <= MAX_GRID_SIZE):
                raise ValueError
        except ValueError:
            self.note_var.set(f"Grid size must be whole numbers from 2 to "
                              f"{MAX_GRID_SIZE}.")
            return
        self.cols, self.rows = cols, rows
        self.path = []
        self.note_var.set("")
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.draw()

    def prepare(self):
        if len(self.path) < 2:
            self.note_var.set("Draw a path first. Drag at least 2 cells on the grid.")
            return False
        try:
            self.space_pause_seconds = parse_grid_space_pause(self.space_pause_var.get())
        except ValueError:
            self.note_var.set("Pause between grid spaces must be a finite number, 0 or more.")
            return False
        self.runs = build_runs(self.path)
        return True

    def on_stop(self):
        if self.held_vk is not None:
            key_up(self.held_vk)
            self.held_vk = None

    def pause_inputs(self):
        if self.held_vk is not None:
            key_up(self.held_vk)

    def resume_inputs(self):
        if self.held_vk is not None:
            key_down(self.held_vk)

    def press(self, sid, vk, seconds):
        if not self.pause_point(sid):
            return False
        self.held_vk = vk
        key_down(vk)
        alive = self.sleep_while_alive(sid, seconds)
        key_up(vk)
        self.held_vk = None
        return alive

    def worker(self, sid):
        while self.alive(sid):
            for vk, _name, tiles in self.runs:
                if self.space_pause_seconds == 0:
                    if not self.press(sid, vk, tiles * TILE_SECONDS):
                        return
                    continue
                for _ in range(tiles):
                    if not self.press(sid, vk, TILE_SECONDS):
                        return
                    if not self.sleep_while_alive(sid, self.space_pause_seconds):
                        return


class ActiveModulesTab(ModuleFrame):
    """Controls the on-screen list of currently running modules."""

    GROUP = "EXTRAS"
    INCLUDABLE = False
    RUNNABLE = False

    def __init__(self, parent, controller, app, saved_settings):
        self.app = app
        self.saved_settings = saved_settings
        super().__init__(parent, controller, "Active Modules",
                         "Shows the modules that are currently running.")

    def build_settings(self):
        self.overlay_var = self.add_dropdown(
            "Show overlay", ("No", "Yes"), self.saved_settings["list_active_modules"])
        self.position_var = self.add_dropdown(
            "Overlay position", OVERLAY_POSITIONS,
            self.saved_settings["active_modules_position"])
        self.hide_when_idle_var = self.add_dropdown(
            "Hide when idle", ("No", "Yes"),
            self.saved_settings["hide_active_modules_when_idle"])
        self.overlay_var.trace_add("write", self._sync_visibility)
        self.hide_when_idle_var.trace_add("write", self._sync_visibility)
        self.position_var.trace_add("write", self._sync_position)

    def _sync_visibility(self, *_args):
        self.app.refresh_active_modules_overlay()
        self.app.save_app_settings()

    def _sync_position(self, *_args):
        self.app.reposition_overlays()
        self.app.save_app_settings()


class CoordinatesTab(ModuleFrame):
    """Keeps a user-editable list of named XYZ coordinates."""

    GROUP = "EXTRAS"
    INCLUDABLE = False
    RUNNABLE = False
    def __init__(self, parent, controller):
        self.rows = []
        super().__init__(parent, controller, "Coordinates",
                         "Stores a list of names and their X, Y, and Z coordinates.")

    def build_settings(self):
        self.rows_frame = tk.Frame(self.settings, bg=PANEL)
        self.header = tk.Frame(self.settings, bg=PANEL)
        self.header.pack(fill="x", pady=(2, 4))
        self.header_cells = []
        for column, label in enumerate(("Name", "X", "Y", "Z", "")):
            cell = tk.Label(self.header, text=label, font=FONT_SMALL, fg=MUTED,
                            bg=PANEL, anchor="w")
            cell.grid(row=0, column=column, sticky="w", padx=(0, 6))
            self.header_cells.append(cell)
        self.align_columns()

        buttons = tk.Frame(self.settings, bg=PANEL)
        buttons.pack(fill="x", pady=(6, 2))
        self.add_coordinate_button = self.track(RoundButton(
            buttons, text="+  Add Coordinate", font=FONT_SMALL, bg=OFF_BG,
            fg=TEXT, hover=OFF_HOVER, padx=10, pady=3,
            command=self.add_coordinate))
        self.add_coordinate_button.pack(side="left")

    def iter_controls(self):
        yield from self._controls
        for row in self.rows:
            for entry in row["entries"]:
                yield entry, None
            yield row["del_btn"], None

    def align_columns(self):
        columns = [[(cell, 6)] for cell in self.header_cells]
        for row in self.rows:
            for column, entry in enumerate(row["entries"]):
                columns[column].append((entry, 6))
            columns[4].append((row["del_btn"], 0))
        align_grid_columns([self.header] + [row["frame"] for row in self.rows], columns)

    def add_row(self, name="", x="", y="", z=""):
        if not self.rows:
            self.rows_frame.pack(fill="x", before=self.add_coordinate_button.master)
        frame = tk.Frame(self.rows_frame, bg=PANEL)
        frame.pack(fill="x", pady=2)
        values = (name, x, y, z)
        widths = (16, 8, 8, 8)
        variables = [tk.StringVar(value=value) for value in values]
        entries = []
        for column, (variable, width) in enumerate(zip(variables, widths)):
            entry = RoundEntry(frame, variable, width=width)
            entry.grid(row=0, column=column, sticky="w", padx=(0, 6), pady=1)
            entries.append(entry)

        del_btn = RoundButton(
            frame, text="\u00d7", font=(FONT_FAMILY, 12, "bold"), bg=OFF_BG, fg=RED,
            hover=OFF_HOVER, padx=0, pady=0, square=True,
            command=lambda: None)
        del_btn.grid(row=0, column=4, sticky="w", pady=1)
        row = {
            "frame": frame, "name": variables[0], "x": variables[1],
            "y": variables[2], "z": variables[3], "entries": entries,
            "del_btn": del_btn,
        }
        del_btn.rb_command = lambda item=row: self.remove_row(item)
        self.rows.append(row)
        self.align_columns()

    def add_coordinate(self):
        if not self.editable():
            return
        self.add_row()
        self.rows[-1]["entries"][0].entry.focus_set()

    def remove_row(self, row):
        if not self.editable():
            return
        row["frame"].destroy()
        self.rows.remove(row)
        if not self.rows:
            self.rows_frame.pack_forget()
        self.align_columns()


class CPSOverlayTab(ModuleFrame):
    """Visualizes the number of left clicks detected during the previous second."""

    GROUP = "EXTRAS"
    INCLUDABLE = False
    RUNNABLE = False
    DISPLAY_NAME = "CPS Visualizer"

    def __init__(self, parent, controller):
        self.click_times = deque()
        self.click_times_lock = threading.Lock()
        self.mouse_hook = None
        self.mouse_callback = HOOKPROC(self._mouse_proc)
        self.mouse_hook_thread = None
        self.mouse_hook_thread_id = 0
        self.hook_ready = threading.Event()
        self.hook_error = None
        self.counting_enabled = False
        self.overlay = None
        self.overlay_job = None
        self.overlay_layout_changed = None
        self.cps_var = tk.StringVar(value="0")
        super().__init__(parent, controller, "CPS",
                         "Shows the number of left mouse clicks during the previous second.")

    def build_settings(self):
        self.overlay_var = self.add_dropdown("Show overlay", ("No", "Yes"), "No")
        self.position_var = self.add_dropdown("Overlay position", OVERLAY_POSITIONS,
                                              "Top right")
        self.overlay_var.trace_add("write", self._sync_overlay)
        self.position_var.trace_add("write", self._sync_position)

    def _sync_overlay(self, *_args):
        if self.overlay_var.get() == "Yes":
            self.show_overlay()
        else:
            self.hide_overlay()

    def _sync_position(self, *_args):
        if self.overlay_layout_changed is not None:
            self.overlay_layout_changed()

    def show_overlay(self):
        if self.overlay is not None and self.overlay.winfo_exists():
            self._sync_position()
            return
        if self.mouse_hook_thread is not None and self.mouse_hook_thread.is_alive():
            self.note_var.set("CPS could not restart because its previous mouse hook is still active.")
            self.overlay_var.set("No")
            return

        self.note_var.set("")
        self.hook_error = None
        self.hook_ready.clear()
        with self.click_times_lock:
            self.click_times.clear()
        self.counting_enabled = True
        self.mouse_hook_thread = threading.Thread(
            target=self._mouse_hook_loop, name="CPSMouseHook", daemon=True)
        self.mouse_hook_thread.start()
        if not self.hook_ready.wait(2.0):
            self.counting_enabled = False
            self.note_var.set("Timed out while starting the global mouse hook for CPS.")
            self.overlay_var.set("No")
            self._stop_mouse_hook()
            return
        if self.hook_error:
            error = self.hook_error
            self.overlay_var.set("No")
            self.note_var.set(f"CPS could not start: {error}")
            return

        overlay = tk.Toplevel(self)
        self.overlay = overlay
        overlay.wm_overrideredirect(True)
        overlay.wm_attributes("-topmost", True)
        overlay.configure(bg=OVERLAY_TRANSPARENT)
        overlay.wm_attributes("-transparentcolor", OVERLAY_TRANSPARENT)

        panel = RoundBox(overlay, fill=PANEL, outline=GREEN,
                         radius=RADIUS_BTN, pad=RADIUS_BTN)
        panel.pack(fill="both", expand=True)
        tk.Label(panel.inner, text="CPS", font=(FONT_FAMILY, 9, "bold"),
                 fg=MUTED, bg=PANEL).pack(side="left", padx=(0, 10))
        tk.Label(panel.inner, textvariable=self.cps_var,
                 font=(FONT_FAMILY, 14, "bold"), fg=GREEN,
                 bg=PANEL, width=3, anchor="e").pack(side="left")

        try:
            make_window_clickthrough(overlay, OVERLAY_TRANSPARENT)
        except OSError as error:
            overlay.destroy()
            self.overlay = None
            self._stop_mouse_hook()
            self.overlay_var.set("No")
            self.note_var.set(f"Could not make CPS overlay click-through: {error}")
            return
        self._sync_position()
        self.refresh_overlay()

    def hide_overlay(self):
        if self.overlay_job is not None:
            self.after_cancel(self.overlay_job)
            self.overlay_job = None
        overlay = self.overlay
        self.overlay = None
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()
        self.counting_enabled = False
        self._stop_mouse_hook()
        with self.click_times_lock:
            self.click_times.clear()
        self.cps_var.set("0")
        self._sync_position()

    def _stop_mouse_hook(self):
        thread_id = self.mouse_hook_thread_id
        if thread_id and not user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0):
            self.hook_error = "Could not signal the CPS mouse hook to stop."
        thread = self.mouse_hook_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
            if thread.is_alive():
                self.hook_error = "The CPS mouse hook did not stop in time."
            else:
                self.mouse_hook_thread = None
        if self.hook_error:
            self.note_var.set(f"CPS hook: {self.hook_error}")

    def _mouse_hook_loop(self):
        mouse_hook = None
        message = wintypes.MSG()
        try:
            user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_NOREMOVE)
            self.mouse_hook_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            module_handle = ctypes.windll.kernel32.GetModuleHandleW(None)
            mouse_hook = user32.SetWindowsHookExW(
                WH_MOUSE_LL, self.mouse_callback, module_handle, 0)
            if not mouse_hook:
                raise RuntimeError("Could not install the global mouse hook.")
            self.mouse_hook = mouse_hook
            self.hook_ready.set()
            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise RuntimeError("The CPS mouse hook message loop failed.")
                if result == 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except (RuntimeError, OSError, ctypes.ArgumentError) as error:
            self.hook_error = str(error)
        finally:
            self.hook_ready.set()
            if mouse_hook and not user32.UnhookWindowsHookEx(mouse_hook):
                self.hook_error = self.hook_error or (
                    "Could not remove the global mouse hook.")
            self.mouse_hook = None
            self.mouse_hook_thread_id = 0

    def refresh_overlay(self):
        self.overlay_job = None
        if self.overlay is None or not self.overlay.winfo_exists():
            return
        now = time.perf_counter()
        with self.click_times_lock:
            while self.click_times and now - self.click_times[0] >= 1.0:
                self.click_times.popleft()
            count = len(self.click_times)
        self.cps_var.set(str(count))
        self.overlay_job = self.after(100, self.refresh_overlay)

    def _mouse_proc(self, code, message, data):
        if (self.counting_enabled and code == HC_ACTION
                and message == WM_LBUTTONDOWN):
            with self.click_times_lock:
                self.click_times.append(time.perf_counter())
        return user32.CallNextHookEx(None, code, message, data)

    def close(self):
        self.hide_overlay()


class KeyboardVisualizerTab(ModuleFrame):
    """Displays the current global state of selected movement keys."""

    GROUP = "EXTRAS"
    INCLUDABLE = False
    RUNNABLE = False
    MODULE_NAME = "Keyboard Visualizer"
    DESCRIPTION = "Visualizes the global pressed state of W, A, S, D, C, Space, and Shift."
    DEFAULT_POSITION = "Bottom left"
    POLL_INTERVAL_MS = 30
    KEY_CODES = {
        "W": VK_W,
        "A": VK_A,
        "S": VK_S,
        "D": VK_D,
        "C": VK_C,
        "Space": VK_SPACE,
        "Shift": VK_SHIFT,
    }
    KEY_POSITIONS = {
        "W": (0, 1),
        "A": (1, 0),
        "S": (1, 1),
        "D": (1, 2),
        "C": (2, 0),
        "Space": (2, 1),
        "Shift": (2, 2),
    }

    def __init__(self, parent, controller):
        self.key_boxes = {}
        self.overlay_key_boxes = {}
        self.key_states = {key_name: False for key_name in self.KEY_CODES}
        self.overlay = None
        self.overlay_layout_changed = None
        self.poll_job = None
        super().__init__(parent, controller, self.MODULE_NAME, self.DESCRIPTION)

    def build_settings(self):
        self.overlay_var = self.add_dropdown("Show on screen", ("No", "Yes"), "No")
        self.position_var = self.add_dropdown("Overlay position", OVERLAY_POSITIONS,
                                              self.DEFAULT_POSITION)
        self.overlay_var.trace_add("write", self._sync_overlay)
        self.position_var.trace_add("write", self._sync_position)
        self.key_boxes = self._create_key_boxes(self.settings)
        self.bind("<Map>", self._start_polling, add="+")
        self.bind("<Unmap>", self._stop_polling, add="+")

    def _create_key_boxes(self, parent):
        key_boxes = {}
        keys_frame = tk.Frame(parent, bg=PANEL)
        keys_frame.pack(fill="x", pady=4)
        for column in range(3):
            keys_frame.grid_columnconfigure(column, weight=1, uniform="keyboard_key")

        for key_name, (row, column) in self.KEY_POSITIONS.items():
            pressed = self.key_states[key_name]
            fill = GREEN if pressed else OFF_BG
            foreground = ON_GREEN if pressed else MUTED
            key_box = RoundBox(keys_frame, fill=fill,
                               outline=fill if pressed else BORDER,
                               radius=RADIUS_FIELD, pad=5)
            key_box.grid(row=row, column=column, sticky="nsew", padx=3, pady=3)
            label = tk.Label(key_box.inner, text=key_name,
                             font=(FONT_FAMILY, 10, "bold"),
                             fg=foreground, bg=fill, anchor="center")
            label.pack(fill="both", expand=True)
            key_boxes[key_name] = (key_box, label)
        return key_boxes

    def _sync_overlay(self, *_args):
        if self.overlay_var.get() == "Yes":
            self.show_overlay()
        else:
            self.hide_overlay()

    def _sync_position(self, *_args):
        if self.overlay_layout_changed is not None:
            self.overlay_layout_changed()

    def show_overlay(self):
        if self.overlay is not None and self.overlay.winfo_exists():
            self._sync_position()
            self._start_polling()
            return

        overlay = tk.Toplevel(self)
        self.overlay = overlay
        overlay.wm_overrideredirect(True)
        overlay.wm_attributes("-topmost", True)
        overlay.configure(bg=OVERLAY_TRANSPARENT)
        overlay.wm_attributes("-transparentcolor", OVERLAY_TRANSPARENT)
        panel = RoundBox(overlay, fill=PANEL, outline=GREEN,
                         radius=RADIUS_BTN, pad=RADIUS_BTN)
        panel.pack(fill="both", expand=True)
        self.overlay_key_boxes = self._create_key_boxes(panel.inner)
        try:
            make_window_clickthrough(overlay, OVERLAY_TRANSPARENT)
        except OSError as error:
            overlay.destroy()
            self.overlay = None
            self.overlay_key_boxes = {}
            self.overlay_var.set("No")
            self.note_var.set(f"Could not make keyboard overlay click-through: {error}")
            return
        self.note_var.set("")
        self._sync_position()
        self._start_polling()

    def hide_overlay(self):
        overlay = self.overlay
        self.overlay = None
        self.overlay_key_boxes = {}
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()
        if not self.winfo_ismapped():
            self._stop_polling()
        self._sync_position()

    def _start_polling(self, _event=None):
        if (self.poll_job is None
                and (self.winfo_ismapped()
                     or (self.overlay is not None and self.overlay.winfo_exists()))):
            self.poll_job = self.after(self.POLL_INTERVAL_MS, self._refresh_keys)

    def _stop_polling(self, _event=None):
        if (self.overlay is None or not self.overlay.winfo_exists()) and self.poll_job is not None:
            self.after_cancel(self.poll_job)
            self.poll_job = None

    def _refresh_keys(self):
        self.poll_job = None
        if (not self.winfo_ismapped()
                and (self.overlay is None or not self.overlay.winfo_exists())):
            return
        for key_name, key_code in self.KEY_CODES.items():
            pressed = bool(user32.GetAsyncKeyState(key_code) & 0x8000)
            if pressed == self.key_states[key_name]:
                continue
            self.key_states[key_name] = pressed
            self._update_key_visual(key_name, pressed)
        self.poll_job = self.after(self.POLL_INTERVAL_MS, self._refresh_keys)

    def _update_key_visual(self, key_name, pressed):
        fill = GREEN if pressed else OFF_BG
        foreground = ON_GREEN if pressed else MUTED
        for key_boxes in (self.key_boxes, self.overlay_key_boxes):
            if key_name in key_boxes:
                box, label = key_boxes[key_name]
                box.set_colors(fill=fill, outline=fill if pressed else BORDER)
                label.configure(bg=fill, fg=foreground)

    def close(self):
        self.hide_overlay()
        self._stop_polling()


class MouseVisualizerTab(KeyboardVisualizerTab):
    """Displays the current global state of the left, middle, and right mouse buttons."""

    MODULE_NAME = "Mouse Visualizer"
    DESCRIPTION = ("Visualizes the global pressed state of the left, middle, and right "
                   "mouse buttons.")
    POLL_INTERVAL_MS = 15
    KEY_CODES = {
        "Left": VK_LBUTTON,
        "Middle": VK_MBUTTON,
        "Right": VK_RBUTTON,
    }
    KEY_POSITIONS = {
        "Left": (0, 0),
        "Middle": (0, 1),
        "Right": (0, 2),
    }

    def _create_key_boxes(self, parent):
        canvas = tk.Canvas(parent, width=112, height=123, bg=PANEL,
                           highlightthickness=0, bd=0)
        canvas.pack(anchor="center", pady=4)
        button_radius = min((56 - 9) / 2, (69 - 5) / 2)
        mouse_radius = button_radius

        def arc_points(cx, cy, start, end, radius):
            return [
                (cx + radius * math.cos(math.radians(angle)),
                 cy + radius * math.sin(math.radians(angle)))
                for angle in range(start, end + 1, 15)
            ]

        def mouse_body_points(x1, y1, x2, y2, radius):
            points = [(x1 + radius, y1), (x2 - radius, y1)]
            points.extend(arc_points(x2 - radius, y1 + radius, 270, 360, radius)[1:])
            points.append((x2, y2 - radius))
            points.extend(arc_points(x2 - radius, y2 - radius, 0, 90, radius)[1:])
            points.append((x1 + radius, y2))
            points.extend(arc_points(x1 + radius, y2 - radius, 90, 180, radius)[1:])
            points.append((x1, y1 + radius))
            points.extend(arc_points(x1 + radius, y1 + radius, 180, 270, radius)[1:])
            return [coordinate for point in points for coordinate in point]

        canvas.create_polygon(
            mouse_body_points(7, 3, 105, 120, mouse_radius),
            fill=OFF_BG, outline="")
        canvas.create_polygon(
            rounded_points(9, 5, 103, 69, mouse_radius), smooth=True,
            fill=OFF_BG, outline="")

        def button_points(x1, y1, x2, y2, radius, round_left):
            if round_left:
                points = [(x1 + radius, y1), (x2, y1), (x2, y2),
                          (x1 + radius, y2)]
                points.extend(arc_points(x1 + radius, y2 - radius, 90, 180, radius)[1:])
                points.append((x1, y1 + radius))
                points.extend(arc_points(x1 + radius, y1 + radius, 180, 270, radius)[1:])
            else:
                points = [(x1, y1), (x2 - radius, y1)]
                points.extend(arc_points(x2 - radius, y1 + radius, 270, 360, radius)[1:])
                points.append((x2, y2 - radius))
                points.extend(arc_points(x2 - radius, y2 - radius, 0, 90, radius)[1:])
                points.append((x1, y2))
            return [coordinate for point in points for coordinate in point]

        left_button = canvas.create_polygon(
            button_points(9, 5, 56, 69, button_radius, True),
            fill=OFF_BG, outline=BORDER, width=1)
        right_button = canvas.create_polygon(
            button_points(56, 5, 103, 69, button_radius, False),
            fill=OFF_BG, outline=BORDER, width=1)
        middle_button = canvas.create_polygon(
            rounded_points(51, 20, 61, 43, 5), smooth=True,
            fill=OFF_BG, outline=BORDER, width=1)
        canvas.create_polygon(
            mouse_body_points(7, 3, 105, 120, mouse_radius),
            fill="", outline=BORDER, width=1)
        return {
            "Left": (canvas, left_button),
            "Middle": (canvas, middle_button),
            "Right": (canvas, right_button),
        }

    def _update_key_visual(self, key_name, pressed):
        fill = GREEN if pressed else OFF_BG
        for key_boxes in (self.key_boxes, self.overlay_key_boxes):
            if key_name in key_boxes:
                canvas, button = key_boxes[key_name]
                canvas.itemconfigure(button, fill=fill)


class KeysTab(ModuleFrame):
    """Spams a key at an interval, or holds it down until stopped."""

    GROUP = "Simultaneous"
    MODES = ["Spam", "Hold"]

    def __init__(self, parent, controller):
        self.vk = None
        self.key_label = ""
        self.mode = "Spam"
        self.interval = 0.1
        super().__init__(parent, controller, "Keys",
                         "Spam presses one key repeatedly at the set interval. Hold presses "
                         "the key down and keeps it down until you stop.")

    def build_settings(self):
        self.key_var = self.add_setting("Key", "e")
        self.mode_var = self.add_dropdown("Mode", self.MODES, "Spam")
        self.interval_var = self.add_setting("Seconds between presses (spam only)", "0.1",
                                             rule=self.is_spam)

    def is_spam(self):
        return self.mode_var.get() == "Spam"

    def prepare(self):
        self.vk = parse_key(self.key_var.get())
        if self.vk is None:
            self.note_var.set("Unknown key. Use one letter or number, or: "
                              "Space, Enter, Tab, Esc, Shift, Ctrl, Alt.")
            return False
        self.mode = self.mode_var.get()
        if self.mode == "Spam":
            try:
                seconds = float(self.interval_var.get())
                if seconds < 0.02:
                    raise ValueError
            except ValueError:
                self.note_var.set("Seconds between presses must be a number, at least 0.02.")
                return False
            self.interval = seconds
        self.key_label = key_display(self.key_var.get())
        return True

    def on_begin(self):
        if self.mode == "Hold":
            key_down(self.vk)

    def on_stop(self):
        if self.vk is not None:
            key_up(self.vk)

    def pause_inputs(self):
        if self.mode == "Hold" and self.vk is not None:
            key_up(self.vk)

    def resume_inputs(self):
        if self.mode == "Hold" and self.vk is not None:
            key_down(self.vk)

    def worker(self, sid):
        if self.mode == "Hold":
            self.hold_until_stopped(sid)
            return
        while self.alive(sid):
            if not self.pause_point(sid):
                return
            key_down(self.vk)
            time.sleep(0.02)
            key_up(self.vk)
            if not self.sleep_while_alive(sid, self.interval):
                return


class AutoSprintTab(ModuleFrame):
    """Taps Shift at a configurable interval until stopped."""

    GROUP = "Simultaneous"

    def __init__(self, parent, controller):
        self.interval = 0.1
        super().__init__(parent, controller, "Autosprint",
                         "Taps Shift repeatedly at the configured interval to sprint.")

    def build_settings(self):
        self.interval_var = self.add_setting("Seconds between presses", "0.1")

    def prepare(self):
        try:
            interval = float(self.interval_var.get())
            if not math.isfinite(interval) or interval < 0.02:
                raise ValueError
        except ValueError:
            self.note_var.set("Seconds between presses must be a number, at least 0.02.")
            return False
        self.interval = interval
        return True

    def worker(self, sid):
        shift = SPECIAL_KEYS["shift"]
        press_duration = 0.02
        while self.alive(sid):
            if not self.pause_point(sid):
                return
            key_down(shift)
            time.sleep(press_duration)
            key_up(shift)
            if not self.sleep_while_alive(sid, max(0, self.interval - press_duration)):
                return


class InputBlockerTab(ModuleFrame):
    """Globally blocks selected keyboard keys and mouse buttons until stopped."""

    GROUP = "Simultaneous"
    PAUSABLE = False

    def __init__(self, parent, controller):
        self.rows = []
        self.blocked_keys = set()
        self.blocked_buttons = set()
        self._keyboard_hook = None
        self._mouse_hook = None
        self._keyboard_callback = HOOKPROC(self._keyboard_proc)
        self._mouse_callback = HOOKPROC(self._mouse_proc)
        self._hook_thread_id = 0
        self._hook_lock = threading.Lock()
        self._worker_error = None
        self.app_process_id = ctypes.windll.kernel32.GetCurrentProcessId()
        super().__init__(parent, controller, "Input Blocker",
                         "Blocks selected keys and mouse buttons globally while running, "
                         "except while this toolbox is focused so its controls remain usable. "
                         "Shift+` (~) is always available to stop all tools.")

    def _new_row_frame(self, parent):
        frame = tk.Frame(parent, bg=PANEL)
        return frame

    def build_settings(self):
        self.header = self._new_row_frame(self.settings)
        self.header.pack(fill="x", pady=(2, 2))
        self.header_cells = []
        for col, text in enumerate(("Type", "Key / Button", "")):
            cell = tk.Label(self.header, text=text, font=FONT_SMALL, fg=MUTED,
                            bg=PANEL, anchor="w")
            cell.grid(row=0, column=col, sticky="w", padx=(0, 6))
            self.header_cells.append(cell)
        self.align_columns()

        self.rows_frame = tk.Frame(self.settings, bg=PANEL)

        buttons = tk.Frame(self.settings, bg=PANEL)
        self.input_buttons = buttons
        buttons.pack(fill="x", pady=(8, 2))
        self.track(RoundButton(buttons, text="+  Add Input", font=FONT_SMALL, bg=OFF_BG,
                               fg=TEXT, hover=OFF_HOVER, padx=10, pady=3,
                               command=self.add_input)).pack(side="left")

    def iter_controls(self):
        yield from self._controls
        for row in self.rows:
            yield row["type_combo"], None
            yield row["key_entry"], lambda r=row: r["type"].get() == "Key"
            yield row["button_combo"], lambda r=row: r["type"].get() == "Mouse button"
            yield row["del_btn"], None

    def align_columns(self):
        columns = [[(cell, 6)] for cell in self.header_cells]
        for row in self.rows:
            columns[0].append((row["type_combo"], 6))
            columns[1].append((row["key_entry"], 2))
            columns[1].append((row["button_combo"], 8))
            columns[2].append((row["del_btn"], 0))
        align_grid_columns([self.header] + [row["frame"] for row in self.rows], columns)

    def add_row(self, input_type="Key", value="E"):
        if not self.rows:
            self.rows_frame.pack(fill="x", before=self.input_buttons)
        frame = self._new_row_frame(self.rows_frame)
        frame.pack(fill="x", pady=2)
        type_var = tk.StringVar(value=input_type)
        type_combo = RoundDropdown(frame, type_var, INPUT_BLOCKER_TYPES, width=10)
        type_combo.grid(row=0, column=0, sticky="w", padx=(0, 6), pady=1)

        key_var = tk.StringVar(value=value if input_type == "Key" else "E")
        key_entry = RoundEntry(frame, key_var, width=10)
        if input_type == "Key":
            key_entry.grid(row=0, column=1, sticky="w", padx=(0, 2), pady=1)

        button_var = tk.StringVar(
            value=value if input_type == "Mouse button" and value in BUTTON_FLAGS
            else "Left")
        button_combo = RoundDropdown(frame, button_var, tuple(BUTTON_FLAGS), width=10)
        if input_type == "Mouse button":
            button_combo.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=1)

        def update_input_widget(*_args):
            if type_var.get() == "Key":
                button_combo.grid_remove()
                key_entry.grid(row=0, column=1, sticky="w", padx=(0, 2), pady=1)
            else:
                key_entry.grid_remove()
                button_combo.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=1)
            self.after_idle(self._apply_locks)

        type_var.trace_add("write", update_input_widget)
        del_btn = RoundButton(
            frame, text="\u00d7", font=(FONT_FAMILY, 12, "bold"), bg=OFF_BG, fg=RED,
            hover=OFF_HOVER, padx=0, pady=0, square=True,
            command=lambda: None)
        del_btn.grid(row=0, column=2, sticky="w", pady=1)
        entry = {
            "frame": frame, "type": type_var, "type_combo": type_combo,
            "key": key_var, "key_entry": key_entry,
            "button": button_var, "button_combo": button_combo, "del_btn": del_btn,
        }
        del_btn.rb_command = lambda e=entry: self.remove_input(e)
        self.rows.append(entry)
        self.align_columns()

    def add_input(self):
        if not self.editable():
            return
        if len(self.rows) >= MAX_INPUT_BLOCKS:
            self.note_var.set(f"Input Blocker supports up to {MAX_INPUT_BLOCKS} entries.")
            return
        self.note_var.set("")
        self.add_row()

    def remove_input(self, entry):
        if not self.editable():
            return
        entry["frame"].destroy()
        self.rows.remove(entry)
        if not self.rows:
            self.rows_frame.pack_forget()
        self.align_columns()

    def prepare(self):
        if not self.rows:
            self.note_var.set("Add at least one key or mouse button to block.")
            return False
        keys, buttons = set(), set()
        for index, row in enumerate(self.rows, 1):
            input_type = row["type"].get()
            if input_type == "Key":
                value = row["key"].get().strip()
                vk = parse_key(value)
                if vk is None:
                    self.note_var.set(f"Entry {index}: choose a supported keyboard key.")
                    return False
                if vk == VK_OEM_3:
                    self.note_var.set("The ` / ~ key is reserved for the emergency stop.")
                    return False
                keys.add(vk)
            elif input_type == "Mouse button" and row["button"].get() in BUTTON_FLAGS:
                buttons.add(row["button"].get())
            else:
                self.note_var.set(f"Entry {index}: choose a supported key or mouse button.")
                return False
        self.blocked_keys = keys
        self.blocked_buttons = buttons
        return True

    def _keyboard_proc(self, code, message, data):
        if (code == HC_ACTION and message in KEYBOARD_MESSAGES
                and not self._is_toolbox_foreground()):
            event = ctypes.cast(data, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if event.vkCode in self.blocked_keys and event.vkCode != VK_OEM_3:
                return 1
        return user32.CallNextHookEx(None, code, message, data)

    def _mouse_proc(self, code, message, data):
        if code == HC_ACTION and not self._is_toolbox_foreground():
            for button in self.blocked_buttons:
                if message in MOUSE_MESSAGES[button]:
                    return 1
        return user32.CallNextHookEx(None, code, message, data)

    def _is_toolbox_foreground(self):
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return False
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
        return process_id.value == self.app_process_id

    def on_stop(self):
        with self._hook_lock:
            thread_id = self._hook_thread_id
        if thread_id and not user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0):
            self.note_var.set("Input Blocker could not signal its global hooks to stop.")

    def idle_check(self):
        if self._worker_error:
            error = self._worker_error
            self._worker_error = None
            if self.running:
                self.stop()
            self.note_var.set(f"Input Blocker stopped: {error}")

    def worker(self, sid):
        keyboard_hook = None
        mouse_hook = None
        thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_NOREMOVE)
        with self._hook_lock:
            self._hook_thread_id = thread_id
        try:
            if not self.alive(sid):
                return
            module_handle = ctypes.windll.kernel32.GetModuleHandleW(None)
            keyboard_hook = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._keyboard_callback, module_handle, 0)
            if not keyboard_hook:
                raise RuntimeError("Could not install the global keyboard hook.")
            mouse_hook = user32.SetWindowsHookExW(
                WH_MOUSE_LL, self._mouse_callback, module_handle, 0)
            if not mouse_hook:
                raise RuntimeError("Could not install the global mouse hook.")
            self._keyboard_hook = keyboard_hook
            self._mouse_hook = mouse_hook

            while self.alive(sid):
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise RuntimeError("The global input hook message loop failed.")
                if result == 0:
                    break
        except (RuntimeError, OSError, ctypes.ArgumentError) as error:
            if self.alive(sid):
                self._worker_error = str(error)
        finally:
            if mouse_hook and not user32.UnhookWindowsHookEx(mouse_hook):
                self._worker_error = self._worker_error or (
                    "Could not remove the global mouse hook.")
            if keyboard_hook and not user32.UnhookWindowsHookEx(keyboard_hook):
                self._worker_error = self._worker_error or (
                    "Could not remove the global keyboard hook.")
            self._mouse_hook = None
            self._keyboard_hook = None
            with self._hook_lock:
                self._hook_thread_id = 0


class ClicksTab(ModuleFrame):
    """Spams a mouse button at an interval, or holds it down until stopped."""

    GROUP = "Simultaneous"
    MODES = ["Spam", "Hold"]

    def __init__(self, parent, controller):
        self.button = "Left"
        self.mode = "Spam"
        self.interval = 0.05
        super().__init__(parent, controller, "Clicks",
                         "Spam clicks the left, middle, or right mouse button repeatedly at "
                         "the set interval. Hold presses the button down and keeps it down "
                         "until you stop.")

    def build_settings(self):
        self.button_var = self.add_dropdown("Mouse button", ["Left", "Middle", "Right"],
                                            "Left")
        self.mode_var = self.add_dropdown("Mode", self.MODES, "Spam")
        self.interval_var = self.add_setting("Seconds between clicks (spam only)", "0.05",
                                             rule=self.is_spam)

    def is_spam(self):
        return self.mode_var.get() == "Spam"

    def prepare(self):
        self.button = self.button_var.get()
        self.mode = self.mode_var.get()
        if self.mode == "Spam":
            try:
                seconds = float(self.interval_var.get())
                if seconds < 0.02:
                    raise ValueError
            except ValueError:
                self.note_var.set("Seconds between clicks must be a number, at least 0.02.")
                return False
            self.interval = seconds
        return True

    def on_begin(self):
        if self.mode == "Hold":
            button_down(self.button)

    def on_stop(self):
        if self.mode == "Hold":
            button_up(self.button)

    def pause_inputs(self):
        if self.mode == "Hold":
            button_up(self.button)

    def resume_inputs(self):
        if self.mode == "Hold":
            button_down(self.button)

    def worker(self, sid):
        if self.mode == "Hold":
            self.hold_until_stopped(sid)
            return
        while self.alive(sid):
            if not self.pause_point(sid):
                return
            click_started = time.perf_counter()
            button_click(self.button)
            remaining = max(0, self.interval - (time.perf_counter() - click_started))
            if not self.sleep_while_alive(sid, remaining):
                return


class HotbarAlertTab(ModuleFrame):
    """Shows alerts for watched hotbar slots whose item quantities reach their threshold."""

    GROUP = "Simultaneous"
    SLOT_OPTIONS = tuple(str(slot) for slot in range(1, 10)) + ("0",)

    def __init__(self, parent, controller):
        self.slots = ("9",)
        self.threshold = HOTBAR_DEFAULT_THRESHOLD
        self.slot_indices = (8,)
        self.autoeat_module = None
        self.poll_interval = DEFAULT_SCREEN_POLL_INTERVAL_MS / 1000
        self._worker_error = None
        self._watch_lock = threading.Lock()
        self._alert_positions = {}
        self._screen_status = ""
        self.overlays = {}
        self.overlay_job = None
        super().__init__(parent, controller, "Hotbar Alert",
                         "Watches the selected hotbar slots and shows an exclamation mark on "
                         "each slot when its item quantity is at or below the set threshold.")

    def build_settings(self):
        self.slot_var = self.add_setting("Hotbar slots (comma-separated)", "9")
        self.threshold_var = self.add_setting(
            "Alert at or below quantity", str(HOTBAR_DEFAULT_THRESHOLD))

    def prepare(self):
        if Image is None or ImageGrab is None or ImageFilter is None:
            self.note_var.set("Hotbar Alert needs Pillow for screen capture.")
            return False
        if not OCR_AVAILABLE:
            self.note_var.set("Hotbar Alert needs Windows OCR support.")
            return False
        try:
            self.slots = parse_hotbar_slots(self.slot_var.get(), self.SLOT_OPTIONS)
        except ValueError:
            self.note_var.set(
                "Enter one or more slots from 1 to 9 or 0, separated by commas.")
            return False
        try:
            self.threshold = int(self.threshold_var.get())
            if self.threshold < 1:
                raise ValueError
        except ValueError:
            self.note_var.set("Alert threshold must be a whole number greater than 0.")
            return False
        if self.autoeat_module is None:
            self.note_var.set("Hotbar Alert could not access Autoeat's screen poll interval.")
            return False
        try:
            self.poll_interval = parse_screen_poll_interval(
                self.autoeat_module.poll_var.get())
        except ValueError:
            self.note_var.set("Autoeat's screen poll interval must be a whole number from "
                              f"{MIN_SCREEN_POLL_INTERVAL_MS} to "
                              f"{MAX_SCREEN_POLL_INTERVAL_MS} milliseconds.")
            return False
        self.slot_indices = tuple(self.SLOT_OPTIONS.index(slot) for slot in self.slots)
        return True

    def on_begin(self):
        self._worker_error = None
        with self._watch_lock:
            self._alert_positions = {}
            self._screen_status = "Searching for the health bar and hotbar..."
        self.overlays = {}
        for slot in self.slots:
            overlay = tk.Toplevel(self)
            overlay.wm_overrideredirect(True)
            overlay.wm_attributes("-topmost", True)
            overlay.configure(bg=OVERLAY_TRANSPARENT)
            overlay.wm_attributes("-transparentcolor", OVERLAY_TRANSPARENT)
            marker_size = 22
            marker = tk.Canvas(overlay, width=marker_size, height=marker_size,
                               bg=OVERLAY_TRANSPARENT, highlightthickness=0, bd=0)
            marker.pack()
            marker.create_rectangle(0, 0, marker_size - 1, marker_size - 1,
                                    fill=RED, outline=RED)
            marker.create_text(marker_size / 2, marker_size / 2, text="!",
                               fill="#ffffff", font=(FONT_FAMILY, 12, "bold"))
            try:
                make_window_clickthrough(overlay, OVERLAY_TRANSPARENT)
            except OSError as error:
                overlay.destroy()
                for created_overlay in self.overlays.values():
                    created_overlay.destroy()
                self.overlays.clear()
                self._worker_error = (
                    f"Hotbar Alert could not create the slot {slot} warning: {error}")
                return
            overlay.withdraw()
            self.overlays[slot] = overlay
        self.overlay_job = self.after(
            max(1, round(self.poll_interval * 1000)), self.refresh_overlay)

    def on_stop(self):
        if self.overlay_job is not None:
            self.after_cancel(self.overlay_job)
            self.overlay_job = None
        for overlay in self.overlays.values():
            if overlay.winfo_exists():
                overlay.destroy()
        self.overlays.clear()
        with self._watch_lock:
            self._alert_positions = {}

    def idle_check(self):
        if self._worker_error is not None:
            message = self._worker_error
            self._worker_error = None
            if self.running:
                self.stop()
            self.note_var.set(message)

    def refresh_overlay(self):
        self.overlay_job = None
        if not self.overlays or not self.running:
            return
        with self._watch_lock:
            positions = self._alert_positions.copy()
            status = self._screen_status
        if status != self.note_var.get():
            self.note_var.set(status)
        for slot, overlay in self.overlays.items():
            if not overlay.winfo_exists():
                continue
            position = positions.get(slot)
            if position is None:
                overlay.withdraw()
            else:
                left, top = position
                if overlay.state() == "withdrawn":
                    overlay.geometry(f"22x22+{left}+{top}")
                    overlay.deiconify()
                elif overlay.winfo_x() != left or overlay.winfo_y() != top:
                    overlay.geometry(f"22x22+{left}+{top}")
        self.overlay_job = self.after(
            max(1, round(self.poll_interval * 1000)), self.refresh_overlay)

    async def watch(self, sid):
        engine = get_ocr_engine()
        tracked = None
        locked_geometry = None
        last_known_quantities = {slot: None for slot in self.slots}
        unreadable_item_reads = {slot: 0 for slot in self.slots}
        above_threshold_reads = {slot: 0 for slot in self.slots}
        alert_visible = {slot: False for slot in self.slots}
        read_error_visible = False
        read_error_reads = 0
        read_success_reads = 0
        while self.alive(sid):
            poll_started = time.perf_counter()
            with self._watch_lock:
                positions = self._alert_positions.copy()
            status = "Health bar not detected. Keep the game and health bar visible."
            if locked_geometry is None:
                reading = None
                if tracked is not None:
                    screenshot, origin = grab_screen(tracked)
                    reading = await read_auto_eat_hud(screenshot, engine, origin)
                if reading is None:
                    screenshot, origin = grab_screen()
                    reading = await read_auto_eat_hud(screenshot, engine, origin)
                if not self.alive(sid):
                    return
                if reading is not None:
                    _, _, health_bar, text_box = reading
                    tracked = tracking_box(
                        [text_box, health_bar], text_box[3] - text_box[1])
                    slot_centers = [
                        hotbar_slot_center(slot_index, health_bar)
                        for slot_index in range(HOTBAR_SLOT_COUNT)
                    ]
                    expected_slot_size = slot_centers[0][2]
                    expected_top = slot_centers[0][1] - expected_slot_size / 2
                    expected_step = slot_centers[1][0] - slot_centers[0][0]
                    frame = screen_grab()
                    grid = find_hotbar_grid_near(
                        frame, expected_top, expected_step, expected_slot_size,
                        health_bar[3])
                    if grid is not None:
                        grid_left, grid_top, slot_pitch = grid
                        screen_width, screen_height = frame.size
                        slot_bounds = [
                            (grid_left + index * slot_pitch, grid_top,
                             grid_left + (index + 1) * slot_pitch,
                             grid_top + slot_pitch)
                            for index in range(HOTBAR_SLOT_COUNT)
                        ]
                        hotbar_box = (
                            max(0, grid_left - 2),
                            max(0, grid_top - 2),
                            min(screen_width, grid_left + HOTBAR_SLOT_COUNT * slot_pitch + 2),
                            min(screen_height, grid_top + slot_pitch + 2),
                        )
                        locked_geometry = (
                            slot_bounds, hotbar_box, slot_pitch,
                            slot_bounds[0][0] - hotbar_box[0],
                        )
                    else:
                        status = "Hotbar slots not detected. Keep the hotbar visible."
                else:
                    tracked = None
            if locked_geometry is not None:
                slot_bounds, hotbar_box, slot_pitch, first_slot_left = locked_geometry
                positions = {}
                row_image = screen_grab(hotbar_box)
                quantities = await read_hotbar_quantities_from_row(
                    row_image, engine, first_slot_left, slot_pitch, self.slot_indices)
                unreadable_slots = False
                for slot, slot_index in zip(self.slots, self.slot_indices):
                    slot_left, slot_top, slot_right, slot_bottom = slot_bounds[slot_index]
                    slot_box = (
                        max(0, slot_left - 2),
                        max(0, slot_top - 2),
                        min(screen_width, slot_right + 2),
                        min(screen_height, slot_bottom + 2),
                    )
                    slot_image = row_image.crop((
                        slot_box[0] - hotbar_box[0],
                        slot_box[1] - hotbar_box[1],
                        slot_box[2] - hotbar_box[0],
                        slot_box[3] - hotbar_box[1],
                    ))
                    quantity = quantities.get(slot_index)
                    has_item = False
                    if quantity is None:
                        has_item = hotbar_slot_has_item(slot_image)
                        if has_item:
                            quantity = await read_hotbar_quantity(slot_image, engine)
                    if quantity is None:
                        if has_item:
                            unreadable_item_reads[slot] += 1
                            if (unreadable_item_reads[slot]
                                    >= HOTBAR_ALERT_INFERRED_ITEM_READS
                                    and (last_known_quantities[slot] is None
                                         or last_known_quantities[slot] <= self.threshold)):
                                quantity = 1
                            else:
                                unreadable_slots = True
                        else:
                            quantity = 0
                            unreadable_item_reads[slot] = 0
                    if not self.alive(sid):
                        return
                    if quantity is not None:
                        last_known_quantities[slot] = quantity
                        unreadable_item_reads[slot] = 0
                        if quantity <= self.threshold:
                            alert_visible[slot] = True
                            above_threshold_reads[slot] = 0
                        elif alert_visible[slot]:
                            above_threshold_reads[slot] += 1
                            if above_threshold_reads[slot] >= HOTBAR_ALERT_CLEAR_READS:
                                alert_visible[slot] = False
                                above_threshold_reads[slot] = 0
                        else:
                            above_threshold_reads[slot] = 0
                    if alert_visible[slot]:
                        positions[slot] = (slot_left + 4, slot_top + 2)
                status = ""
                if unreadable_slots:
                    read_error_reads += 1
                    read_success_reads = 0
                    if read_error_reads >= HOTBAR_ALERT_STATUS_CONFIRM_READS:
                        read_error_visible = True
                else:
                    read_success_reads += 1
                    read_error_reads = 0
                    if read_success_reads >= HOTBAR_ALERT_CLEAR_READS:
                        read_error_visible = False
                if read_error_visible:
                    status = "Could not read one or more selected slot quantities."
            with self._watch_lock:
                self._alert_positions = positions
                self._screen_status = status
            await asyncio.sleep(max(
                0, self.poll_interval - (time.perf_counter() - poll_started)))

    def worker(self, sid):
        try:
            asyncio.run(self.watch(sid))
        except Exception as error:
            if self.alive(sid):
                detail = str(error) or type(error).__name__
                self._worker_error = f"Hotbar Alert stopped: {detail}"


class SpinTab(ModuleFrame):
    """Continuously turns the camera horizontally until stopped."""

    GROUP = "Simultaneous"

    def __init__(self, parent, controller):
        self.direction = "Clockwise (mouse right)"
        self.speed = 5000.0
        super().__init__(parent, controller, "Spin",
                         "Continuously moves the mouse horizontally to rotate the camera. "
                         "Choose a direction and speed. Speed is capped by in-game mouse sensitivity.")

    def build_settings(self):
        self.direction_var = self.add_dropdown(
            "Direction", ["Clockwise (mouse right)", "Counterclockwise (mouse left)"],
            self.direction)
        self.speed_var = self.add_setting("Speed (mouse pixels per second)", "5000")

    def prepare(self):
        direction = self.direction_var.get()
        if direction not in ("Clockwise (mouse right)", "Counterclockwise (mouse left)"):
            self.note_var.set("Choose clockwise or counterclockwise rotation.")
            return False
        try:
            speed = float(self.speed_var.get())
            if not math.isfinite(speed) or not 1 <= speed <= SPIN_MAX_SPEED:
                raise ValueError
        except ValueError:
            self.note_var.set(f"Spin speed must be a number from 1 to {SPIN_MAX_SPEED} "
                              "mouse pixels per second.")
            return False
        self.direction = direction
        self.speed = speed
        return True

    def worker(self, sid):
        direction = 1 if self.direction == "Clockwise (mouse right)" else -1
        pending = 0.0
        last = time.perf_counter()
        while self.alive(sid):
            if self.paused_now():
                if not self.pause_point(sid):
                    return
                pending = 0.0
                last = time.perf_counter()
                continue
            now = time.perf_counter()
            pending += self.speed * (now - last)
            last = now
            pixels = int(pending)
            if pixels:
                pending -= pixels
                move_rel(direction * pixels, 0)
            else:
                delay = MOUSE_STREAM_TICK - (time.perf_counter() - now)
                if delay > 0 and not self.sleep_while_alive(sid, delay):
                    return


class AutoeatTab(ModuleFrame):
    """Watches health and eats from a chosen hotbar slot until health exceeds a threshold."""

    GROUP = "Simultaneous"
    PAUSABLE = False

    def __init__(self, parent, controller):
        self.slot = "0"
        self.threshold = 35
        self.pause_others = True
        self.poll_interval = DEFAULT_SCREEN_POLL_INTERVAL_MS / 1000
        self._eating = False
        self._worker_error = None
        super().__init__(parent, controller, "Autoeat",
                         "Watches your healthbar and switches to the chosen slot when your "
                         "health dips below a chosen threshold, eating until health is over "
                         "the threshold. Other running tools pause while it eats, unless the "
                         "pause option is set to No.")

    def build_settings(self):
        self.slot_var = self.add_dropdown("Hotbar slot", AUTOEAT_SLOT_ORDER, "0")
        self.threshold_var = self.add_setting("Health threshold (eat at or below)", "35")
        self.poll_var = self.add_setting(
            "Screen poll interval (ms)", str(DEFAULT_SCREEN_POLL_INTERVAL_MS))
        self.pause_var = self.add_dropdown(
            "Pause other tools while eating", ("Yes", "No"), "Yes")

    def prepare(self):
        if Image is None or ImageGrab is None:
            self.note_var.set("Autoeat needs Pillow for screen capture. Run: pip install pillow")
            return False
        if not OCR_AVAILABLE:
            self.note_var.set("Autoeat needs Windows OCR support.")
            return False
        slot = self.slot_var.get()
        if slot not in AUTOEAT_SLOT_ORDER:
            self.note_var.set("Choose a hotbar slot from 1 to 9 or 0.")
            return False
        try:
            threshold = int(self.threshold_var.get())
            if threshold < 0:
                raise ValueError
        except ValueError:
            self.note_var.set("Health threshold must be a whole number, 0 or greater.")
            return False
        try:
            poll_interval = parse_screen_poll_interval(self.poll_var.get())
        except ValueError:
            self.note_var.set("Screen poll interval must be a whole number from "
                              f"{MIN_SCREEN_POLL_INTERVAL_MS} to "
                              f"{MAX_SCREEN_POLL_INTERVAL_MS} milliseconds.")
            return False
        pause_choice = self.pause_var.get()
        if pause_choice not in ("No", "Yes"):
            self.note_var.set("Choose Yes or No for pausing other tools while eating.")
            return False
        self.slot = slot
        self.slot_vk = parse_key(slot)
        self.threshold = threshold
        self.poll_interval = poll_interval
        self.pause_others = pause_choice == "Yes"
        return True

    def on_begin(self):
        self._eating = False
        self._worker_error = None

    def on_stop(self):
        if self._eating:
            button_up("Right")
            self._eating = False
        self._resume_others()

    def _pause_others(self):
        if self.pause_others:
            self.controller.others_paused.set()

    def _resume_others(self):
        self.controller.others_paused.clear()

    def idle_check(self):
        if self._worker_error is not None:
            message = self._worker_error
            self._worker_error = None
            if self.running:
                self.stop()
            self.note_var.set(message)

    async def watch(self, sid):
        engine = get_ocr_engine()

        checked_slot = False
        tracked = None
        while self.alive(sid):
            poll_started = time.perf_counter()
            reading = None
            if tracked is not None:
                shot, origin = grab_screen(tracked)
                reading = await read_auto_eat_hud(shot, engine, origin)
            if reading is None:
                shot, origin = grab_screen()
                reading = await read_auto_eat_hud(shot, engine, origin)
            if not self.alive(sid):
                return
            if reading is None:
                tracked = None
            else:
                health, max_health, health_bar, text_box = reading
                tracked = tracking_box([text_box, health_bar], text_box[3] - text_box[1])
                if not checked_slot:
                    if auto_eat_slot_is_empty(self.slot, health_bar):
                        raise RuntimeError(f"hotbar slot {self.slot} is empty.")
                    checked_slot = True
                if self._eating and auto_eat_slot_is_empty(self.slot, health_bar):
                    raise RuntimeError(f"hotbar slot {self.slot} became empty.")
                if health < max_health and health <= self.threshold and not self._eating:
                    self._pause_others()
                    tap_key(self.slot_vk)
                    await asyncio.sleep(AUTOEAT_SLOT_SETTLE_SECONDS)
                    if not self.alive(sid):
                        return
                    if auto_eat_slot_is_empty(self.slot, health_bar):
                        raise RuntimeError(f"hotbar slot {self.slot} is empty.")
                    button_down("Right")
                    self._eating = True
                elif (health >= max_health or health > self.threshold) and self._eating:
                    button_up("Right")
                    self._eating = False
                    self._resume_others()
            await asyncio.sleep(max(
                0, self.poll_interval - (time.perf_counter() - poll_started)))

    def worker(self, sid):
        try:
            asyncio.run(self.watch(sid))
        except Exception as error:
            if self.alive(sid):
                detail = str(error) or type(error).__name__
                self._worker_error = f"Autoeat stopped: {detail}"
        finally:
            if self._eating:
                button_up("Right")
                self._eating = False
            self._resume_others()


class PatternTab(ModuleFrame):
    """A custom loop of key presses, mouse clicks, pauses, and camera turns."""

    GROUP = "Independent"

    def __init__(self, parent, controller):
        self.rows = []
        self.steps = []
        self.total = 0.0
        self.held = set()
        super().__init__(parent, controller, "Pattern",
                         "Build a loop of key presses, mouse clicks, pauses, and camera "
                         "turns. Each step waits its seconds before the next one. Key Down "
                         "holds a key until a Key Up step or Stop.")

    def _new_row_frame(self, parent):
        """Creates a row; align_columns synchronizes it with the shared header."""
        return tk.Frame(parent, bg=PANEL)

    def build_settings(self):
        self.header = self._new_row_frame(self.settings)
        self.header.pack(fill="x", pady=(2, 2))
        self.header_cells = []
        for col, text in enumerate(("Action", "Key", "Click", "Wait (s)", "")):
            cell = tk.Label(self.header, text=text, font=FONT_SMALL, fg=MUTED,
                            bg=PANEL, anchor="w")
            cell.grid(row=0, column=col, sticky="w", padx=(0, 5))
            self.header_cells.append(cell)
        self.align_columns()

        self.rows_frame = tk.Frame(self.settings, bg=PANEL)

        btns = tk.Frame(self.settings, bg=PANEL)
        self.step_buttons = btns
        btns.pack(fill="x", pady=(8, 2))
        self.track(RoundButton(btns, text="+  Add Step", font=FONT_SMALL, bg=OFF_BG,
                               fg=TEXT, hover=OFF_HOVER, padx=10, pady=3,
                               command=self.add_step)).pack(side="left")
        self.reset_steps()

    def iter_controls(self):
        yield from self._controls
        for row in self.rows:
            yield row["combo"], None
            yield row["key_entry"], (lambda r=row: r["action"].get() in KEY_ACTIONS)
            yield row["direction_combo"], (
                lambda r=row: r["action"].get() == ACT_CAMERA)
            yield row["click_combo"], None
            yield row["secs_entry"], None
            yield row["pixels_entry"], (
                lambda r=row: r["action"].get() == ACT_CAMERA)
            yield row["del_btn"], None

    def align_columns(self):
        columns = [[(cell, 5)] for cell in self.header_cells]
        for row in self.rows:
            columns[0].append((row["combo"], 5))
            columns[1].append((row["key_entry"], 5))
            columns[2].append((row["click_combo"], 5))
            columns[3].append((row["secs_entry"], 5))
            columns[4].append((row["del_btn"], 0))
        align_grid_columns([self.header] + [row["frame"] for row in self.rows], columns)

    def add_row(self, action, key, seconds, click="None",
                direction=PATTERN_CAMERA_DIRECTIONS[0],
                pixels=PATTERN_CAMERA_DEFAULT_PIXELS):
        if not self.rows:
            self.rows_frame.pack(fill="x", before=self.step_buttons)
        row_frame = self._new_row_frame(self.rows_frame)
        row_frame.pack(fill="x", pady=2)
        action_var = tk.StringVar(value=action)
        combo = RoundDropdown(row_frame, action_var, PATTERN_ACTIONS, width=12)
        combo.grid(row=0, column=0, sticky="w", padx=(0, 5), pady=1)
        key_var = tk.StringVar(value=key)
        key_entry = RoundEntry(row_frame, key_var, width=7)
        key_entry.grid(row=0, column=1, sticky="w", padx=(0, 5), pady=1)
        camera_frame = tk.Frame(row_frame, bg=PANEL)
        direction_var = tk.StringVar(value=direction)
        direction_combo = RoundDropdown(
            camera_frame, direction_var, PATTERN_CAMERA_DIRECTIONS, width=16)
        pixels_var = tk.StringVar(value=str(pixels))
        pixels_entry = RoundEntry(camera_frame, pixels_var, width=7)
        tk.Label(camera_frame, text="Direction", font=FONT_SMALL,
                 fg=MUTED, bg=PANEL).pack(side="left", padx=(0, 5))
        direction_combo.pack(side="left", padx=(0, 12))
        tk.Label(camera_frame, text="Mouse pixels", font=FONT_SMALL,
                 fg=MUTED, bg=PANEL).pack(side="left", padx=(0, 5))
        pixels_entry.pack(side="left")
        click_var = tk.StringVar(value=click)
        click_combo = RoundDropdown(row_frame, click_var, PATTERN_CLICK_OPTIONS, width=8)
        click_combo.grid(row=0, column=2, sticky="w", padx=(0, 5), pady=1)
        secs_var = tk.StringVar(value=str(seconds))
        secs_entry = RoundEntry(row_frame, secs_var, width=7)
        secs_entry.grid(row=0, column=3, sticky="w", padx=(0, 5), pady=1)
        del_btn = RoundButton(row_frame, text="\u00d7",
                              font=(FONT_FAMILY, 12, "bold"), bg=OFF_BG, fg=RED,
                              hover=OFF_HOVER, padx=0, pady=0, square=True,
                              command=lambda e=None: None)
        del_btn.grid(row=0, column=4, sticky="w", pady=1)
        entry = {"frame": row_frame, "action": action_var, "combo": combo,
                 "key_var": key_var, "key_entry": key_entry,
                 "direction_var": direction_var, "direction_combo": direction_combo,
                 "camera_frame": camera_frame,
                 "click_var": click_var, "click_combo": click_combo,
                 "pixels_var": pixels_var, "pixels_entry": pixels_entry,
                 "secs_var": secs_var, "secs_entry": secs_entry, "del_btn": del_btn}
        del_btn.rb_command = lambda e=entry: self.remove_step(e)
        self.rows.append(entry)
        action_var.trace_add(
            "write", lambda *_args, row=entry: self.update_row_fields(row))
        self.update_row_fields(entry)
        self.align_columns()

    def update_row_fields(self, row):
        action = row["action"].get()
        if action in KEY_ACTIONS:
            row["key_entry"].grid()
        elif row["key_entry"].winfo_manager():
            row["key_entry"].grid_remove()
        if action == ACT_CAMERA:
            row["camera_frame"].grid(
                row=1, column=0, columnspan=5, sticky="w", pady=(2, 0))
        elif row["camera_frame"].winfo_manager():
            row["camera_frame"].grid_remove()

    def add_step(self):
        if not self.editable():
            return
        if len(self.rows) >= MAX_PATTERN_STEPS:
            self.note_var.set(f"A pattern can have up to {MAX_PATTERN_STEPS} steps.")
            return
        self.note_var.set("")
        self.add_row(ACT_TAP, "e", 0.1)

    def remove_step(self, entry):
        if not self.editable():
            return
        entry["frame"].destroy()
        self.rows.remove(entry)
        if not self.rows:
            self.rows_frame.pack_forget()
        self.align_columns()

    def reset_steps(self):
        if not self.editable():
            return
        for entry in self.rows:
            entry["frame"].destroy()
        self.rows.clear()
        self.rows_frame.pack_forget()
        self.note_var.set("")
        for action, key, seconds in DEFAULT_PATTERN:
            self.add_row(action, key, seconds)

    def prepare(self):
        steps = []
        for i, row in enumerate(self.rows, 1):
            action = row["action"].get()
            click = row["click_var"].get()
            if click not in PATTERN_CLICK_OPTIONS:
                self.note_var.set(
                    f"Step {i}: choose None, Left, Middle, or Right for Click.")
                return False
            if action not in PATTERN_ACTIONS:
                self.note_var.set(f"Step {i}: choose a valid action.")
                return False
            try:
                seconds = float(row["secs_var"].get())
                if not math.isfinite(seconds) or seconds < 0:
                    raise ValueError
            except ValueError:
                self.note_var.set(
                    f"Step {i}: wait time must be a number, 0 or more.")
                return False
            vk, label = None, ""
            if action in KEY_ACTIONS:
                label = row["key_var"].get().strip()
                vk = parse_key(label)
                if vk is None:
                    self.note_var.set(f"Step {i}: unknown key '{label}'. Use one letter "
                                      "or number, or: Space, Enter, Tab, Esc, Shift, "
                                      "Ctrl, Alt.")
                    return False
            direction = row["direction_var"].get()
            pixels = 0
            if action == ACT_CAMERA:
                if direction not in PATTERN_CAMERA_DIRECTIONS:
                    self.note_var.set(f"Step {i}: choose a valid camera direction.")
                    return False
                try:
                    pixels = parse_pattern_camera_pixels(row["pixels_var"].get())
                except ValueError:
                    self.note_var.set(
                        f"Step {i}: camera pixels must be a whole number from 1 to "
                        f"{PATTERN_CAMERA_MAX_PIXELS}.")
                    return False
            steps.append((action, vk, label, click, seconds, direction, pixels))
        if not steps:
            self.note_var.set("Add at least one step.")
            return False
        total = sum(s[4] for s in steps)
        if total < 0.05:
            self.note_var.set("Total wait must be at least 0.05 seconds, or the loop "
                              "runs too fast.")
            return False
        self.steps = steps
        self.total = total
        return True

    def on_begin(self):
        self.held = set()

    def on_stop(self):
        for vk in list(self.held):
            key_up(vk)
        self.held.clear()

    def pause_inputs(self):
        for vk in list(self.held):
            key_up(vk)

    def resume_inputs(self):
        for vk in list(self.held):
            key_down(vk)

    def run_step(self, sid, action, vk, click, seconds, direction, pixels):
        if not self.pause_point(sid):
            return False
        if action == ACT_TAP:
            key_down(vk)
            time.sleep(TAP_SECONDS)
            key_up(vk)
        elif action == ACT_DOWN:
            if vk not in self.held:
                self.held.add(vk)
                key_down(vk)
        elif action == ACT_UP:
            if vk in self.held:
                self.held.discard(vk)
                key_up(vk)
        elif action == ACT_LEFT:
            button_click("Left")
        elif action == ACT_MIDDLE:
            button_click("Middle")
        elif action == ACT_RIGHT:
            button_click("Right")
        elif action == ACT_CAMERA:
            direction_sign = 1 if direction == "Clockwise" else -1
            move_rel(direction_sign * pixels, 0)
        elif action == ACT_PAUSE:
            pass
        if click != "None":
            if not self.pause_point(sid):
                return False
            button_click(click)
        return self.sleep_while_alive(sid, seconds)

    def worker(self, sid):
        while self.alive(sid):
            for action, vk, _label, click, seconds, direction, pixels in self.steps:
                if not self.run_step(
                        sid, action, vk, click, seconds, direction, pixels):
                    return


class CenterBase(ModuleFrame):
    """Shared screen detection and adjustment logic for Run Once tools."""

    GROUP = "Run Once"
    INCLUDABLE = False

    def __init__(self, parent, controller, module_name, description):
        self.look_seconds = 5.0
        self.hold_vk = None
        self.hold_label = "C"
        self.align_tolerance = 0.2
        self.tolerance_x = 12
        self.tolerance_y = 3
        self.max_tap = 0.25
        self.pause_seconds = 0.3
        self.max_taps = 150
        self.white_threshold = 200
        self.message = ""
        self.phase = "Starting"
        self.done_sid = None
        self.holding_key = False
        self.near = None
        self.size_ref = None
        self.axis_gain = {"x": None, "y": None}
        super().__init__(parent, controller, module_name, description)

    def _build_status(self):
        self.result_var = tk.StringVar(value="")
        self.result_label = tk.Label(self.settings, textvariable=self.result_var,
                                     font=FONT_BODY, fg=GREEN, bg=PANEL, wraplength=420,
                                     justify="left")
        self._result_shown = False
        self.result_var.trace_add("write", lambda *_: self._sync_result())

    def _sync_result(self):
        want = bool(self.result_var.get())
        if want and not self._result_shown:
            self.result_label.pack(anchor="w", pady=(6, 0))
            self._result_shown = True
        elif not want and self._result_shown:
            self.result_label.pack_forget()
            self._result_shown = False

    def cross_px(self):
        """Calculates the screen center in pixels for the current display dimensions."""
        sw, sh = screen_size()
        return sw / 2, sh / 2

    def on_stop(self):
        if self.holding_key and self.hold_vk is not None:
            key_up(self.hold_vk)
            self.holding_key = False

    def read(self, sid):
        """Takes several screenshots and returns the median position and tilt of the square,
        measured from the crosshair. Returns None if the square wasn't found, or the run stopped."""
        cross = self.cross_px()
        xs, ys, ts = [], [], []
        ref = None
        for i in range(READ_SAMPLES):
            if not self.alive(sid):
                return None
            boxes = detect_squares(self.white_threshold, cross)
            target = pick_square(boxes, self.near, cross, self.size_ref) if boxes else None
            if target is not None:
                if self.size_ref is None:
                    self.size_ref = box_size(target)
                cx, cy = box_center(target)
                t = box_tilt(target)
                if ref is None:
                    ref = t
                xs.append(cx)
                ys.append(cy)
                ts.append(ref + wrap45(t - ref))
                self.near = (cx, cy)
            if i < READ_SAMPLES - 1 and not self.sleep_while_alive(sid, READ_SAMPLE_GAP):
                return None
        if not xs:
            return None
        return {"dx": statistics.median(xs) - cross[0],
                "dy": statistics.median(ys) - cross[1],
                "tilt": wrap45(statistics.median(ts)),
                "n": len(xs)}

    def read_or_retry(self, sid):
        """Reads the square, retrying a few times if it's briefly missing."""
        for attempt in range(MAX_MISSES):
            if not self.alive(sid):
                return None
            r = self.read(sid)
            if r is not None:
                return r
            if attempt >= 2:
                self.near = None
            if not self.sleep_while_alive(sid, MISS_RETRY_SECONDS):
                return None
        self.message = ("Couldn't find the square. Make sure it's visible near the center "
                        "of the screen.")
        return None

    def look_down(self, sid):
        """Moves the mouse straight down for the set time. The mouse button is not held."""
        rate = LOOK_PIXELS_PER_TICK / LOOK_TICK
        pixels = int(round(rate * self.look_seconds))
        return stream_mouse(0, pixels, rate, lambda: self.alive(sid))

    def move_mouse_x(self, sid, px):
        """Moves the mouse left (negative) or right (positive) one pixel at a time, so the
        game sees smooth motion. Returns False if the run was stopped."""
        rate = LOOK_PIXELS_PER_TICK / LOOK_TICK
        return stream_mouse(px, 0, rate, lambda: self.alive(sid))

    def align_tilt(self, sid):
        """Moves the mouse left or right until the square is upright.

        Probe movement estimates the game's rotation response. Each correction then uses
        the observed response to keep refining that estimate.
        """
        r0 = self.read_or_retry(sid)
        if r0 is None:
            return False
        if abs(r0["tilt"]) <= self.align_tolerance:
            return True

        gain = None
        for probe in (ALIGN_PROBE_PX, ALIGN_PROBE_PX * 2, ALIGN_PROBE_PX * 3):
            if not self.move_mouse_x(sid, probe):
                return False
            if not self.sleep_while_alive(sid, LOOK_SETTLE_SECONDS):
                return False
            r1 = self.read_or_retry(sid)
            if r1 is None:
                return False
            change = wrap45(r1["tilt"] - r0["tilt"])
            if abs(change) >= ALIGN_MIN_CHANGE:
                gain = change / probe
                r0 = r1
                break
            if not self.move_mouse_x(sid, -probe):
                return False
            if not self.sleep_while_alive(sid, LOOK_SETTLE_SECONDS):
                return False
            r0 = self.read_or_retry(sid)
            if r0 is None:
                return False

        if gain is None:
            self.message = ("Mouse movement didn't rotate the square enough to measure "
                            "its response, so Align stopped.")
            return False

        stable = 0
        previous_tilt = r0["tilt"]
        previous_move = 0
        steps = 0
        while self.alive(sid):
            if steps >= ALIGN_MAX_STEPS:
                self.message = (f"Couldn't line the square up after {ALIGN_MAX_STEPS} "
                                f"moves. Last tilt: {previous_tilt:+.2f} degrees.")
                return False
            r = self.read_or_retry(sid)
            if r is None:
                return False
            t = r["tilt"]
            self.phase = f"Lining up the square ({t:+.2f} degrees off)"

            if abs(t) <= self.align_tolerance:
                stable += 1
                if stable >= STABLE_READS:
                    return True
                if not self.sleep_while_alive(sid, 0.1):
                    return False
                continue
            stable = 0

            if previous_move:
                change = wrap45(t - previous_tilt)
                if abs(change) >= ALIGN_MIN_CHANGE:
                    measured_gain = change / previous_move
                    if measured_gain * gain <= 0:
                        gain = measured_gain
                    else:
                        gain = 0.5 * gain + 0.5 * measured_gain

            move = -t / gain * ALIGN_SAFETY
            if abs(move) < ALIGN_MIN_PX:
                move = ALIGN_MIN_PX if move > 0 else -ALIGN_MIN_PX
            move = max(-ALIGN_MAX_PX, min(ALIGN_MAX_PX, move))
            move = int(round(move))
            previous_tilt = t
            previous_move = move
            steps += 1
            if not self.move_mouse_x(sid, move):
                return False
            if not self.sleep_while_alive(sid, LOOK_SETTLE_SECONDS):
                return False
        return False

    def tap(self, sid, vk, duration):
        """Holds a key for a short time, then waits so the screen can settle."""
        key_down(vk)
        if duration < 0.05:
            time.sleep(duration)
            alive = self.alive(sid)
        else:
            alive = self.sleep_while_alive(sid, duration)
        key_up(vk)
        return alive and self.sleep_while_alive(sid, self.pause_seconds)

    def calibrate_axis(self, sid, axis):
        """Taps the positive key and measures its full screen-space movement vector."""
        key = HORIZ_POS_KEY if axis == "x" else VERT_POS_KEY
        name = "D" if axis == "x" else "S"
        for tap_len in (CAL_TAP_SECONDS, CAL_TAP_SECONDS * 2):
            r0 = self.read_or_retry(sid)
            if r0 is None:
                return False
            if not self.tap(sid, key, tap_len):
                return False
            r1 = self.read_or_retry(sid)
            if r1 is None:
                return False
            change_x = r1["dx"] - r0["dx"]
            change_y = r1["dy"] - r0["dy"]
            if math.hypot(change_x, change_y) >= CHANGE_MIN_PX:
                self.axis_gain[axis] = (change_x / tap_len, change_y / tap_len)
                return True
        self.message = (f"Pressing {name} didn't move the square enough to calibrate "
                        f"the {axis} direction, so Center stopped.")
        return False

    def center_position(self, sid):
        """Uses measured key movement vectors to correct the square's screen position."""
        stable = 0
        taps = 0
        while self.alive(sid):
            if taps >= self.max_taps:
                self.message = f"Gave up after {self.max_taps} taps."
                return
            r = self.read_or_retry(sid)
            if r is None:
                return
            dx, dy = r["dx"], r["dy"]
            self.phase = f"Centering ({dx:+.0f}px across, {dy:+.0f}px down)"

            in_x = abs(dx) <= self.tolerance_x
            in_y = abs(dy) <= self.tolerance_y
            if in_x and in_y:
                stable += 1
                if stable >= STABLE_READS:
                    self.message = f"Centered after {taps} taps."
                    return
                if not self.sleep_while_alive(sid, 0.1):
                    return
                continue
            stable = 0

            for axis in ("x", "y"):
                if self.axis_gain[axis] is None:
                    if not self.calibrate_axis(sid, axis):
                        return
                    break
            else:
                best = None
                distance_sq = dx * dx + dy * dy
                for axis, pos_key, neg_key in (
                        ("x", HORIZ_POS_KEY, HORIZ_NEG_KEY),
                        ("y", VERT_POS_KEY, VERT_NEG_KEY)):
                    gain_x, gain_y = self.axis_gain[axis]
                    speed_sq = gain_x * gain_x + gain_y * gain_y
                    if speed_sq == 0:
                        continue
                    projected_seconds = -(dx * gain_x + dy * gain_y) / speed_sq
                    if projected_seconds == 0:
                        continue
                    duration = min(self.max_tap,
                                   max(POS_MIN_TAP, abs(projected_seconds) * POS_SAFETY))
                    signed_duration = duration if projected_seconds > 0 else -duration
                    next_x = dx + gain_x * signed_duration
                    next_y = dy + gain_y * signed_duration
                    improvement = distance_sq - (next_x * next_x + next_y * next_y)
                    if best is None or improvement > best[0]:
                        key = pos_key if signed_duration > 0 else neg_key
                        best = (improvement, axis, key, duration, signed_duration)

                if best is None or best[0] <= 0:
                    self.message = ("The movement keys can't move the square closer to the "
                                    "screen center, so Center stopped.")
                    return
                axis, key, duration, signed_duration = best[1:]

                if not self.tap(sid, key, duration):
                    return
                taps += 1

                r2 = self.read_or_retry(sid)
                if r2 is None:
                    return
                change_x = r2["dx"] - dx
                change_y = r2["dy"] - dy
                if math.hypot(change_x, change_y) >= CHANGE_MIN_PX:
                    measured_x = change_x / signed_duration
                    measured_y = change_y / signed_duration
                    gain_x, gain_y = self.axis_gain[axis]
                    self.axis_gain[axis] = (
                        0.7 * gain_x + 0.3 * measured_x,
                        0.7 * gain_y + 0.3 * measured_y,
                    )
            if any(self.axis_gain[axis] is None for axis in ("x", "y")):
                continue


class CenterTab(CenterBase):
    """Centers the square on the screen midpoint without changing its rotation."""

    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Center",
                         "Holds the hold key (C) and taps the movement keys to center the "
                         "square on the screen midpoint, first left and right, then up and "
                         "down. Releases the hold key when centered, then turns itself off.")

    def build_settings(self):
        self._build_status()
        self.hold_var = self.add_setting("Hold key", "c")
        self.tol_x_var = self.add_setting("Horizontal tolerance (pixels)", "12")
        self.tol_y_var = self.add_setting("Vertical tolerance (pixels)", "3")
        self.tap_var = self.add_setting("Max tap length (seconds)", "0.25")
        self.pause_var = self.add_setting("Pause after each tap (seconds)", "0.3")
        self.max_var = self.add_setting("Max taps before giving up", "150")
        self.thresh_var = self.add_setting("White threshold (0 to 255)", "200")

    def prepare(self):
        self.message = ""
        self.done_sid = None
        self.phase = "Starting"
        self.result_var.set("")
        if ImageGrab is None:
            self.note_var.set("Center needs Pillow for screen capture. Run: pip install pillow")
            return False
        vk = parse_key(self.hold_var.get())
        if vk is None:
            self.note_var.set("Unknown hold key. Use one letter or number, or: "
                              "Space, Enter, Tab, Esc, Shift, Ctrl, Alt.")
            return False
        try:
            tolerance_x = int(float(self.tol_x_var.get()))
            tolerance_y = int(float(self.tol_y_var.get()))
            tap = float(self.tap_var.get())
            pause = float(self.pause_var.get())
            max_taps = int(float(self.max_var.get()))
            threshold = int(float(self.thresh_var.get()))
            if (tolerance_x < 0 or tolerance_y < 0 or tap <= 0 or pause < 0 or max_taps < 1
                    or not 0 <= threshold <= 255):
                raise ValueError
        except ValueError:
            self.note_var.set("Center settings must be numbers. Tolerances cannot be negative, "
                              "tap length must be positive, and threshold must be 0 to 255.")
            return False
        self.tolerance_x = tolerance_x
        self.tolerance_y = tolerance_y
        self.max_tap = tap
        self.pause_seconds = pause
        self.max_taps = max_taps
        self.white_threshold = threshold
        self.hold_vk = vk
        self.hold_label = key_display(self.hold_var.get())
        self.near = None
        self.size_ref = None
        self.axis_gain = {"x": None, "y": None}
        return True

    def worker(self, sid):
        try:
            self.phase = "Centering"
            key_down(self.hold_vk)
            self.holding_key = True
            try:
                self.center_position(sid)
            finally:
                key_up(self.hold_vk)
                self.holding_key = False
        except Exception as e:
            self.message = f"Center stopped with an error: {e}"
        finally:
            self.done_sid = self.session

    def idle_check(self):
        if self.running and self.done_sid == self.session:
            self.stop()
            return
        self.result_var.set(self.phase if self.running else self.message)


class AlignTab(CenterBase):
    """Looks down, then rotates the square upright as a standalone Run Once tool."""

    def __init__(self, parent, controller):
        super().__init__(parent, controller, "Align",
                         "Holds the selected key (C by default) while looking straight down, "
                         "then moves the mouse left or right until the square faces a cardinal "
                         "direction. Releases the key and turns itself off when done.")

    def build_settings(self):
        self._build_status()
        self.hold_var = self.add_setting("Hold key", "c")
        self.look_var = self.add_setting("Look down (seconds)", "5")
        self.align_var = self.add_setting("Line-up tolerance (degrees)", "0.2")
        self.thresh_var = self.add_setting("White threshold (0 to 255)", "200")

    def prepare(self):
        self.message = ""
        self.done_sid = None
        self.phase = "Starting"
        self.result_var.set("")
        if ImageGrab is None:
            self.note_var.set("Align needs Pillow for screen capture. Run: pip install pillow")
            return False
        vk = parse_key(self.hold_var.get())
        if vk is None:
            self.note_var.set("Unknown hold key. Use one letter or number, or: "
                              "Space, Enter, Tab, Esc, Shift, Ctrl, Alt.")
            return False
        try:
            look = float(self.look_var.get())
            align = float(self.align_var.get())
            threshold = int(float(self.thresh_var.get()))
            if look < 0 or not 0.05 <= align <= 10 or not 0 <= threshold <= 255:
                raise ValueError
        except ValueError:
            self.note_var.set("Align settings must be numbers. Look-down time cannot be "
                              "negative, line-up tolerance must be 0.05 to 10 degrees, and "
                              "threshold must be 0 to 255.")
            return False
        self.look_seconds = look
        self.align_tolerance = align
        self.white_threshold = threshold
        self.hold_vk = vk
        self.hold_label = key_display(self.hold_var.get())
        self.near = None
        self.size_ref = None
        return True

    def worker(self, sid):
        try:
            key_down(self.hold_vk)
            self.holding_key = True
            self.phase = "Looking down"
            try:
                if not self.look_down(sid):
                    return
                if not self.sleep_while_alive(sid, LOOK_SETTLE_SECONDS):
                    return
                self.phase = "Lining up the square"
                if self.align_tilt(sid):
                    self.message = "Square aligned."
            finally:
                key_up(self.hold_vk)
                self.holding_key = False
        except Exception as e:
            self.message = f"Align stopped with an error: {e}"
        finally:
            self.done_sid = self.session

    def idle_check(self):
        if self.running and self.done_sid == self.session:
            self.stop()
            return
        self.result_var.set(self.phase if self.running else self.message)


ANTI_AFK_ACTIONS = ("Random", "Jump", "Double jump", "Strafe", "Step forward and back",
                    "Camera nudge", "Crouch tap", "Left click", "Middle click",
                    "Right click", "Tap custom key")
ANTI_AFK_DIRECTIONS = ("Random", "Left", "Right")
ANTI_AFK_CROUCH_KEY = "c"
ANTI_AFK_GROUPS = {
    "custom_key": ("Tap custom key", "Random"),
    "presses": ("Jump", "Left click", "Middle click", "Right click",
                "Tap custom key", "Random"),
    "gap": ("Jump", "Double jump", "Left click", "Middle click", "Right click",
            "Tap custom key", "Random"),
    "hold": ("Strafe", "Step forward and back", "Crouch tap", "Random"),
    "nudge": ("Camera nudge", "Random"),
}


def parse_anti_afk(action, raw):
    """Checks the Anti AFK settings and returns them ready to use. raw holds the setting text by
    name. Only the settings the chosen action uses are checked; the rest get harmless defaults, so
    a hidden value can't block a start. Raises ValueError with a message the user can read."""
    if action not in ANTI_AFK_ACTIONS:
        raise ValueError("Choose an Anti AFK action from the list.")
    try:
        low, high = float(raw["min"]), float(raw["max"])
        max_actions, max_minutes = int(raw["max_actions"]), int(raw["max_minutes"])
    except (KeyError, ValueError):
        raise ValueError("Anti AFK settings must be numbers.")
    if not 1 <= low <= high <= 3600:
        raise ValueError("Wait times must be at least 1 second, with the minimum no more than the "
                         "maximum, up to 3600.")
    if not 0 <= max_actions <= 100000:
        raise ValueError("Stop after actions must be from 0 (never) to 100000.")
    if not 0 <= max_minutes <= 1440:
        raise ValueError("Stop after minutes must be from 0 (never) to 1440.")

    def used(group):
        return action in ANTI_AFK_GROUPS[group]

    key_vk = None
    if used("custom_key"):
        key_vk = parse_key(raw["custom_key"])
        if key_vk is None:
            raise ValueError("Unknown custom key. Use one letter or number, or: Space, Enter, Tab, "
                             "Esc, Shift, Ctrl, Alt.")
    presses, gap_ms = 1, 150
    if used("presses"):
        try:
            presses = int(raw["presses"])
        except ValueError:
            raise ValueError("Presses in a row must be a whole number.")
        if not 1 <= presses <= 5:
            raise ValueError("Presses in a row must be from 1 to 5.")
    if used("gap"):
        try:
            gap_ms = int(raw["gap"])
        except ValueError:
            raise ValueError("Gap between presses must be a whole number of milliseconds.")
        if not 20 <= gap_ms <= 2000:
            raise ValueError("Gap between presses must be from 20 to 2000 milliseconds.")
    hold_ms, variation = 200, 0
    if used("hold"):
        try:
            hold_ms, variation = int(raw["hold"]), int(raw["variation"])
        except ValueError:
            raise ValueError("Hold time and variation must be whole numbers.")
        if not 20 <= hold_ms <= 5000:
            raise ValueError("Hold time must be from 20 to 5000 milliseconds.")
        if not 0 <= variation <= 50:
            raise ValueError("Hold time variation must be from 0 to 50 percent.")
    nudge_px, direction = 12, "Random"
    if used("nudge"):
        try:
            nudge_px = int(raw["nudge"])
        except ValueError:
            raise ValueError("Camera nudge must be a whole number of pixels.")
        if not 1 <= nudge_px <= 200:
            raise ValueError("Camera nudge must be from 1 to 200 pixels.")
        direction = raw["direction"]
        if direction not in ANTI_AFK_DIRECTIONS:
            raise ValueError("Camera nudge direction must be Random, Left, or Right.")
    return {"action": action, "key_vk": key_vk, "min_wait": low, "max_wait": high,
            "presses": presses, "gap_seconds": gap_ms / 1000, "hold_seconds": hold_ms / 1000,
            "variation": variation / 100, "nudge_px": nudge_px, "direction": direction,
            "max_actions": max_actions, "max_minutes": max_minutes}


class AntiAFKTab(ModuleFrame):
    """Does something small every so often so the game doesn't log you out for being idle."""

    GROUP = "Independent"

    def __init__(self, parent, controller):
        self._held = set()
        self._paused_held = set()
        self.choice = "Random"
        self.key_vk = None
        self.crouch_vk = None
        self.min_wait = 20.0
        self.max_wait = 40.0
        self.presses = 1
        self.gap_seconds = 0.15
        self.hold_seconds = 0.2
        self.variation = 0.0
        self.nudge_px = 12
        self.nudge_direction = "Random"
        self.max_actions = 0
        self.max_minutes = 0
        self.actions_done = 0
        self.done_sid = None
        super().__init__(parent, controller, "Anti AFK",
                         "Every so often, does something small so the game does not log you out "
                         "for being idle. Options the chosen action does not use are greyed out; "
                         "Random uses them all. Jump, clicks, and taps can repeat several times "
                         "with a gap. "
                         "Strafe, step, and the camera nudge always return to where they started. "
                         "It stops on its own if you set a limit.")

    def option_rule(self, group):
        """Greys a setting out unless the chosen action uses it. Random uses every setting, so
        nothing is greyed out for it. Settings with no group are always live."""
        if group is None:
            return None
        return lambda: self.action_var.get() in ANTI_AFK_GROUPS[group]

    def build_settings(self):
        self.action_var = self.add_dropdown("Action", ANTI_AFK_ACTIONS, "Random")
        self.custom_key_var = self.add_setting("Custom key (for Tap custom key)", "e",
                                               rule=self.option_rule("custom_key"))
        self.presses_var = self.add_setting("Presses in a row (1 to 5)", "1",
                                            rule=self.option_rule("presses"))
        self.gap_var = self.add_setting("Gap between presses (ms)", "150",
                                        rule=self.option_rule("gap"))
        self.hold_var = self.add_setting("Hold time (ms, strafe, step, crouch)", "200",
                                         rule=self.option_rule("hold"))
        self.variation_var = self.add_setting("Hold time variation (%)", "0",
                                              rule=self.option_rule("hold"))
        self.nudge_var = self.add_setting("Camera nudge (px)", "12",
                                          rule=self.option_rule("nudge"))
        self.direction_var = self.add_dropdown("Camera nudge direction", ANTI_AFK_DIRECTIONS,
                                               "Random", rule=self.option_rule("nudge"))
        self.min_var = self.add_setting("Wait at least (seconds)", "20")
        self.max_var = self.add_setting("Wait at most (seconds)", "40")
        self.max_actions_var = self.add_setting("Stop after actions (0 = never)", "0")
        self.max_minutes_var = self.add_setting("Stop after minutes (0 = never)", "0")

    def _raw_values(self):
        return {"custom_key": self.custom_key_var.get(), "min": self.min_var.get(),
                "max": self.max_var.get(), "presses": self.presses_var.get(),
                "gap": self.gap_var.get(), "hold": self.hold_var.get(),
                "variation": self.variation_var.get(), "nudge": self.nudge_var.get(),
                "direction": self.direction_var.get(), "max_actions": self.max_actions_var.get(),
                "max_minutes": self.max_minutes_var.get()}

    def prepare(self):
        try:
            settings = parse_anti_afk(self.action_var.get(), self._raw_values())
        except ValueError as error:
            self.note_var.set(str(error))
            return False
        self.choice = settings["action"]
        self.key_vk = settings["key_vk"]
        self.crouch_vk = parse_key(ANTI_AFK_CROUCH_KEY)
        self.min_wait = settings["min_wait"]
        self.max_wait = settings["max_wait"]
        self.presses = settings["presses"]
        self.gap_seconds = settings["gap_seconds"]
        self.hold_seconds = settings["hold_seconds"]
        self.variation = settings["variation"]
        self.nudge_px = settings["nudge_px"]
        self.nudge_direction = settings["direction"]
        self.max_actions = settings["max_actions"]
        self.max_minutes = settings["max_minutes"]
        return True

    def on_begin(self):
        self._held.clear()
        self._paused_held.clear()
        self.actions_done = 0
        self.done_sid = None

    def on_stop(self):
        for vk in list(self._held):
            key_up(vk)
        self._held.clear()
        self._paused_held.clear()

    def idle_check(self):
        if self.running and self.done_sid == self.session:
            self.stop()

    def _press(self, vk):
        key_down(vk)
        self._held.add(vk)

    def _release(self, vk):
        key_up(vk)
        self._held.discard(vk)

    def pause_inputs(self):
        self._paused_held = set(self._held)
        for vk in list(self._held):
            key_up(vk)
        self._held.clear()

    def resume_inputs(self):
        for vk in self._paused_held:
            key_down(vk)
            self._held.add(vk)
        self._paused_held.clear()

    def worker(self, sid):
        try:
            self._run(sid)
        finally:
            self.done_sid = self.session

    def _run(self, sid):
        started = time.perf_counter()
        while self.alive(sid):
            if not self.sleep_while_alive(sid, random.uniform(self.min_wait, self.max_wait)):
                return
            if self.max_actions and self.actions_done >= self.max_actions:
                return
            if self.max_minutes and time.perf_counter() - started >= self.max_minutes * 60:
                return
            if not self.perform(sid, self.pick_action()):
                return
            self.actions_done += 1

    def pick_action(self):
        if self.choice != "Random":
            return self.choice
        return random.choice([name for name in ANTI_AFK_ACTIONS if name != "Random"])

    def _hold_time(self):
        """The hold time for one action, varied by the chosen percentage."""
        if not self.variation:
            return self.hold_seconds
        return self.hold_seconds * random.uniform(1 - self.variation, 1 + self.variation)

    def _series(self, sid, count, press):
        """Presses count times, with the chosen gap between presses. Returns False if stopped."""
        for index in range(count):
            if index and not self.sleep_while_alive(sid, self.gap_seconds):
                return False
            if not press(sid):
                return False
        return True

    def _click(self, sid, button):
        if not self.pause_point(sid):
            return False
        button_click(button)
        return True

    def perform(self, sid, kind):
        """Does one action. Returns False if the run was stopped."""
        if kind == "Jump":
            return self._series(sid, self.presses, lambda s: self._hold(s, VK_SPACE, 0.05))
        if kind == "Double jump":
            return self._series(sid, 2, lambda s: self._hold(s, VK_SPACE, 0.05))
        if kind == "Strafe":
            hold = self._hold_time()
            return self._hold(sid, VK_A, hold) and self._hold(sid, VK_D, hold)
        if kind == "Step forward and back":
            hold = self._hold_time()
            return self._hold(sid, VK_W, hold) and self._hold(sid, VK_S, hold)
        if kind == "Camera nudge":
            return self._nudge(sid)
        if kind == "Crouch tap":
            return self._hold(sid, self.crouch_vk, self._hold_time())
        if kind == "Left click":
            return self._series(sid, self.presses, lambda s: self._click(s, "Left"))
        if kind == "Middle click":
            return self._series(sid, self.presses, lambda s: self._click(s, "Middle"))
        if kind == "Right click":
            return self._series(sid, self.presses, lambda s: self._click(s, "Right"))
        if kind == "Tap custom key":
            return self._series(sid, self.presses, lambda s: self._hold(s, self.key_vk, 0.05))
        return False

    def _hold(self, sid, vk, seconds):
        if not self.pause_point(sid):
            return False
        self._press(vk)
        try:
            return self.sleep_while_alive(sid, seconds)
        finally:
            self._release(vk)

    def _nudge(self, sid):
        """Turns the camera a little one way, then back, so the view ends where it started."""
        if not self.pause_point(sid):
            return False
        if self.nudge_direction == "Random":
            sign = random.choice((-1, 1))
        else:
            sign = -1 if self.nudge_direction == "Left" else 1
        step = sign * self.nudge_px
        move_rel(step, 0)
        try:
            return self.sleep_while_alive(sid, 0.08)
        finally:
            move_rel(-step, 0)


class StartSelectedTab(ModuleFrame):
    """Starts every tool ticked 'Include in Start Selected' together, after one countdown."""

    GROUP = "Selected"
    INCLUDABLE = False
    PAUSABLE = False
    RESETTABLE = False

    def __init__(self, parent, controller, tools):
        self.tools = tools
        self.launched = []
        super().__init__(parent, controller, "START SELECTED",
                         START_SELECTED_DESCRIPTION)

    def build_settings(self):
        tk.Label(self.settings, text="Tools that will start", font=FONT_BODY, fg=TEXT,
                 bg=PANEL).pack(anchor="w", pady=(4, 4))
        self.list_var = tk.StringVar(value="")
        tk.Label(self.settings, textvariable=self.list_var, font=FONT_BODY, fg=MUTED,
                 bg=PANEL, justify="left", anchor="w").pack(fill="x")

    def chosen_tools(self):
        return [m for m in self.tools if m.INCLUDABLE and m.include_var.get()]

    def refresh_list(self):
        chosen = self.chosen_tools()
        if chosen:
            self.list_var.set("\n".join("\u2022  " + m.module_name for m in chosen))
        else:
            self.list_var.set("No tools are ticked yet. Tick \"Include in Start Selected\" "
                              "on a tool's page.")

    def acquire(self):
        return True

    def start(self):
        if self.running or self.countdown_job is not None:
            return
        chosen = self.chosen_tools()
        if not chosen:
            self.note_var.set("No tools are ticked. Tick \"Include in Start Selected\" "
                              "on a tool first.")
            return
        run_once = [m for m in chosen if m.GROUP == "Run Once"]
        if run_once and len(chosen) > 1:
            self.note_var.set("Run Once tools must be selected by themselves. Untick all "
                              "other tools.")
            return
        independent = [m for m in chosen if m.GROUP == "Independent"]
        if len(independent) > 1:
            self.note_var.set("Only one Independent tool can be selected at a time. "
                              "Untick all but one.")
            return
        super().start()

    def on_begin(self):
        self.launched = []
        skipped = []
        for mod in self.chosen_tools():
            if mod.running:
                continue
            if mod.launch_now():
                self.launched.append(mod)
            else:
                skipped.append(mod.module_name)
        if skipped:
            self.note_var.set("Didn't start: " + ", ".join(skipped) +
                              ". See the message on each tool.")

    def worker(self, sid):
        self.hold_until_stopped(sid)

    def on_stop(self):
        for mod in self.launched:
            mod.stop()
        self.launched = []

    def idle_check(self):
        self.refresh_list()
        if self.running and not any(m.running for m in self.launched):
            self.stop()


class App:
    def __init__(self, root):
        self.root = root
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
        root.title(APP_TITLE)
        root.configure(bg=BG)
        set_initial_window_geometry(root, 880, 820, 640, 520)
        root.resizable(True, True)
        self.settings_path = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "dinguschan-tools", "settings.json")
        saved = self.read_app_settings()
        set_theme_palette(saved["accent_color"], saved["group_color"],
                          saved["red_color"])
        self.setup_styles()
        self.legacy_active_modules_settings = saved
        self.overlay_organization_var = tk.StringVar(
            root, value=saved["overlay_organization"])
        self.overlay_organization_var.trace_add(
            "write", self._overlay_organization_changed)
        self.settings_window = None
        self.accent_color_button = None
        self.group_color_button = None
        self.red_color_button = None
        self.active_modules_window = None
        self.active_modules_text = None
        self.profiles_path = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "dinguschan-tools", "profiles.json")
        self.profiles, profile_error = self.read_profiles()
        self.profile_storage_error = profile_error
        self.default_profile_snapshot = None

        self.controller = Controller()

        header = tk.Frame(root, bg=HEADER_BG)
        header.pack(fill="x")
        self.brand_icon = None
        self.window_icon = None
        title_padx = 14
        if Image is not None and ImageTk is not None:
            with Image.open(os.path.join(FONT_DIR, "icon.png")) as source:
                source_image = source.convert("RGBA")
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            brand_image = source_image.copy()
            brand_image.thumbnail((48, 36), resampling)
            self.brand_icon = ImageTk.PhotoImage(brand_image, master=root)
            window_icon_image = source_image.copy()
            window_icon_image.thumbnail((64, 64), resampling)
            square_icon = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            square_icon.alpha_composite(
                window_icon_image,
                ((64 - window_icon_image.width) // 2,
                 (64 - window_icon_image.height) // 2))
            self.window_icon = ImageTk.PhotoImage(square_icon, master=root)
            root.iconphoto(True, self.window_icon)
            tk.Label(header, image=self.brand_icon, bg=HEADER_BG).pack(
                side="left", padx=(14, 8), pady=4)
            title_padx = (0, 14)
        tk.Label(header, text=APP_TITLE, font=FONT_HEAD, fg=TEXT,
                 bg=HEADER_BG).pack(side="left", padx=title_padx, pady=8)
        tk.Label(header, text="Press Shift+` (~) to stop all", font=FONT_SMALL,
                 fg=GROUP_TAG_COLOR,
                 bg=HEADER_BG).pack(side="right", padx=(7, 14))
        tk.Frame(header, bg=BORDER, width=1, height=22).pack(
            side="right", padx=(0, 4), pady=4)
        settings_button = RoundBox(
            header, fill=OFF_BG, outline=BORDER, radius=RADIUS_FIELD, pad=2)
        settings_button.pack(side="right", padx=(0, 8), pady=5)
        RoundButton(
            settings_button.inner, text="Settings", command=self.open_settings,
            font=FONT_SMALL, bg=OFF_BG, fg=TEXT, hover=OFF_HOVER,
            padx=8, pady=3, anchor="w", icon="settings").pack()
        tk.Frame(root, bg=GREEN, height=2).pack(fill="x")

        self.build_profile_footer(root)
        if profile_error:
            self.profile_status_var.set(profile_error)

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(body, bg=SIDEBAR, width=220)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content = tk.Frame(body, bg=PANEL)
        self.content.pack(side="left", fill="both", expand=True)

        self.active_modules_module = ActiveModulesTab(
            self.content, self.controller, self, saved)
        self.cps_module = CPSOverlayTab(self.content, self.controller)
        self.keyboard_visualizer_module = KeyboardVisualizerTab(
            self.content, self.controller)
        self.mouse_visualizer_module = MouseVisualizerTab(
            self.content, self.controller)
        self.list_active_modules_var = self.active_modules_module.overlay_var
        self.hide_active_modules_when_idle_var = (
            self.active_modules_module.hide_when_idle_var)
        for overlay_module in (self.cps_module, self.keyboard_visualizer_module,
                               self.mouse_visualizer_module):
            overlay_module.overlay_layout_changed = self.reposition_overlays
        autoeat_module = AutoeatTab(self.content, self.controller)
        hotbar_alert_module = HotbarAlertTab(self.content, self.controller)
        hotbar_alert_module.autoeat_module = autoeat_module
        self.group_modules = {
            "Simultaneous": [hotbar_alert_module, autoeat_module,
                             AutoSprintTab(self.content, self.controller),
                             InputBlockerTab(self.content, self.controller),
                             ClicksTab(self.content, self.controller),
                             KeysTab(self.content, self.controller),
                             SpinTab(self.content, self.controller)],
            "Independent": [AutofishTab(self.content, self.controller),
                            GridPathTab(self.content, self.controller),
                            PatternTab(self.content, self.controller),
                            AntiAFKTab(self.content, self.controller)],
            "Run Once": [AlignTab(self.content, self.controller),
                           CenterTab(self.content, self.controller)],
            "EXTRAS": [self.active_modules_module,
                       CoordinatesTab(self.content, self.controller), self.cps_module,
                       self.keyboard_visualizer_module, self.mouse_visualizer_module],
        }
        self.tools = [m for group in self.group_modules.values() for m in group]
        self.selected_page = StartSelectedTab(self.content, self.controller, self.tools)
        self.modules = self.tools + [self.selected_page]
        self.initial_module_defaults = self.capture_profile()
        for module in self.tools:
            module.reset_defaults_callback = self.reset_module_to_defaults

        self.selected = None
        self.selected_group = None
        self.sidebar_group_modules = {}
        self.group_items = {}
        self.group_lists = {}
        self.module_items = []
        self.selected_item = None
        self.build_sidebar()
        self.match_button_heights()

        self.select(self.group_modules[DEFAULT_GROUP][0])
        self.ensure_default_profile()
        root.after(PROFILE_AUTOSAVE_INTERVAL_MS, self.autosave_default_profile)

        root.bind_all("<MouseWheel>", self.on_wheel)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll_hotkey()
        self.refresh_sidebar()
        root.after_idle(self.apply_windows_titlebar_colors)

    def match_button_heights(self):
        self.root.update_idletasks()
        widgets = list(self.root.winfo_children())
        entries = []
        buttons = []
        while widgets:
            widget = widgets.pop()
            if isinstance(widget, RoundEntry):
                entries.append(widget)
            elif isinstance(widget, RoundButton):
                buttons.append(widget)
            widgets.extend(widget.winfo_children())

        if not entries:
            return
        field_height = max(entry.winfo_reqheight() for entry in entries)
        for button in buttons:
            if not button.rb_square:
                button.set_height(field_height)

    def apply_windows_titlebar_colors(self):
        try:
            set_windows_titlebar_colors(self.root, SIDEBAR, TEXT)
        except OSError as error:
            self.profile_status_var.set(f"Could not update window title bar: {error}")

    def read_profiles(self):
        try:
            with open(self.profiles_path, "r", encoding="utf-8") as file:
                profiles = json.load(file)
        except FileNotFoundError:
            return {}, ""
        except (OSError, json.JSONDecodeError) as error:
            return {}, f"Could not read profiles: {error}"
        if not isinstance(profiles, dict) or any(
                not isinstance(name, str) or not isinstance(profile, dict)
                for name, profile in profiles.items()):
            return {}, "Could not read profiles: profile file has an invalid format."
        return profiles, ""

    @staticmethod
    def profile_dropdown_choices(profiles):
        choices = sorted(name for name in profiles if name != DEFAULT_PROFILE_NAME)
        if DEFAULT_PROFILE_NAME in profiles:
            choices.append(DEFAULT_PROFILE_NAME)
        return choices

    def profile_snapshot(self, profile):
        return json.dumps(profile, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    def write_profiles(self, profiles, error_prefix):
        try:
            os.makedirs(os.path.dirname(self.profiles_path), exist_ok=True)
            with open(self.profiles_path, "w", encoding="utf-8") as file:
                json.dump(profiles, file, ensure_ascii=True, indent=2)
                file.write("\n")
        except OSError as error:
            self.profile_status_var.set(f"{error_prefix}: {error}")
            return False

        self.profiles = profiles
        self.profile_storage_error = ""
        choices = self.profile_dropdown_choices(profiles)
        if self.profile_dropdown.choices != choices:
            self.profile_dropdown.set_choices(choices)
        return True

    def save_default_profile(self, profile):
        if self.profile_storage_error:
            self.profile_status_var.set(
                f"Could not auto-save {DEFAULT_PROFILE_NAME}: {self.profile_storage_error}")
            return False
        profiles = dict(self.profiles)
        profiles[DEFAULT_PROFILE_NAME] = profile
        if not self.write_profiles(profiles, f"Could not auto-save {DEFAULT_PROFILE_NAME}"):
            return False
        self.default_profile_snapshot = self.profile_snapshot(profile)
        return True

    def ensure_default_profile(self):
        if self.profile_storage_error:
            return
        if (DEFAULT_PROFILE_NAME not in self.profiles
                and LEGACY_DEFAULT_PROFILE_NAME in self.profiles):
            profiles = dict(self.profiles)
            profiles[DEFAULT_PROFILE_NAME] = profiles.pop(LEGACY_DEFAULT_PROFILE_NAME)
            if not self.write_profiles(
                    profiles, f"Could not rename {LEGACY_DEFAULT_PROFILE_NAME} profile"):
                return
        if DEFAULT_PROFILE_NAME not in self.profiles:
            if not self.save_default_profile(self.capture_profile()):
                return
        else:
            self.default_profile_snapshot = self.profile_snapshot(self.capture_profile())
        self.profile_choice_var.set(DEFAULT_PROFILE_NAME)
        self.root.after_idle(self.load_profile)

    def autosave_default_profile(self):
        if not self.profile_storage_error:
            profile = self.capture_profile()
            if self.profile_snapshot(profile) != self.default_profile_snapshot:
                self.save_default_profile(profile)
        self.root.after(PROFILE_AUTOSAVE_INTERVAL_MS, self.autosave_default_profile)

    def build_profile_footer(self, parent):
        footer = tk.Frame(parent, bg=HEADER_BG)
        footer.pack(side="bottom", fill="x")
        tk.Frame(footer, bg=GREEN, height=2).pack(fill="x")
        row = tk.Frame(footer, bg=HEADER_BG)
        row.pack(fill="x", padx=6, pady=6)

        self.profile_name_var = tk.StringVar(value="")
        self.profile_name_entry = RoundEntry(
            row, self.profile_name_var, width=18, placeholder="Name this profile...")
        self.profile_name_entry.pack(side="left")
        RoundButton(row, text="Save", command=self.save_profile, font=FONT_SMALL,
                    bg=GREEN, fg=ON_GREEN, hover=GREEN_HOVER, padx=12,
                    pady=4).pack(side="left", padx=(6, 6))

        self.profile_choice_var = tk.StringVar(value="")
        self.profile_dropdown = RoundDropdown(
            row, self.profile_choice_var, self.profile_dropdown_choices(self.profiles), width=15,
            open_above=True)
        self.profile_dropdown.pack(side="left")
        self.profile_dropdown.set_enabled(True)
        RoundButton(row, text="Load profile", command=self.load_profile, font=FONT_SMALL,
                    bg=GREEN, fg=ON_GREEN, hover=GREEN_HOVER, padx=12,
                    pady=4).pack(side="left", padx=(6, 0))
        self.profile_status_var = tk.StringVar(value="")
        self.profile_status_label = tk.Label(
            footer, textvariable=self.profile_status_var, font=FONT_SMALL,
            fg=MUTED, bg=HEADER_BG, anchor="w")
        self._profile_status_shown = False
        self._profile_status_clear_job = None
        self._profile_status_clear_message = None
        self.profile_status_var.trace_add("write", lambda *_: self._sync_profile_status())

    def _sync_profile_status(self):
        if (self._profile_status_clear_job is not None
                and self.profile_status_var.get() != self._profile_status_clear_message):
            self.root.after_cancel(self._profile_status_clear_job)
            self._profile_status_clear_job = None
            self._profile_status_clear_message = None
        want = bool(self.profile_status_var.get())
        if want and not self._profile_status_shown:
            self.profile_status_label.pack(fill="x", padx=12, pady=(0, 6))
            self._profile_status_shown = True
        elif not want and self._profile_status_shown:
            self.profile_status_label.pack_forget()
            self._profile_status_shown = False

    def _show_loaded_profile_status(self, profile_name):
        if self._profile_status_clear_job is not None:
            self.root.after_cancel(self._profile_status_clear_job)
            self._profile_status_clear_job = None
            self._profile_status_clear_message = None
        message = f"Loaded profile “{profile_name}”."
        self._profile_status_clear_message = message
        self.profile_status_var.set(message)
        self._profile_status_clear_job = self.root.after(
            3000, self._clear_loaded_profile_status)

    def _clear_loaded_profile_status(self):
        message = self._profile_status_clear_message
        self._profile_status_clear_job = None
        self._profile_status_clear_message = None
        if self.profile_status_var.get() == message:
            self.profile_status_var.set("")

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("Settings")
        window.configure(bg=BG)
        window.resizable(False, False)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self.close_settings)

        panel = RoundBox(window, fill=PANEL, outline=GREEN,
                         radius=RADIUS_CARD, pad=14)
        panel.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(panel.inner, text="Overlay organization",
                 font=FONT_BODY, fg=TEXT, bg=PANEL).grid(
                     row=0, column=0, sticky="w", padx=(0, 18), pady=6)
        organization = RoundDropdown(
            panel.inner, self.overlay_organization_var,
            ("Vertical", "Horizontal"), width=14)
        organization.grid(row=0, column=1, sticky="e", pady=6)
        organization.set_enabled(True)

        tk.Label(panel.inner, text="GUI colors",
                 font=FONT_BODY, fg=TEXT, bg=PANEL).grid(
                     row=1, column=0, columnspan=2, sticky="w", pady=(12, 4))
        tk.Label(panel.inner, text="Accent color",
                 font=FONT_BODY, fg=MUTED, bg=PANEL).grid(
                     row=2, column=0, sticky="w", padx=(0, 18), pady=4)
        self.accent_color_button = RoundButton(
            panel.inner, text=GREEN, command=self.choose_accent_color,
            font=FONT_SMALL, bg=GREEN, fg=ON_GREEN, hover=GREEN_HOVER,
            padx=12, pady=4)
        self.accent_color_button.grid(row=2, column=1, sticky="e", pady=4)

        tk.Label(panel.inner, text="Group tag color",
                 font=FONT_BODY, fg=MUTED, bg=PANEL).grid(
                     row=3, column=0, sticky="w", padx=(0, 18), pady=4)
        self.group_color_button = RoundButton(
            panel.inner, text=GROUP_TAG_COLOR, command=self.choose_group_color,
            font=FONT_SMALL, bg=GROUP_TAG_COLOR, fg=text_color_for(GROUP_TAG_COLOR),
            hover=lerp_hex(GROUP_TAG_COLOR, "#ffffff", 0.18), padx=12, pady=4)
        self.group_color_button.grid(row=3, column=1, sticky="e", pady=4)
        tk.Label(panel.inner, text="Error / reset color",
                 font=FONT_BODY, fg=MUTED, bg=PANEL).grid(
                     row=4, column=0, sticky="w", padx=(0, 18), pady=4)
        self.red_color_button = RoundButton(
            panel.inner, text=RED, command=self.choose_red_color,
            font=FONT_SMALL, bg=RED, fg=ON_RED, hover=RED_HOVER,
            padx=12, pady=4)
        self.red_color_button.grid(row=4, column=1, sticky="e", pady=4)
        tk.Label(panel.inner, text="Changes apply immediately and are saved automatically.",
                 font=FONT_SMALL, fg=MUTED, bg=PANEL).grid(
                     row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        window.update_idletasks()
        work_area = get_screen_work_area()
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        x = work_area.left + (work_area.right - work_area.left - width) // 2
        y = work_area.top + (work_area.bottom - work_area.top - height) // 2
        window.geometry(f"{width}x{height}+{x}+{y}")

    def close_settings(self):
        if self.settings_window is not None:
            if self.settings_window.winfo_exists():
                self.settings_window.destroy()
            self.settings_window = None
        self.accent_color_button = None
        self.group_color_button = None
        self.red_color_button = None

    def _overlay_organization_changed(self, *_args):
        self.save_app_settings()
        self.reposition_overlays()

    def choose_accent_color(self):
        _rgb, color = colorchooser.askcolor(
            color=GREEN, parent=self.settings_window, title="Choose accent color")
        if color:
            self._apply_gui_colors(accent=color)

    def choose_group_color(self):
        _rgb, color = colorchooser.askcolor(
            color=GROUP_TAG_COLOR, parent=self.settings_window,
            title="Choose group tag color")
        if color:
            self._apply_gui_colors(group_color=color)

    def choose_red_color(self):
        _rgb, color = colorchooser.askcolor(
            color=RED, parent=self.settings_window, title="Choose error / reset color")
        if color:
            self._apply_gui_colors(red_color=color)

    def _apply_gui_colors(self, accent=None, group_color=None, red_color=None):
        new_accent = (accent or GREEN).lower()
        new_group = (group_color or GROUP_TAG_COLOR).lower()
        new_red = (red_color or RED).lower()
        if (not valid_hex_color(new_accent) or not valid_hex_color(new_group)
                or not valid_hex_color(new_red)):
            return
        replacements = set_theme_palette(new_accent, new_group, new_red)
        self.setup_styles()
        self._recolor_widget_tree(self.root, replacements)
        for module in self.tools:
            if module.reset_button is not None:
                module.reset_button.set_style(
                    RED, RESET_BUTTON_FG, RED_HOVER, module.reset_button.enabled)
        if self.accent_color_button is not None:
            self.accent_color_button.set_text(GREEN)
            self.accent_color_button.set_style(GREEN, ON_GREEN, GREEN_HOVER)
        if self.group_color_button is not None:
            self.group_color_button.set_text(GROUP_TAG_COLOR)
            self.group_color_button.set_style(
                GROUP_TAG_COLOR, text_color_for(GROUP_TAG_COLOR),
                lerp_hex(GROUP_TAG_COLOR, "#ffffff", 0.18))
        if self.red_color_button is not None:
            self.red_color_button.set_text(RED)
            self.red_color_button.set_style(RED, ON_RED, RED_HOVER)
        self.save_app_settings()

    def _recolor_widget_tree(self, root, replacements):
        widgets = [root]
        color_options = (
            "bg", "fg", "activebackground", "activeforeground",
            "disabledforeground", "insertbackground", "selectbackground",
            "selectforeground", "highlightbackground", "highlightcolor",
            "troughcolor",
        )
        while widgets:
            widget = widgets.pop()
            if isinstance(widget, RoundBox):
                widget.set_colors(
                    fill=replacements.get(widget.box_fill, widget.box_fill),
                    outline=replacements.get(widget.box_outline, widget.box_outline))
            if isinstance(widget, RoundButton):
                widget.set_style(
                    replacements.get(widget.base_bg, widget.base_bg),
                    replacements.get(widget.fg_color, widget.fg_color),
                    replacements.get(widget.hover_bg, widget.hover_bg),
                    widget.enabled)
            for option in color_options:
                try:
                    value = widget.cget(option)
                    if value in replacements:
                        widget.configure(**{option: replacements[value]})
                except tk.TclError:
                    continue
            if isinstance(widget, tk.Canvas):
                for item in widget.find_all():
                    for option in ("fill", "outline"):
                        try:
                            value = widget.itemcget(item, option)
                            if value in replacements:
                                widget.itemconfigure(
                                    item, **{option: replacements[value]})
                        except tk.TclError:
                            continue
            widgets.extend(widget.winfo_children())

    def read_app_settings(self):
        settings = {
            "list_active_modules": "Yes",
            "hide_active_modules_when_idle": "No",
            "active_modules_position": "Bottom right",
            "overlay_organization": "Horizontal",
            "accent_color": DEFAULT_GREEN,
            "group_color": DEFAULT_GROUP_TAG_COLOR,
            "red_color": DEFAULT_RED,
        }
        try:
            with open(self.settings_path, "r", encoding="utf-8") as file:
                saved = json.load(file)
        except (OSError, json.JSONDecodeError):
            return settings
        if isinstance(saved, dict):
            for key in settings:
                if key == "active_modules_position":
                    if saved.get(key) in OVERLAY_POSITIONS:
                        settings[key] = saved[key]
                elif key == "overlay_organization":
                    if saved.get(key) in ("Vertical", "Horizontal"):
                        settings[key] = saved[key]
                elif key in ("accent_color", "group_color", "red_color"):
                    if valid_hex_color(saved.get(key)):
                        settings[key] = saved[key].lower()
                elif saved.get(key) in ("Yes", "No"):
                    settings[key] = saved[key]
        return settings

    def save_app_settings(self):
        settings = {
            "list_active_modules": self.list_active_modules_var.get(),
            "hide_active_modules_when_idle": self.hide_active_modules_when_idle_var.get(),
            "active_modules_position": self.active_modules_module.position_var.get(),
            "overlay_organization": self.overlay_organization_var.get(),
            "accent_color": GREEN,
            "group_color": GROUP_TAG_COLOR,
            "red_color": RED,
        }
        try:
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as file:
                json.dump(settings, file, ensure_ascii=True, indent=2)
                file.write("\n")
        except OSError as error:
            self.profile_status_var.set(f"Could not save settings: {error}")

    def refresh_active_modules_overlay(self):
        overlay_modules = (
            self.cps_module, self.keyboard_visualizer_module,
            self.mouse_visualizer_module)
        active = [
            mod.display_name for mod in self.tools
            if mod.running or (
                mod in overlay_modules and mod.overlay_var.get() == "Yes")
        ]
        if (self.list_active_modules_var.get() == "No"
                or (self.hide_active_modules_when_idle_var.get() == "Yes" and not active)):
            if self.active_modules_window is not None:
                if self.active_modules_window.winfo_exists():
                    self.active_modules_window.destroy()
                self.active_modules_window = None
                self.active_modules_text = None
                self.reposition_overlays()
            return

        if (self.active_modules_window is None
                or not self.active_modules_window.winfo_exists()):
            overlay = tk.Toplevel(self.root)
            self.active_modules_window = overlay
            overlay.wm_overrideredirect(True)
            overlay.wm_attributes("-topmost", True)
            overlay.configure(bg=OVERLAY_TRANSPARENT)
            overlay.wm_attributes("-transparentcolor", OVERLAY_TRANSPARENT)
            panel = RoundBox(overlay, fill=PANEL, outline=GREEN,
                             radius=RADIUS_BTN, pad=RADIUS_BTN)
            panel.pack(fill="both", expand=True)
            title = tk.Label(panel.inner, text="ACTIVE MODULES",
                             font=(FONT_FAMILY, 9), fg=GREEN,
                             bg=PANEL, anchor="w")
            title.pack(fill="x")
            divider = tk.Frame(panel.inner, bg=GREEN, height=2)
            divider.pack(fill="x", pady=(5, 6))
            self.active_modules_text = tk.StringVar(self.root, value="")
            module_list = tk.Label(
                panel.inner, textvariable=self.active_modules_text,
                font=(FONT_FAMILY, 10), fg=TEXT, bg=PANEL,
                justify="left", anchor="w")
            module_list.pack(fill="x")
            for widget in (overlay, panel, panel.bg_canvas, panel.inner,
                           title, divider, module_list):
                widget.bind("<Button-1>", self._focus_main_window_from_overlay,
                            add="+")

        text = "\n".join(f"• {name}" for name in active) or "No active modules"
        self.active_modules_text.set(text)
        self.reposition_overlays()

    def reposition_overlays(self):
        overlays = []
        if (self.active_modules_window is not None
                and self.active_modules_window.winfo_exists()):
            overlays.append((self.active_modules_window,
                             self.active_modules_module.position_var.get()))
        if self.cps_module.overlay is not None and self.cps_module.overlay.winfo_exists():
            overlays.append((self.cps_module.overlay, self.cps_module.position_var.get()))
        if (self.keyboard_visualizer_module.overlay is not None
                and self.keyboard_visualizer_module.overlay.winfo_exists()):
            overlays.append((self.keyboard_visualizer_module.overlay,
                             self.keyboard_visualizer_module.position_var.get()))
        if (self.mouse_visualizer_module.overlay is not None
                and self.mouse_visualizer_module.overlay.winfo_exists()):
            overlays.append((self.mouse_visualizer_module.overlay,
                             self.mouse_visualizer_module.position_var.get()))
        if not overlays:
            return

        work_area = get_screen_work_area()
        groups = {}
        for window, position in overlays:
            window.update_idletasks()
            size = (window.winfo_reqwidth(), window.winfo_reqheight())
            groups.setdefault(position, []).append((window, size[0], size[1]))

        for position, group in groups.items():
            if self.overlay_organization_var.get() == "Horizontal":
                total_width = (sum(item[1] for item in group)
                               + OVERLAY_STACK_GAP * (len(group) - 1))
                x = (work_area.left + OVERLAY_STACK_GAP
                     if position.endswith("left")
                     else max(work_area.left,
                              work_area.right - OVERLAY_STACK_GAP - total_width))
                for window, width, height in group:
                    y = (work_area.top + OVERLAY_STACK_GAP
                         if position.startswith("Top")
                         else max(work_area.top,
                                  work_area.bottom - height - OVERLAY_STACK_GAP))
                    window.geometry(f"{width}x{height}+{x}+{y}")
                    x += width + OVERLAY_STACK_GAP
            else:
                total_height = (sum(item[2] for item in group)
                                + OVERLAY_STACK_GAP * (len(group) - 1))
                y = (work_area.top + OVERLAY_STACK_GAP
                     if position.startswith("Top")
                     else max(work_area.top,
                              work_area.bottom - OVERLAY_STACK_GAP - total_height))
                for window, width, height in group:
                    x = (work_area.left + OVERLAY_STACK_GAP
                         if position.endswith("left")
                         else max(work_area.left,
                                  work_area.right - width - OVERLAY_STACK_GAP))
                    window.geometry(f"{width}x{height}+{x}+{y}")
                    y += height + OVERLAY_STACK_GAP

    def _focus_main_window_from_overlay(self, _event=None):
        if any(mod.running for mod in self.tools):
            return "break"
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        return "break"

    def capture_profile(self):
        fields = {
            "Keys": ("key_var", "mode_var", "interval_var"),
            "Clicks": ("button_var", "mode_var", "interval_var"),
            "Hotbar Alert": ("slot_var", "threshold_var"),
            "Autosprint": ("interval_var",),
            "Spin": ("direction_var", "speed_var"),
            "Grid Path": ("space_pause_var",),
            "Autoeat": ("slot_var", "threshold_var", "poll_var", "pause_var"),
            "Autofish": ("poll_var", "crouch_var", "no_bite_var", "swap_var", "rod_slot_var",
                         "flare_var",
                         "flare_interval_var", "flare_slot_var", "spot_var",
                         "spot_min_var", "spot_max_var", "spot_limit_var", "spot_vertical_min_var",
                         "spot_vertical_max_var", "spot_vertical_limit_var"),
            "Center": ("hold_var", "tol_x_var", "tol_y_var", "tap_var", "pause_var",
                       "max_var", "thresh_var"),
            "Align": ("hold_var", "look_var", "align_var", "thresh_var"),
            "Anti AFK": ("action_var", "custom_key_var", "presses_var", "gap_var", "hold_var",
                         "variation_var", "nudge_var", "direction_var", "min_var", "max_var",
                         "max_actions_var", "max_minutes_var"),
            "Active Modules": ("overlay_var", "position_var", "hide_when_idle_var"),
            "CPS": ("overlay_var", "position_var"),
            "Keyboard Visualizer": ("overlay_var", "position_var"),
            "Mouse Visualizer": ("overlay_var", "position_var"),
        }
        tools = {}
        for mod in self.tools:
            settings = {
                name: getattr(mod, name).get()
                for name in fields.get(mod.module_name, ())
            }
            settings["delay"] = mod.delay_var.get()
            settings["include"] = mod.include_var.get()
            if mod.module_name == "Coordinates":
                settings["coordinates"] = [
                    [row[field].get() for field in ("name", "x", "y", "z")]
                    for row in mod.rows
                ]
            elif mod.module_name == "Grid Path":
                settings["grid"] = {
                    "cols": mod.cols,
                    "rows": mod.rows,
                    "path": [list(cell) for cell in mod.path],
                }
            elif mod.module_name == "Pattern":
                settings["steps"] = [
                    [row["action"].get(), row["key_var"].get(), row["click_var"].get(),
                     row["secs_var"].get(), row["direction_var"].get(),
                     row["pixels_var"].get()]
                    for row in mod.rows
                ]
            elif mod.module_name == "Input Blocker":
                settings["inputs"] = [
                    [row["type"].get(),
                     row["key"].get() if row["type"].get() == "Key"
                     else row["button"].get()]
                    for row in mod.rows
                ]
            tools[mod.module_name] = settings
        return {"version": PROFILE_VERSION, "tools": tools}

    def validate_profile(self, profile, allow_invalid_values=False):
        fields = {
            "Keys": ("key_var", "mode_var", "interval_var"),
            "Clicks": ("button_var", "mode_var", "interval_var"),
            "Hotbar Alert": ("slot_var", "threshold_var"),
            "Autosprint": ("interval_var",),
            "Spin": ("direction_var", "speed_var"),
            "Grid Path": ("space_pause_var",),
            "Autoeat": ("slot_var", "threshold_var", "poll_var", "pause_var"),
            "Autofish": ("poll_var", "crouch_var", "no_bite_var", "swap_var", "rod_slot_var",
                         "flare_var",
                         "flare_interval_var", "flare_slot_var", "spot_var",
                         "spot_min_var", "spot_max_var", "spot_limit_var", "spot_vertical_min_var",
                         "spot_vertical_max_var", "spot_vertical_limit_var"),
            "Center": ("hold_var", "tol_x_var", "tol_y_var", "tap_var", "pause_var",
                       "max_var", "thresh_var"),
            "Align": ("hold_var", "look_var", "align_var", "thresh_var"),
            "Anti AFK": ("action_var", "custom_key_var", "presses_var", "gap_var", "hold_var",
                         "variation_var", "nudge_var", "direction_var", "min_var", "max_var",
                         "max_actions_var", "max_minutes_var"),
            "Active Modules": ("overlay_var", "position_var", "hide_when_idle_var"),
            "CPS": ("overlay_var", "position_var"),
            "Keyboard Visualizer": ("overlay_var", "position_var"),
            "Mouse Visualizer": ("overlay_var", "position_var"),
        }
        if (not isinstance(profile, dict) or profile.get("version") not in (1, PROFILE_VERSION)
                or not isinstance(profile.get("tools"), dict)):
            raise ValueError("This profile has an unsupported or invalid format.")

        normalized = {}
        for mod in self.tools:
            settings = profile["tools"].get(mod.module_name)
            if mod.module_name == "Autosprint" and mod.module_name not in profile["tools"]:
                settings = profile["tools"].get("Auto-sprint")
            if mod.module_name == "Autoeat" and mod.module_name not in profile["tools"]:
                settings = {
                    "slot_var": "0",
                    "threshold_var": "35",
                    "poll_var": str(DEFAULT_SCREEN_POLL_INTERVAL_MS),
                    "pause_var": "Yes",
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif (mod.module_name == "Hotbar Alert"
                  and mod.module_name not in profile["tools"]):
                settings = {
                    "slot_var": "9",
                    "threshold_var": str(HOTBAR_DEFAULT_THRESHOLD),
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif mod.module_name == "Anti AFK" and mod.module_name not in profile["tools"]:
                settings = {
                    "action_var": "Random",
                    "custom_key_var": "e",
                    "min_var": "20",
                    "max_var": "40",
                    "hold_var": "200",
                    "nudge_var": "12",
                    "direction_var": "Random",
                    "variation_var": "0",
                    "presses_var": "1",
                    "gap_var": "150",
                    "max_actions_var": "0",
                    "max_minutes_var": "0",
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif mod.module_name == "Autofish" and mod.module_name not in profile["tools"]:
                settings = {
                    "poll_var": str(DEFAULT_SCREEN_POLL_INTERVAL_MS),
                    "crouch_var": "No",
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif (mod.module_name == "Autosprint"
                  and mod.module_name not in profile["tools"]
                  and "Auto-sprint" not in profile["tools"]):
                settings = {
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif mod.module_name == "Input Blocker" and mod.module_name not in profile["tools"]:
                settings = {
                    "inputs": [],
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif mod.module_name == "Coordinates" and mod.module_name not in profile["tools"]:
                settings = {
                    "coordinates": [],
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif (mod.module_name == "Active Modules"
                  and mod.module_name not in profile["tools"]):
                settings = {
                    "overlay_var": self.legacy_active_modules_settings["list_active_modules"],
                    "position_var":
                        self.legacy_active_modules_settings["active_modules_position"],
                    "hide_when_idle_var":
                        self.legacy_active_modules_settings["hide_active_modules_when_idle"],
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif mod.module_name == "CPS" and mod.module_name not in profile["tools"]:
                settings = {
                    "overlay_var": "No",
                    "position_var": "Top right",
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif (mod.module_name == "Keyboard Visualizer"
                  and mod.module_name not in profile["tools"]):
                settings = {
                    "overlay_var": "No",
                    "position_var": "Bottom left",
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            elif (mod.module_name == "Mouse Visualizer"
                  and mod.module_name not in profile["tools"]):
                settings = {
                    "overlay_var": "No",
                    "position_var": "Bottom left",
                    "delay": str(DELAY_SECONDS),
                    "include": False,
                }
            if not isinstance(settings, dict):
                raise ValueError(f"Profile is missing settings for {mod.module_name}.")
            if not isinstance(settings.get("delay"), str):
                raise ValueError(f"Profile has invalid settings for {mod.module_name}.")
            if not isinstance(settings.get("include"), bool):
                raise ValueError(f"Profile has invalid settings for {mod.module_name}.")
            values = {}
            for name in fields.get(mod.module_name, ()):
                if (name == "overlay_var" and name not in settings
                        and mod.module_name == "Active Modules"):
                    value = self.legacy_active_modules_settings["list_active_modules"]
                elif (name == "hide_when_idle_var" and name not in settings
                      and mod.module_name == "Active Modules"):
                    value = self.legacy_active_modules_settings["hide_active_modules_when_idle"]
                elif (name == "position_var" and name not in settings
                      and mod.module_name == "Active Modules"):
                    value = self.legacy_active_modules_settings["active_modules_position"]
                elif (name == "overlay_var" and name not in settings
                        and mod.module_name == "Keyboard Visualizer"):
                    value = "No"
                elif (name == "position_var" and name not in settings
                      and mod.module_name == "CPS"):
                    value = "Top right"
                elif (name == "position_var" and name not in settings
                      and mod.module_name == "Keyboard Visualizer"):
                    value = "Bottom left"
                elif (name == "overlay_var" and name not in settings
                      and mod.module_name == "Mouse Visualizer"):
                    value = "No"
                elif (name == "position_var" and name not in settings
                      and mod.module_name == "Mouse Visualizer"):
                    value = "Bottom left"
                elif (name == "poll_var" and name not in settings
                        and mod.module_name in ("Autoeat", "Autofish")):
                    value = str(DEFAULT_SCREEN_POLL_INTERVAL_MS)
                elif (name == "crouch_var" and name not in settings
                      and mod.module_name == "Autofish"):
                    value = "No"
                elif (name == "no_bite_var" and name not in settings
                      and mod.module_name == "Autofish"):
                    value = "45"
                elif (name in ("swap_var", "rod_slot_var", "flare_var", "flare_interval_var",
                               "flare_slot_var")
                      and name not in settings and mod.module_name == "Autofish"):
                    value = {"swap_var": "No", "rod_slot_var": "8", "flare_var": "No",
                             "flare_interval_var": "70", "flare_slot_var": "9"}[name]
                elif (name in ("spot_var", "spot_min_var", "spot_max_var", "spot_limit_var",
                               "spot_vertical_min_var", "spot_vertical_max_var",
                               "spot_vertical_limit_var")
                      and name not in settings and mod.module_name == "Autofish"):
                    value = {"spot_var": "No", "spot_min_var": "150",
                             "spot_max_var": "500", "spot_limit_var": "600",
                             "spot_vertical_min_var": "40", "spot_vertical_max_var": "160",
                             "spot_vertical_limit_var": "240"}[name]
                elif (name == "pause_var" and name not in settings
                      and mod.module_name == "Autoeat"):
                    value = "Yes"
                elif (name == "interval_var" and name not in settings
                      and mod.module_name == "Autosprint"):
                    value = "0.1"
                elif (name == "space_pause_var" and name not in settings
                      and mod.module_name == "Grid Path"):
                    value = "0"
                else:
                    value = settings.get(name)
                    if value is None and mod.module_name == "Align" and name == "hold_var":
                        value = "c"
                if (profile["version"] == 1
                        and mod.module_name == "Keyboard Visualizer"
                        and name == "position_var" and value == "Top left"):
                    value = "Bottom left"
                if not isinstance(value, str):
                    raise ValueError(f"Profile has invalid settings for {mod.module_name}.")
                values[name] = value

            if mod.module_name == "Autoeat" and not allow_invalid_values:
                if values["slot_var"] not in AUTOEAT_SLOT_ORDER:
                    raise ValueError("Profile has an invalid Autoeat hotbar slot.")
                if values["pause_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid Autoeat pause setting.")
                try:
                    if int(values["threshold_var"]) < 0:
                        raise ValueError
                except ValueError:
                    raise ValueError("Profile has an invalid Autoeat health threshold.")
                try:
                    parse_screen_poll_interval(values["poll_var"])
                except ValueError:
                    raise ValueError("Profile has an invalid Autoeat screen poll interval.")
            elif mod.module_name == "Hotbar Alert" and not allow_invalid_values:
                try:
                    parse_hotbar_slots(
                        values["slot_var"], HotbarAlertTab.SLOT_OPTIONS)
                except ValueError:
                    raise ValueError("Profile has invalid Hotbar Alert slots.")
                try:
                    if int(values["threshold_var"]) < 1:
                        raise ValueError
                except ValueError:
                    raise ValueError("Profile has an invalid Hotbar Alert threshold.")
            elif mod.module_name == "Anti AFK" and not allow_invalid_values:
                try:
                    parse_anti_afk(values["action_var"], {
                        "custom_key": values["custom_key_var"], "min": values["min_var"],
                        "max": values["max_var"], "presses": values["presses_var"],
                        "gap": values["gap_var"], "hold": values["hold_var"],
                        "variation": values["variation_var"], "nudge": values["nudge_var"],
                        "direction": values["direction_var"],
                        "max_actions": values["max_actions_var"],
                        "max_minutes": values["max_minutes_var"]})
                except ValueError as error:
                    raise ValueError(f"Profile has invalid Anti AFK settings: {error}")
            elif mod.module_name == "Autofish" and not allow_invalid_values:
                if values["crouch_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid Autofish crouch setting.")
                if values["spot_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid Autofish spot setting.")
                try:
                    parse_no_bite_timeout(values["no_bite_var"])
                except ValueError:
                    raise ValueError("Profile has an invalid Autofish no-bite recast time.")
                if values["swap_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid Autofish fishing rod setting.")
                if values["rod_slot_var"] not in AUTOEAT_SLOT_ORDER:
                    raise ValueError("Profile has an invalid Autofish fishing rod slot.")
                if values["flare_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid Autofish flare setting.")
                if values["flare_var"] == "Yes" and values["swap_var"] == "Yes":
                    try:
                        parse_flare_interval(values["flare_interval_var"])
                    except ValueError:
                        raise ValueError("Profile has an invalid Autofish flare interval.")
                if values["spot_var"] == "Yes":
                    try:
                        parse_spot_range(values["spot_min_var"], values["spot_max_var"],
                                         values["spot_limit_var"])
                    except ValueError:
                        raise ValueError("Profile has invalid Autofish spot turn amounts.")
                    try:
                        parse_vertical_range(values["spot_vertical_min_var"],
                                             values["spot_vertical_max_var"],
                                             values["spot_vertical_limit_var"])
                    except ValueError:
                        raise ValueError("Profile has invalid Autofish vertical change amounts.")
                try:
                    parse_screen_poll_interval(values["poll_var"])
                except ValueError:
                    raise ValueError("Profile has an invalid Autofish screen poll interval.")
            elif mod.module_name == "Autosprint" and not allow_invalid_values:
                try:
                    interval = float(values["interval_var"])
                    if not math.isfinite(interval) or interval < 0.02:
                        raise ValueError
                except ValueError:
                    raise ValueError("Profile has an invalid Autosprint interval.")
            elif mod.module_name == "Input Blocker":
                inputs = settings.get("inputs")
                if (not isinstance(inputs, list) or len(inputs) > MAX_INPUT_BLOCKS
                        or any(not isinstance(item, list) or len(item) != 2
                               or item[0] not in INPUT_BLOCKER_TYPES
                               or not isinstance(item[1], str) for item in inputs)):
                    raise ValueError("Profile has invalid Input Blocker settings.")
                if not allow_invalid_values:
                    for input_type, value in inputs:
                        if input_type == "Key":
                            vk = parse_key(value)
                            if vk is None:
                                raise ValueError("Profile has an invalid blocked key.")
                            if vk == VK_OEM_3:
                                raise ValueError(
                                    "Profile cannot block the emergency-stop key (` / ~).")
                        elif value not in BUTTON_FLAGS:
                            raise ValueError("Profile has an invalid blocked mouse button.")
                values["inputs"] = inputs
            elif mod.module_name == "Coordinates":
                coordinates = settings.get("coordinates")
                if (not isinstance(coordinates, list)
                        or any(not isinstance(row, list) or len(row) != 4
                               or any(not isinstance(value, str) for value in row)
                               for row in coordinates)):
                    raise ValueError("Profile has invalid Coordinates settings.")
                values["coordinates"] = coordinates
            elif mod.module_name == "Active Modules":
                if values["overlay_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid Active Modules overlay setting.")
                if values["hide_when_idle_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid Active Modules idle setting.")
                if values["position_var"] not in OVERLAY_POSITIONS:
                    raise ValueError("Profile has an invalid Active Modules overlay position.")
            elif mod.module_name == "CPS":
                if values["overlay_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid CPS overlay setting.")
                if values["position_var"] not in OVERLAY_POSITIONS:
                    raise ValueError("Profile has an invalid CPS overlay position.")
            elif mod.module_name == "Keyboard Visualizer":
                if values["overlay_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid keyboard overlay setting.")
                if values["position_var"] not in OVERLAY_POSITIONS:
                    raise ValueError("Profile has an invalid keyboard overlay position.")
            elif mod.module_name == "Mouse Visualizer":
                if values["overlay_var"] not in ("No", "Yes"):
                    raise ValueError("Profile has an invalid mouse overlay setting.")
                if values["position_var"] not in OVERLAY_POSITIONS:
                    raise ValueError("Profile has an invalid mouse overlay position.")
            elif mod.module_name == "Grid Path":
                if not allow_invalid_values:
                    try:
                        parse_grid_space_pause(values["space_pause_var"])
                    except ValueError:
                        raise ValueError(
                            "Profile has an invalid Grid Path pause between spaces.")
                grid = settings.get("grid")
                if (not isinstance(grid, dict)
                        or type(grid.get("cols")) is not int
                        or type(grid.get("rows")) is not int
                        or not 2 <= grid["cols"] <= MAX_GRID_SIZE
                        or not 2 <= grid["rows"] <= MAX_GRID_SIZE
                        or not isinstance(grid.get("path"), list)):
                    raise ValueError("Profile has invalid Grid Path settings.")
                path = grid["path"]
                if any(not isinstance(cell, list) or len(cell) != 2
                       or type(cell[0]) is not int or type(cell[1]) is not int
                       or not 0 <= cell[0] < grid["cols"]
                       or not 0 <= cell[1] < grid["rows"] for cell in path):
                    raise ValueError("Profile has an invalid Grid Path.")
                values["grid"] = {
                    "cols": grid["cols"], "rows": grid["rows"],
                    "path": [tuple(cell) for cell in path],
                }
            elif mod.module_name == "Pattern":
                steps = settings.get("steps")
                if (not isinstance(steps, list) or len(steps) > MAX_PATTERN_STEPS
                        or any(not isinstance(step, list) or len(step) not in (3, 4, 6)
                               or step[0] not in PATTERN_ACTIONS
                               or not isinstance(step[1], str)
                               or (len(step) == 3 and not isinstance(step[2], str))
                               or (len(step) == 4 and (
                                   step[2] not in PATTERN_CLICK_OPTIONS
                                   or not isinstance(step[3], str)))
                               or (len(step) == 6 and (
                                   step[2] not in PATTERN_CLICK_OPTIONS
                                   or not isinstance(step[3], str)
                                   or not isinstance(step[4], str)
                                   or step[4] not in PATTERN_CAMERA_DIRECTIONS
                                   or not isinstance(step[5], str)))
                               for step in steps)):
                    raise ValueError("Profile has invalid Pattern settings.")
                normalized_steps = []
                for step in steps:
                    if len(step) == 3:
                        normalized_step = [
                            step[0], step[1], "None", step[2],
                            PATTERN_CAMERA_DIRECTIONS[0], PATTERN_CAMERA_DEFAULT_PIXELS]
                    elif len(step) == 4:
                        normalized_step = [
                            step[0], step[1], step[2], step[3],
                            PATTERN_CAMERA_DIRECTIONS[0], PATTERN_CAMERA_DEFAULT_PIXELS]
                    else:
                        normalized_step = step
                    if normalized_step[0] == ACT_CAMERA:
                        try:
                            parse_pattern_camera_pixels(normalized_step[5])
                        except ValueError:
                            raise ValueError(
                                "Profile has invalid Pattern camera pixel amount.")
                    normalized_steps.append(normalized_step)
                values["steps"] = normalized_steps

            values["delay"] = settings["delay"]
            values["include"] = settings["include"]
            normalized[mod.module_name] = values
        return normalized

    def save_profile(self):
        name = ("" if self.profile_name_entry.placeholder_active
                else self.profile_name_var.get().strip())
        if not name:
            self.profile_status_var.set("Enter a name for this profile.")
            return
        if len(name) > 64:
            self.profile_status_var.set("Profile names must be 64 characters or fewer.")
            return

        profile = self.capture_profile()
        profiles = dict(self.profiles)
        profiles[name] = profile
        if not self.write_profiles(profiles, "Could not save profile"):
            return

        if name == DEFAULT_PROFILE_NAME:
            self.default_profile_snapshot = self.profile_snapshot(profile)
        self.profile_choice_var.set(name)
        self.profile_status_var.set(f"Saved profile “{name}”.")

    def reset_module_to_defaults(self, mod):
        if not mod.editable():
            return
        try:
            settings_by_tool = self.validate_profile(
                self.initial_module_defaults, allow_invalid_values=True)
        except ValueError as error:
            mod.note_var.set(f"Could not reset to defaults: {error}")
            return
        self._apply_module_settings(mod, settings_by_tool[mod.module_name])
        self.profile_status_var.set(f"{mod.module_name} reset to defaults.")

    def _apply_module_settings(self, mod, settings):
        for setting_name, value in settings.items():
            if setting_name in ("delay", "include", "grid", "steps", "inputs",
                                "coordinates"):
                continue
            getattr(mod, setting_name).set(value)
        mod.delay_var.set(settings["delay"])
        mod.include_var.set(settings["include"])
        mod.note_var.set("")
        if mod.module_name == "Grid Path":
            grid = settings["grid"]
            mod.cols, mod.rows = grid["cols"], grid["rows"]
            mod.cols_var.set(str(mod.cols))
            mod.rows_var.set(str(mod.rows))
            mod.path = list(grid["path"])
            mod.canvas.xview_moveto(0)
            mod.canvas.yview_moveto(0)
            mod.draw()
        elif mod.module_name == "Pattern":
            for row in mod.rows:
                row["frame"].destroy()
            mod.rows.clear()
            mod.rows_frame.pack_forget()
            for action, key, click, seconds, direction, pixels in settings["steps"]:
                mod.add_row(action, key, seconds, click, direction, pixels)
        elif mod.module_name == "Input Blocker":
            for row in mod.rows:
                row["frame"].destroy()
            mod.rows.clear()
            mod.rows_frame.pack_forget()
            for input_type, value in settings["inputs"]:
                mod.add_row(input_type, value)
        elif mod.module_name == "Coordinates":
            for row in mod.rows:
                row["frame"].destroy()
            mod.rows.clear()
            mod.rows_frame.pack_forget()
            for coordinate in settings["coordinates"]:
                mod.add_row(*coordinate)

    def load_profile(self):
        name = self.profile_choice_var.get()
        if name not in self.profiles:
            self.profile_status_var.set("Choose a profile to load.")
            return
        if any(mod.running or mod.countdown_job is not None for mod in self.modules):
            self.profile_status_var.set("Stop all tools before loading a profile.")
            return
        try:
            settings_by_tool = self.validate_profile(
                self.profiles[name], allow_invalid_values=name == DEFAULT_PROFILE_NAME)
        except ValueError as error:
            self.profile_status_var.set(f"Could not load profile: {error}")
            return

        profile_name = name
        for mod in self.tools:
            self._apply_module_settings(mod, settings_by_tool[mod.module_name])

        self.profile_name_entry.set_value(profile_name)
        self._show_loaded_profile_status(profile_name)

    def build_sidebar(self):
        self.selected_item = NavItem(self.sidebar, "\u25B6 START SELECTED",
                                     lambda: self.select(self.selected_page), pad_left=14,
                                     info=START_SELECTED_DESCRIPTION,
                                     info_open_above=True)
        self.selected_item.pack(side="bottom", fill="x", pady=(0, 10))
        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(side="bottom", fill="x",
                                                        padx=12, pady=8)

        self.category_mode_var = tk.StringVar(value="Compatibility")

        tk.Frame(self.sidebar, bg=SIDEBAR, height=10).pack(fill="x")
        category_header = tk.Frame(self.sidebar, bg=SIDEBAR)
        category_header.pack(fill="x", padx=(14, 8), pady=(2, 5))
        tk.Label(category_header, text="Categories", bg=SIDEBAR, fg=MUTED,
                 font=(FONT_FAMILY, 9, "bold")).pack(side="left")
        self.category_mode_dropdown = RoundDropdown(
            category_header, self.category_mode_var, ("Compatibility", "Type"), width=14,
            command=self._on_category_mode_changed)
        self.category_mode_dropdown.set_enabled(True)
        self.category_filter_button = CategoryFilterButton(
            category_header, self._open_category_filter)
        self.category_filter_button.pack(side="right")

        self.category_navigation = tk.Frame(self.sidebar, bg=SIDEBAR)
        self.category_navigation.pack(fill="x")
        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(fill="x", padx=12, pady=8)
        self.category_list_area = tk.Frame(self.sidebar, bg=SIDEBAR)
        self.category_list_area.pack(fill="both", expand=True)
        self._rebuild_sidebar_categories()

    def _open_category_filter(self):
        self.category_mode_dropdown.open_menu(
            anchor=self.category_filter_button, align_right=True)

    def _on_category_mode_changed(self):
        self.category_filter_button.set_active(self.category_mode_var.get() == "Type")
        self._rebuild_sidebar_categories()

    def _rebuild_sidebar_categories(self):
        if self.category_mode_var.get() == "Compatibility":
            groups = self.group_modules
            group_info = GROUP_INFO
            show_compatibility_tags = True
        else:
            groups = {category: [] for category in TYPE_CATEGORY_ORDER}
            for mod in self.tools:
                category = MODULE_TYPE_BY_NAME.get(mod.module_name)
                if category is None:
                    raise ValueError(
                        f"Module {mod.module_name!r} has no type category.")
                groups[category].append(mod)
            group_info = TYPE_CATEGORY_INFO
            show_compatibility_tags = False

        for child in self.category_navigation.winfo_children():
            child.destroy()
        for child in self.category_list_area.winfo_children():
            child.destroy()
        self.group_items.clear()
        self.group_lists.clear()
        self.module_items.clear()
        self.sidebar_group_modules = groups

        for group, mods in groups.items():
            nav = NavItem(
                self.category_navigation, group.upper(),
                lambda g=group: self.select(self.sidebar_group_modules[g][0]),
                pad_left=8, info=group_info[group],
                tag_group=group if show_compatibility_tags else None)
            nav.pack(fill="x")
            self.group_items[group] = nav

            lst = tk.Frame(self.category_list_area, bg=SIDEBAR)
            for mod in mods:
                nav = NavItem(lst, mod.display_name,
                              lambda m=mod: self.select(m), pad_left=22)
                nav.pack(fill="x")
                self.module_items.append((mod, nav))
            self.group_lists[group] = lst

        if self.selected is not None:
            self.selected_group = None
            self.select(self.selected)

    def _show_list(self, group):
        for lst in self.group_lists.values():
            lst.pack_forget()
        if group is not None:
            self.group_lists[group].pack(fill="x", anchor="n")
        self.selected_group = group

    def select(self, mod):
        """Shows a page and the tool list it belongs to."""
        group = next((g for g, ms in self.sidebar_group_modules.items()
                      if mod in ms), None)
        if group != self.selected_group:
            self._show_list(group)
        if self.selected is not None:
            self.selected.pack_forget()
        self.selected = mod
        mod.pack(fill="both", expand=True)

    def setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Dark.Vertical.TScrollbar", background=OFF_BG,
                        troughcolor=PANEL, bordercolor=PANEL, arrowcolor=MUTED,
                        lightcolor=OFF_BG, darkcolor=OFF_BG)
        style.map("Dark.Vertical.TScrollbar",
                  background=[("active", BORDER), ("pressed", GREEN)])

    def on_wheel(self, event):
        if self.selected is not None:
            self.selected.scroll(event)

    def refresh_sidebar(self):
        phase = 0.5 + 0.5 * math.cos(2 * math.pi * (time.time() % 1.6) / 1.6)
        pulse = lerp_hex(GREEN_DIM, GREEN, phase)

        for mod, nav in self.module_items:
            busy = mod.running or mod.countdown_job is not None
            text = ("\u25CF  " if busy else "") + mod.display_name
            fg = pulse if mod.running else (GREEN if mod is self.selected else TEXT)
            nav.update_look(selected=mod is self.selected, text=text, fg=fg)

        for group, nav in self.group_items.items():
            any_busy = any(m.running or m.countdown_job is not None
                           for m in self.sidebar_group_modules[group])
            text = ("\u25CF  " if any_busy else "") + group.upper()
            selected = group == self.selected_group
            nav.update_look(selected=selected, text=text,
                            fg=GREEN if selected else MUTED)

        sp = self.selected_page
        busy = sp.running or sp.countdown_job is not None
        text = ("\u25CF  " if busy else "") + "\u25B6 START SELECTED"
        fg = pulse if sp.running else (GREEN if self.selected is sp else TEXT)
        self.selected_item.update_look(selected=self.selected is sp, text=text, fg=fg)

        self.refresh_active_modules_overlay()
        self.root.after(150, self.refresh_sidebar)

    def stop_all(self):
        for mod in self.modules:
            mod.stop()

    def poll_hotkey(self):
        if tilde_pressed():
            self.stop_all()
        self.root.after(50, self.poll_hotkey)

    def on_close(self):
        if not self.profile_storage_error:
            profile = self.capture_profile()
            if self.profile_snapshot(profile) != self.default_profile_snapshot:
                self.save_default_profile(profile)
        self.cps_module.close()
        self.keyboard_visualizer_module.close()
        self.mouse_visualizer_module.close()
        self.stop_all()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()