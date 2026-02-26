"""
Linux implementation of WindowInterface.

Uses kdotool (preferred on KDE Wayland) and xdotool (X11 fallback) to
query and control windows.  All subprocess commands are non-interactive —
the haircross bug (requiring mouse input) cannot occur here.
"""

import logging
import os
import shutil
import subprocess
from typing import List, Optional, Tuple

from StreamDock.domain.Models import WindowInfo
from .window_interface import WindowInterface

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application-name normalisation table
#
# Each entry: (keywords_lower, normalised_name, exact_matches_or_None)
# Exact-match is checked first (case-sensitive); keyword match is
# case-insensitive against both WM_CLASS and window title.
# ---------------------------------------------------------------------------
APP_PATTERNS: List[Tuple[list, str, Optional[list]]] = [
    ([" antigravity"],              "Antigravity", None),
    (["chrome"],                    "Chrome",       None),
    (["chromium"],                  "Chromium",     None),
    (["code"],                      "VSCode",        None),
    (["discord"],                   "Discord",       None),
    (["dolphin"],                   "Dolphin",       None),
    (["firefox"],                   "Firefox",       None),
    (["intellij"],                  "IntelliJ",      None),
    (["kate"],                      "Kate",          None),
    (["konsole"],                   "Konsole",       ["org.kde.konsole"]),
    (["obsidian"],                  "Obsidian",      None),
    (["pycharm"],                   "PyCharm",       None),
    (["slack"],                     "Slack",         None),
    (["spotify"],                   "Spotify",       None),
    (["telegram", "telegram-desktop"], "Telegram",  None),
    (["yakuake"],                   "Yakuake",       ["org.kde.yakuake"]),
    (["zoom", "zoom workplace"],    "Zoom",          None),
]


