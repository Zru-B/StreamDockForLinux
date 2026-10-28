"""
Linux implementation of WindowInterface.

Uses kdotool (preferred on KDE Wayland) and xdotool (X11 fallback) to
query and control windows.  All subprocess commands are non-interactive —
the haircross bug (requiring mouse input) cannot occur here.
"""

import atexit
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
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

# After a kdotool timeout, stop calling it for this long, then probe again.
KDOTOOL_RETRY_SECONDS = 60.0

# kdotool's error when KWin has no active window (e.g. on the lock screen).
_KDOTOOL_NULL_WINDOW = "of null"

# The fixed lines `getwindowgeometry --shell` prints before the chained name/class.
_XDOTOOL_SHELL_KEYS = ("WINDOW", "X", "Y", "WIDTH", "HEIGHT", "SCREEN")


def _qdbus_env() -> dict:
    """qdbus6 prints a multi-line locale warning on every call unless LC_ALL is set."""
    return {**os.environ, "LC_ALL": "C.UTF-8"}


# KWin script files still on disk; normally each call removes its own, this
# covers an interpreter exit in the middle of a call.
_live_kwin_scripts: set = set()


def _remove_leftover_kwin_scripts() -> None:
    for path in list(_live_kwin_scripts):
        try:
            os.remove(path)
        except OSError:
            pass
    _live_kwin_scripts.clear()


atexit.register(_remove_leftover_kwin_scripts)


def _kwin_script_dir() -> str:
    """$XDG_RUNTIME_DIR is private to the user; /tmp is only the fallback."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir):
        return runtime_dir
    return tempfile.gettempdir()


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
        self._kdotool_retry_at: Optional[float] = None
        self._xdotool_available: Optional[bool] = None
        self._qdbus_available: Optional[bool] = None

    # ------------------------------------------------------------------ #
    # Public helpers                                                       #
    # ------------------------------------------------------------------ #

    def reset_tool_cache(self) -> None:
        """Clear cached tool-availability flags (useful in tests)."""
        self._kdotool_available = None
        self._kdotool_retry_at = None
        self._xdotool_available = None

    def is_kdotool_available(self) -> bool:
        """Return ``True`` if kdotool is installed and functional."""
        if self._kdotool_retry_at is not None and time.monotonic() >= self._kdotool_retry_at:
            self._kdotool_available = None
            self._kdotool_retry_at = None
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
            self._kdotool_available = (
                result.returncode == 0 or self._is_kdotool_null_window(result)
            )
        except subprocess.TimeoutExpired:
            self._suspend_kdotool("probe")
        except Exception:
            self._kdotool_available = False
        return self._kdotool_available

    def _suspend_kdotool(self, what: str) -> None:
        """
        Stop using kdotool after a timeout, but only for a while: a busy KWin
        stalls it transiently, and giving up for the session would push every
        later poll onto the qdbus path, which writes captions to the journal.
        """
        logger.warning("kdotool %s timed out — retrying it in %.0f s", what, KDOTOOL_RETRY_SECONDS)
        self._kdotool_available = False
        self._kdotool_retry_at = time.monotonic() + KDOTOOL_RETRY_SECONDS

    def _qdbus_fallback_allowed(self) -> bool:
        """The KWin-script fallback is for a kdotool that does not work, not one backing off."""
        return (
            bool(os.environ.get("WAYLAND_DISPLAY"))
            and self._kdotool_retry_at is None
            and self.is_qdbus_kwin_available()
        )

    @staticmethod
    def _is_kdotool_null_window(result) -> bool:
        return _KDOTOOL_NULL_WINDOW in f"{result.stderr or ''}{result.stdout or ''}"

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
                env=_qdbus_env(),
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
        and kdotool does not work at all (KWin 6.3 panic). Falls back to xdotool (X11/XWayland).
        Both explicit tool paths use ``getactivewindow`` — no mouse interaction required.

        When kdotool works, a failed query is not handed to the fallbacks: KWin
        having no active window (lock screen) is a real answer, and the qdbus
        path would write a caption into the journal on every poll.
        """
        try:
            if self.is_kdotool_available():
                return self._kdotool_get_active_window()

            # If in Wayland, prefer qdbus6 KWin scripting fallback over xdotool
            if self._qdbus_fallback_allowed():
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
                    
            if self._qdbus_fallback_allowed():
                wid = self._qdbus_search_by_class(class_name)
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
                try:
                    r = subprocess.run(
                        ["kdotool", "search", "--name", regex_pattern],
                        capture_output=True, text=True, timeout=1, check=False,
                    )
                    if r.returncode == 0:
                        lines = r.stdout.strip().splitlines()
                        if lines:
                            return lines[0].strip()
                except subprocess.TimeoutExpired:
                    self._suspend_kdotool("search")

            # Fallback to qdbus scripting if Wayland native and kdotool is busted
            if self._qdbus_fallback_allowed():
                wid = self._qdbus_search_by_name(name)
                if wid:
                    return wid

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
                
            if self._qdbus_fallback_allowed():
                if self._qdbus_activate_window(window_id):
                    return True

            if self.is_xdotool_available() and self._xdotool_activate(window_id):
                return True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error activating window: %s", exc, exc_info=True)
        return False

    def activate_tray_app(self, app_name: str) -> bool:
        """Attempt to activate a minimized-to-tray application directly via DBus."""
        try:
            import re
            r = subprocess.run(["busctl", "--user", "list", "--no-pager"], capture_output=True, text=True, timeout=1)
            if r.returncode != 0:
                return False
                
            regex = re.compile(self._to_case_insensitive_regex(app_name))
            svc_to_activate = None
            
            for line in r.stdout.splitlines():
                if "org.kde.StatusNotifierItem" in line:
                    svc = line.split()[0]
                    if regex.search(svc):
                        svc_to_activate = svc
                        break
                        
            if svc_to_activate:
                activate_r = subprocess.run(
                    ["dbus-send", "--session", "--type=method_call", f"--dest={svc_to_activate}", 
                     "/StatusNotifierItem", "org.kde.StatusNotifierItem.Activate", "int32:0", "int32:0"],
                    capture_output=True, timeout=1
                )
                return activate_r.returncode == 0
                
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.debug("Tray DBus activation failed for '%s': %s", app_name, exc)
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
        """
        One chained kdotool call per poll; it prints the id, the title and the
        class on separate lines (getactivewindow itself prints nothing when chained).
        """
        try:
            r = subprocess.run(
                ["kdotool", "getactivewindow", "getwindowid", "getwindowname", "getwindowclassname"],
                capture_output=True, text=True, timeout=1, check=False,
            )
        except subprocess.TimeoutExpired:
            self._suspend_kdotool("getactivewindow")
            return None
        if r.returncode != 0:
            if self._is_kdotool_null_window(r):
                logger.debug("kdotool: no active window")
            else:
                logger.debug("kdotool getactivewindow failed: %s", (r.stderr or "").strip())
            return None
        lines = r.stdout.rstrip("\n").split("\n")
        if len(lines) < 3 or not lines[0].strip():
            return None
        window_id = lines[0].strip()
        class_raw = lines[-1].strip()
        title = "\n".join(lines[1:-1]).strip()
        if class_raw:
            class_ = self.normalize_class_name(class_raw, title)
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
        try:
            r = subprocess.run(
                ["kdotool", "search", "--class", regex_pattern],
                capture_output=True, text=True, timeout=2, check=False,
            )
        except subprocess.TimeoutExpired:
            self._suspend_kdotool("search")
            return None
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("\n")[0]
        return None

    def _kdotool_activate(self, window_id: str) -> bool:
        try:
            r = subprocess.run(
                ["kdotool", "windowactivate", window_id],
                capture_output=True, text=True, timeout=2, check=False,
            )
        except subprocess.TimeoutExpired:
            self._suspend_kdotool("windowactivate")
            return False
        return r.returncode == 0

    # ------------------------------------------------------------------ #
    # Private subprocess helpers — xdotool                                #
    # ------------------------------------------------------------------ #

    def _xdotool_get_active_window(self) -> Optional[WindowInfo]:
        """
        One chained xdotool call per poll. xdotool has no getwindowid and a chained
        getactivewindow prints nothing, so the id comes from the WINDOW= line of
        ``getwindowgeometry --shell``; the title and class follow on their own lines.
        """
        r = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowgeometry", "--shell",
             "getwindowname", "getwindowclassname"],
            capture_output=True, text=True, timeout=1, check=False,
        )
        if r.returncode != 0:
            return None
        lines = r.stdout.rstrip("\n").split("\n")
        shell = {}
        while lines and "=" in lines[0]:
            key, _, value = lines[0].partition("=")
            if key not in _XDOTOOL_SHELL_KEYS or key in shell:
                break
            shell[key] = value
            lines.pop(0)
        window_id = shell.get("WINDOW", "").strip()
        if not window_id:
            return None
        class_raw = lines.pop().strip() if len(lines) > 1 else ""
        if class_raw == "(null)":
            class_raw = ""
        title = "\n".join(lines).strip()
        if class_raw:
            class_ = self.normalize_class_name(class_raw, title)
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
        marker_id = uuid.uuid4().hex
        script = f"""
        var active = workspace.activeWindow;
        if (active) {{
            print("{marker_id}|" + active.caption + "|||" + active.resourceClass);
        }}
        """
        try:
            results = self._qdbus_execute_script(script, marker_id)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.debug("qdbus fallback failed: %s", exc)
            return None
        if not results:
            return None

        payload = results[-1]
        # A caption may itself contain the separator; the class never does.
        title, class_raw = payload.rsplit("|||", 1)
        class_nm = self.normalize_class_name(class_raw, title)
        return WindowInfo(
            title=title, class_=class_nm, raw=payload,
            method="qdbus_kwin", window_id=""
        )

    def _qdbus_execute_script(self, script_content: str, marker_id: str) -> Optional[List[str]]:
        """
        Load, run and unload a one-shot KWin script, returning what it printed
        after ``marker_id|`` (KWin sends script output to the journal).

        Each call gets its own file and plugin name, so concurrent calls from
        the poll thread and an action thread cannot unload each other's script.
        """
        script_id = f"streamdock_{marker_id}"
        fd, path = tempfile.mkstemp(suffix=".js", prefix="streamdock_kwin_", dir=_kwin_script_dir())
        _live_kwin_scripts.add(path)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(script_content)

            # Whole seconds: the marker, not the window, keeps old lines out.
            since = int(time.time())
            res_load = subprocess.run(
                ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", path, script_id],
                capture_output=True, text=True, timeout=1, check=False,
                env=_qdbus_env(),
            )
            if res_load.returncode != 0:
                logger.debug("Failed to load KWin script via qdbus6: %s", res_load.stderr)
                return None

            script_num = res_load.stdout.strip()
            if not script_num.isdigit():
                return None

            subprocess.run(
                ["qdbus6", "org.kde.KWin", f"/Scripting/Script{script_num}", "org.kde.kwin.Script.run"],
                capture_output=True, check=False, timeout=1,
                env=_qdbus_env(),
            )
            time.sleep(0.1)  # Grace period for KWin to write to the journal

            res_journal = subprocess.run(
                ["journalctl", "--user", f"--since=@{since}", "-o", "cat", "--no-pager"],
                capture_output=True, text=True, timeout=1, check=False
            )

            prefix = marker_id + "|"
            return [
                line.split(prefix, 1)[1]
                for line in res_journal.stdout.splitlines()
                if prefix in line and "|||" in line
            ]
        finally:
            subprocess.run(
                ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", script_id],
                capture_output=True, check=False, timeout=1,
                env=_qdbus_env(),
            )
            _live_kwin_scripts.discard(path)
            try:
                os.remove(path)
            except OSError:
                pass

    def _qdbus_search_by_class(self, class_name: str) -> Optional[str]:
        import re
        marker_id = uuid.uuid4().hex
        script = f"""
        var wins = workspace.windowList();
        for (var i = 0; i < wins.length; i++) {{
            var w = wins[i];
            if (w.resourceClass) {{
                print("{marker_id}|" + w.internalId + "|||" + w.resourceClass);
            }}
        }}
        """
        results = self._qdbus_execute_script(script, marker_id)
        if not results:
            return None
            
        regex = re.compile(self._to_case_insensitive_regex(class_name))
        for res in results:
            parts = res.split("|||", 1)
            if len(parts) == 2:
                wid, w_class = parts
                if regex.search(w_class):
                    return wid
        return None
        
    def _qdbus_search_by_name(self, name: str) -> Optional[str]:
        import re
        marker_id = uuid.uuid4().hex
        script = f"""
        var wins = workspace.windowList();
        for (var i = 0; i < wins.length; i++) {{
            var w = wins[i];
            if (w.caption) {{
                print("{marker_id}|" + w.internalId + "|||" + w.caption);
            }}
        }}
        """
        results = self._qdbus_execute_script(script, marker_id)
        if not results:
            return None
            
        regex = re.compile(self._to_case_insensitive_regex(name))
        for res in results:
            # internalId never contains the separator; a caption may.
            parts = res.split("|||", 1)
            if len(parts) == 2:
                wid, caption = parts
                if regex.search(caption):
                    return wid
        return None

    def _qdbus_activate_window(self, window_id: str) -> bool:
        marker_id = uuid.uuid4().hex
        script = f"""
        var wins = workspace.windowList();
        for (var i = 0; i < wins.length; i++) {{
            if (wins[i].internalId == "{window_id}") {{
                workspace.activeWindow = wins[i];
                print("{marker_id}|success|||OK");
                break;
            }}
        }}
        """
        results = self._qdbus_execute_script(script, marker_id)
        return bool(results)