class LinuxWindowManager(WindowInterface):
    """
    Linux window manager using kdotool / xdotool.

    Tool availability is cached as instance state after the first check.
    Call ``reset_tool_cache()`` to force a re-check (useful in tests).

    Haircross safety contract
    -------------------------
    ``get_active_window()`` only ever invokes::

        kdotool getactivewindow
        xdotool getactivewindow

    It never calls ``selectwindow``, bare ``xprop`` (without ``-id``), or
    any other command that requires mouse input.
    """

    def __init__(self) -> None:
        self._kdotool_available: Optional[bool] = None
        self._xdotool_available: Optional[bool] = None
        self._qdbus_available: Optional[bool] = None
        self._kwin_script_path: Optional[str] = None
        self._kwin_script_id: str = "streamdock_detect"

    def __del__(self) -> None:
        """Cleanup temporary KWin script files and unload from DBus."""
        try:
            if self._qdbus_available and self._kwin_script_path:
                # Unload script
                subprocess.run(
                    ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", self._kwin_script_id],
                    capture_output=True, check=False, timeout=1
                )
                # Remove file
                if os.path.exists(self._kwin_script_path):
                    os.remove(self._kwin_script_path)
        except Exception:
            pass  # Best effort during interpreter shutdown

    # ------------------------------------------------------------------ #
    # Public helpers                                                       #
    # ------------------------------------------------------------------ #

    def reset_tool_cache(self) -> None:
        """Clear cached tool-availability flags (useful in tests)."""
        self._kdotool_available = None
        self._xdotool_available = None

    def is_kdotool_available(self) -> bool:
        """Return ``True`` if kdotool is installed and functional."""
        if self._kdotool_available is not None:
            return self._kdotool_available
        if shutil.which("kdotool") is None:
            self._kdotool_available = False
            return False
        try:
            result = subprocess.run(
                ["kdotool", "getactivewindow"],
                capture_output=True, text=True, timeout=1, check=False,
            )
            self._kdotool_available = result.returncode == 0
        except Exception:
            self._kdotool_available = False
        return self._kdotool_available

    def is_xdotool_available(self) -> bool:
        """Return ``True`` if xdotool is installed."""
        if self._xdotool_available is not None:
            return self._xdotool_available
        if shutil.which("xdotool") is None:
            self._xdotool_available = False
            return False
        try:
            # We only need to know the binary exists and launches.
            # A non-zero exit (e.g. no X11 display) is fine.
            subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True, text=True, timeout=1, check=False,
            )
            self._xdotool_available = True
        except Exception:
            self._xdotool_available = False
        return self._xdotool_available

    def is_qdbus_kwin_available(self) -> bool:
        """Return ``True`` if qdbus6 and KWin scripting are available."""
        if self._qdbus_available is not None:
            return self._qdbus_available
        if shutil.which("qdbus6") is None:
            self._qdbus_available = False
            return False
        try:
            r = subprocess.run(
                ["qdbus6", "org.kde.KWin", "/Scripting"],
                capture_output=True, text=True, timeout=1, check=False,
            )
            self._qdbus_available = r.returncode == 0
        except Exception:
            self._qdbus_available = False
        return self._qdbus_available

    # ------------------------------------------------------------------ #
    # WindowInterface implementation                                       #
    # ------------------------------------------------------------------ #

    def get_active_window(self) -> Optional[WindowInfo]:
        """
        Return the currently focused window.

        Tries kdotool first (Wayland/KDE), falls back to qdbus scripting if Wayland
        and kdotool panics (KWin 6.3 bug). Falls back to xdotool (X11/XWayland).
        Both explicit tool paths use ``getactivewindow`` — no mouse interaction required.
        """
        try:
            if self.is_kdotool_available():
                window = self._kdotool_get_active_window()
                if window:
                    return window
            
            # If in Wayland, prefer qdbus6 KWin scripting fallback over xdotool
            if os.environ.get("WAYLAND_DISPLAY") and self.is_qdbus_kwin_available():
                window = self._qdbus_get_active_window()
                if window:
                    return window

            if self.is_xdotool_available():
                return self._xdotool_get_active_window()

        except Exception as exc:
            logger.error("Error getting active window: %s", exc, exc_info=True)
        return None

    def search_window_by_class(self, class_name: str) -> Optional[str]:
        """Return the ID of the first window matching *class_name*, or ``None``."""
        try:
            if self.is_kdotool_available():
                wid = self._kdotool_search_by_class(class_name)
                if wid:
                    return wid
            if self.is_xdotool_available():
                return self._xdotool_search_by_class(class_name)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error searching window by class: %s", exc, exc_info=True)
        return None

    def search_window_by_name(self, name: str) -> Optional[str]:
        """Search for a window by its visible title (name), ignoring class."""
        if not name:
            return None
        
        try:
            regex_pattern = self._to_case_insensitive_regex(name)
            # Try kdotool first
            if self.is_kdotool_available():
                r = subprocess.run(
                    ["kdotool", "search", "--name", regex_pattern],
                    capture_output=True, text=True, timeout=1, check=False,
                )
                if r.returncode == 0:
                    lines = r.stdout.strip().splitlines()
                    if lines:
                        return lines[0].strip()

            # Fallback to xdotool
            if self.is_xdotool_available():
                r = subprocess.run(
                    ["xdotool", "search", "--name", regex_pattern],
                    capture_output=True, text=True, timeout=1, check=False,
                )
                if r.returncode == 0:
                    lines = r.stdout.strip().splitlines()
                    if lines:
                        return lines[-1].strip()  # Bottom of stack
        except Exception as exc:
            logger.error("Error searching window by name '%s': %s", name, exc, exc_info=True)
        return None

    def activate_window(self, window_id: str) -> bool:
        """Bring window *window_id* to the foreground."""
        try:
            if self.is_kdotool_available() and self._kdotool_activate(window_id):
                return True
            if self.is_xdotool_available() and self._xdotool_activate(window_id):
                return True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error activating window: %s", exc, exc_info=True)
        return False

    # ------------------------------------------------------------------ #
    # Name normalisation                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def normalize_class_name(class_name: str, title: str = "") -> str:
        """Translate a raw WM_CLASS string to a human-readable app name."""
        if not class_name:
            return "unknown"
        cl = class_name.lower()
        tl = title.lower() if title else ""
        for keywords, normalized, exact_matches in APP_PATTERNS:
            if exact_matches and class_name in exact_matches:
                return normalized
            if any(kw in cl or kw in tl for kw in keywords):
                return normalized
        return class_name

    @staticmethod
    def extract_app_from_title(title: str) -> str:
        """Guess an application name from the window title string."""
        if not title:
            return "unknown"
        # Try direct normalisation first
        normalised = LinuxWindowManager.normalize_class_name(title, title)
        if normalised != title:
            return normalised
        # Common title patterns: "Doc — App" / "Doc - App" / "App: Doc"
        for sep in (" — ", " - "):
            if sep in title:
                return LinuxWindowManager.normalize_class_name(
                    title.split(sep)[-1].strip(), title
                )
        if ": " in title:
            return LinuxWindowManager.normalize_class_name(
                title.split(":")[0].strip(), title
            )
        fallback = title.split()[0] if title.split() else "unknown"
        return LinuxWindowManager.normalize_class_name(fallback, title)

    # ------------------------------------------------------------------ #
    # Private subprocess helpers — kdotool                                #
    # ------------------------------------------------------------------ #

    def _kdotool_get_active_window(self) -> Optional[WindowInfo]:
        r = subprocess.run(
            ["kdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=1, check=False,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        window_id = r.stdout.strip()

        r_name = subprocess.run(
            ["kdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=1, check=False,
        )
        title = r_name.stdout.strip() if r_name.returncode == 0 else ""

        r_class = subprocess.run(
            ["kdotool", "getactivewindow", "getwindowclassname"],
            capture_output=True, text=True, timeout=1, check=False,
        )
        if r_class.returncode == 0 and r_class.stdout.strip():
            class_ = self.normalize_class_name(r_class.stdout.strip(), title)
        else:
            class_ = self.extract_app_from_title(title)

        logger.debug("kdotool: title=%s class=%s", title, class_)
        return WindowInfo(title=title, class_=class_, raw=title,
                          method="kdotool", window_id=window_id)

    @staticmethod
    def _to_case_insensitive_regex(text: str) -> str:
        """Convert a string into a case-insensitive POSIX-compatible regex."""
        import re
        escaped = re.escape(text)
        return re.sub(r'[a-zA-Z]', lambda m: f"[{m.group().upper()}{m.group().lower()}]", escaped)

    def _kdotool_search_by_class(self, class_name: str) -> Optional[str]:
        regex_pattern = self._to_case_insensitive_regex(class_name)
        r = subprocess.run(
            ["kdotool", "search", "--class", regex_pattern],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("\n")[0]
        return None

    def _kdotool_activate(self, window_id: str) -> bool:
        r = subprocess.run(
            ["kdotool", "windowactivate", window_id],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return r.returncode == 0

    # ------------------------------------------------------------------ #
    # Private subprocess helpers — xdotool                                #
    # ------------------------------------------------------------------ #

    def _xdotool_get_active_window(self) -> Optional[WindowInfo]:
        r = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=1, check=False,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        window_id = r.stdout.strip()

        r_name = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=1, check=False,
        )
        title = r_name.stdout.strip() if r_name.returncode == 0 else ""

        r_class = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowclassname"],
            capture_output=True, text=True, timeout=1, check=False,
        )
        if r_class.returncode == 0 and r_class.stdout.strip():
            class_ = self.normalize_class_name(r_class.stdout.strip(), title)
        else:
            class_ = self.extract_app_from_title(title)

        logger.debug("xdotool: title=%s class=%s", title, class_)
        return WindowInfo(title=title, class_=class_, raw=title,
                          method="xdotool", window_id=window_id)

    def _xdotool_search_by_class(self, class_name: str) -> Optional[str]:
        regex_pattern = self._to_case_insensitive_regex(class_name)
        r = subprocess.run(
            ["xdotool", "search", "--all", "--onlyvisible", "--class", regex_pattern],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("\n")[-1]
        return None

    def _xdotool_activate(self, window_id: str) -> bool:
        r = subprocess.run(
            ["xdotool", "windowactivate", window_id],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return r.returncode == 0

    # ------------------------------------------------------------------ #
    # Private subprocess helpers — qdbus fallback (KWin 6.3+ workaround) #
    # ------------------------------------------------------------------ #

    def _qdbus_get_active_window(self) -> Optional[WindowInfo]:
        """
        Extract active window directly via a temporary KWin script loaded over DBus.
        Used as a fallback when kdotool crashes due to malformed DBus paths in KWin 6.3.
        """
        import time
        import uuid
        import tempfile

        # Generate a unique marker for this specific query
        marker_id = uuid.uuid4().hex
        
        # 1. Prepare and write script to a temporary file
        if not self._kwin_script_path:
            script_content = f"""
            var active = workspace.activeWindow;
            if (active) {{
                print("{marker_id}|" + active.caption + "|||" + active.resourceClass);
            }}
            """
            fd, path = tempfile.mkstemp(suffix=".js", prefix="streamdock_kwin_")
            with os.fdopen(fd, "w") as f:
                f.write(script_content)
            self._kwin_script_path = path

        try:
            # 2. Re-write the script content with the new marker
            # We rewrite it quickly so `loadScript` grabs the fresh marker
            script_content = f"""
            var active = workspace.activeWindow;
            if (active) {{
                print("{marker_id}|" + active.caption + "|||" + active.resourceClass);
            }}
            """
            with open(self._kwin_script_path, "w") as f:
                f.write(script_content)

            # 3. Load script into KWin (returns integer script DBus ID)
            # We first unload it just in case
            subprocess.run(
                ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", self._kwin_script_id],
                capture_output=True, check=False, timeout=1
            )
            res_load = subprocess.run(
                ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", self._kwin_script_path, self._kwin_script_id],
                capture_output=True, text=True, timeout=1, check=False
            )
            
            if res_load.returncode != 0:
                logger.debug("Failed to load KWin script via qdbus6: %s", res_load.stderr)
                return None
                
            script_num = res_load.stdout.strip()
            if not script_num.isdigit():
                return None

            # 4. Trigger script run
            subprocess.run(
                ["qdbus6", "org.kde.KWin", f"/Scripting/Script{script_num}", "org.kde.kwin.Script.run"],
                capture_output=True, check=False, timeout=1
            )
            time.sleep(0.05)  # Small grace period for KWin to write to journal

            # 5. Extract output from journal
            res_journal = subprocess.run(
                ["journalctl", "--user", "-n", "20", "--no-pager"],
                capture_output=True, text=True, timeout=1, check=False
            )

            # 6. Parse log for our marker
            for line in reversed(res_journal.stdout.splitlines()):
                if marker_id in line and "|||" in line:
                    # Line format: ... js: [marker_id]|[caption]|||[class]
                    payload = line.split(marker_id + "|")[-1]
                    parts = payload.split("|||")
                    if len(parts) == 2:
                        title, class_raw = parts
                        # Clean Up DBus unloading to not leak memory
                        subprocess.run(
                            ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", self._kwin_script_id],
                            capture_output=True, check=False, timeout=1
                        )
                        class_nm = self.normalize_class_name(class_raw, title)
                        return WindowInfo(
                            title=title, class_=class_nm, raw=payload,
                            method="qdbus_kwin", window_id=""
                        )

            return None
            
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.debug("qdbus fallback failed: %s", exc)
            return None
