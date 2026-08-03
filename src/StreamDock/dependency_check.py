"""
Dependency checking and reporting for StreamDock.
Checks for both system binaries and Python packages.
"""
import copy
import ctypes
import importlib
import importlib.util
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

@dataclass
class Dependency:
    name: str
    category: str  # "Required", "Optional", "System Tool"
    description: str
    display_name: Optional[str] = None
    check_type: str = "python"  # "python", "binary", "shared_lib"
    package_names: Optional[Dict[str, str]] = None
    installed: bool = False
    version: Optional[str] = None
    feature: Optional[str] = None
    aliases: Optional[List[str]] = None  # alternative binary names to probe

class DependencyChecker:
    """Checks for system and Python dependencies."""

    def __init__(self):
        self.system_tools_templates = [
            Dependency(
                "xdotool", "System Tool", "X11 key emulation and window manipulation",
                check_type="binary", feature="X11 support",
                package_names={"debian": "xdotool", "arch": "xdotool", "fedora": "xdotool"}
            ),
            Dependency(
                "kdotool", "System Tool", "Wayland (KDE) window manipulation",
                check_type="binary", feature="Wayland/KDE support",
                package_names=None
            ),
            Dependency(
                "wmctrl", "System Tool", "Legacy window management",
                check_type="binary", feature="Fallback window focus",
                package_names={"debian": "wmctrl", "arch": "wmctrl", "fedora": "wmctrl"}
            ),
            Dependency(
                "pgrep", "System Tool", "Process detection",
                check_type="binary", feature="Auto-launch detection",
                package_names={"debian": "procps", "arch": "procps-ng", "fedora": "procps-ng"}
            ),
            Dependency(
                "qdbus", "System Tool", "Qt D-Bus communication",
                check_type="binary", feature="KDE integration",
                package_names={"debian": "qttools5-dev-tools", "arch": "qt5-tools", "fedora": "qt5-qttools"}
            ),
            Dependency(
                "qdbus6", "System Tool", "Qt6 D-Bus communication",
                check_type="binary", feature="Plasma 6 support",
                package_names={"debian": "qdbus-qt6", "arch": "qt6-tools", "fedora": "qt6-qttools"},
                aliases=["qdbus"],  # qdbus-qt6 on Ubuntu installs as 'qdbus' under /usr/lib/qt6/bin
            ),
            Dependency(
                "dbus-send", "System Tool", "Generic D-Bus communication",
                check_type="binary", feature="Media controls",
                package_names={"debian": "dbus", "arch": "dbus", "fedora": "dbus"}
            ),
            Dependency(
                "pactl", "System Tool", "PulseAudio/PipeWire volume control",
                check_type="binary", feature="Volume actions",
                package_names={"debian": "pulseaudio-utils", "arch": "libpulse", "fedora": "pulseaudio-utils"}
            ),
            Dependency(
                "journalctl", "System Tool", "Systemd journal access",
                check_type="binary", feature="KWin script logging",
                package_names={"debian": "systemd", "arch": "systemd", "fedora": "systemd"}
            ),
        ]

        self.system_lib_templates = [
            Dependency(
                "libhidapi-libusb", "Required", "HID USB backend shared library",
                check_type="shared_lib", feature="USB communication with StreamDock device",
                package_names={"debian": "libhidapi-libusb0", "arch": "hidapi", "fedora": "hidapi"}
            ),
        ]

        self.python_packages_templates = [
            Dependency("PIL", "Required", "Image processing", display_name="Pillow", check_type="python"),
            Dependency("yaml", "Required", "YAML configuration parsing", display_name="PyYAML", check_type="python"),
            Dependency("cairosvg", "Required", "SVG image support", check_type="python"),
            Dependency("pyudev", "Required", "USB device monitoring", check_type="python"),
            Dependency("PyQt6", "Required", "GUI and event loop", check_type="python"),
            Dependency("dbus", "Optional", "D-Bus python bindings", check_type="python", feature="Lock monitor (KDE)"),
            Dependency("gi", "Optional", "GObject introspection", check_type="python", feature="Lock monitor (GNOME)"),
        ]

        self._hidapi_candidate_libs = [
            "libhidapi-libusb.so.0",
            "libhidapi-libusb.so",
            "libhidapi.so.0",
            "libhidapi.so",
        ]

        self._last_results: Optional[List[Dependency]] = None

    # Some distros install Qt6 tools under a version-specific prefix not in $PATH.
    _BINARY_FALLBACK_DIRS = [
        "/usr/lib/qt6/bin",
        "/usr/lib/x86_64-linux-gnu/qt6/bin",
    ]

    def _check_system_tool(self, dep: Dependency) -> bool:
        """Check if a system tool is in PATH or a known non-PATH Qt prefix."""
        candidates = [dep.name] + (dep.aliases or [])
        for name in candidates:
            if shutil.which(name) is not None:
                return True
            for directory in self._BINARY_FALLBACK_DIRS:
                if os.path.isfile(os.path.join(directory, name)):
                    return True
        return False

    def _check_shared_library(self, dep: Dependency) -> Tuple[bool, Optional[str]]:
        """Check if a shared library can be loaded."""
        candidates = self._hidapi_candidate_libs if dep.name == "libhidapi-libusb" else [dep.name]
        for candidate in candidates:
            try:
                ctypes.CDLL(candidate)
                return True, candidate
            except OSError:
                continue
        return False, None

    def _check_python_package(self, dep: Dependency) -> bool:
        """Check if a Python package is installed."""
        package_name = dep.name
        try:
            spec = importlib.util.find_spec(package_name)
            if spec is None:
                return False

            # Try to get version
            try:
                module = importlib.import_module(package_name)
                # Some packages might not have __version__ or it might be in metadata
                dep.version = getattr(module, '__version__', 'unknown')
            except Exception:  # pylint: disable=broad-exception-caught
                pass

            return True
        except (ImportError, TypeError):
            return False

    def _detect_distro_family(self) -> str:
        """Detect Linux distro family for package hint generation."""
        os_release_path = "/etc/os-release"
        if not os.path.exists(os_release_path):
            return "unknown"

        try:
            values: Dict[str, str] = {}
            with open(os_release_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if "=" not in line or line.startswith("#"):
                        continue
                    key, value = line.split("=", 1)
                    values[key.strip().lower()] = value.strip().strip('"')

            distro_id = values.get("id", "").lower()
            distro_like = values.get("id_like", "").lower()
            normalized = f"{distro_id} {distro_like}"

            if any(token in normalized for token in ["ubuntu", "debian"]):
                return "debian"
            if any(token in normalized for token in ["arch", "manjaro"]):
                return "arch"
            if any(token in normalized for token in ["fedora", "rhel", "centos"]):
                return "fedora"
        except OSError:
            return "unknown"

        return "unknown"

    def _get_package_manager(self, distro_family: str) -> Optional[str]:
        if distro_family == "debian":
            return "apt"
        if distro_family == "arch":
            return "pacman"
        if distro_family == "fedora":
            return "dnf"
        return None

    def _clone_templates(self) -> Tuple[List[Dependency], List[Dependency], List[Dependency]]:
        """Clone dependency templates to avoid mutating baseline definitions."""
        return (
            copy.deepcopy(self.python_packages_templates),
            copy.deepcopy(self.system_lib_templates),
            copy.deepcopy(self.system_tools_templates),
        )

    def _build_system_install_hint(self, missing_system: List[Dependency], distro_family: str) -> Optional[str]:
        package_manager = self._get_package_manager(distro_family)
        if package_manager is None:
            return None

        packages: List[str] = []
        for dep in missing_system:
            if dep.package_names is None:
                continue
            package_name = dep.package_names.get(distro_family)
            if package_name and package_name not in packages:
                packages.append(package_name)

        if not packages:
            return None

        if package_manager == "apt":
            return f"sudo apt update && sudo apt install {' '.join(packages)}"
        if package_manager == "pacman":
            return f"sudo pacman -S {' '.join(packages)}"
        if package_manager == "dnf":
            return f"sudo dnf install {' '.join(packages)}"

        return None

    def _print_install_hints(self, results: List[Dependency], distro_family: str) -> None:
        missing_required_python = [
            d for d in results if not d.installed and d.category == "Required" and d.check_type == "python"
        ]
        missing_optional_python = [
            d for d in results if not d.installed and d.category == "Optional" and d.check_type == "python"
        ]
        missing_system = [
            d for d in results if not d.installed and d.check_type in {"binary", "shared_lib"}
        ]

        print("\n--- Installation Suggestions ---")

        if missing_required_python:
            print("Required Python packages missing:")
            print("  pip install -r requirements.txt")

        if missing_optional_python:
            print("Optional Python feature packages missing:")
            print("  pip install dbus-python PyGObject")

        if missing_system:
            system_hint = self._build_system_install_hint(missing_system, distro_family)
            if system_hint:
                distro_label = {
                    "debian": "Ubuntu/Debian",
                    "arch": "Arch Linux",
                    "fedora": "Fedora",
                }.get(distro_family, distro_family)
                print(f"{distro_label} system packages:")
                print(f"  {system_hint}")
            else:
                print("Install the missing system tools/libraries using your distro package manager.")

    def run_check(self) -> List[Dependency]:
        """Run all checks and return the results."""
        results = []
        python_packages, system_libs, system_tools = self._clone_templates()

        for dep in python_packages:
            dep.installed = self._check_python_package(dep)
            results.append(dep)

        for dep in system_libs:
            dep.installed, dep.version = self._check_shared_library(dep)
            results.append(dep)

        for dep in system_tools:
            dep.installed = self._check_system_tool(dep)
            results.append(dep)

        self._last_results = results
        return results

    def print_report(self):
        """Print a formatted report to the console."""
        results = self.run_check()
        distro_family = self._detect_distro_family()

        print("\n" + "="*60)
        print(" StreamDock Dependency Check ".center(60, "="))
        print("="*60 + "\n")

        # Python Packages
        print("--- Python Packages ---")
        for dep in results:
            if dep.check_type == "python":
                status = "✅ INSTALLED" if dep.installed else "❌ MISSING"
                version_str = f" (v{dep.version})" if dep.version and dep.version != 'unknown' else ""
                name_to_show = dep.display_name or dep.name
                print(f"{status.ljust(12)} {name_to_show.ljust(15)} {dep.description.ljust(20)}{version_str}")
                if not dep.installed and dep.feature:
                    print(f"             └─ Required for: {dep.feature}")

        print("\n--- System Libraries ---")
        for dep in results:
            if dep.check_type == "shared_lib":
                status = "✅ FOUND" if dep.installed else "❌ MISSING"
                loaded_as = f" ({dep.version})" if dep.version else ""
                print(f"{status.ljust(12)} {dep.name.ljust(15)} {dep.description}{loaded_as}")
                if not dep.installed and dep.feature:
                    print(f"             └─ Required for: {dep.feature}")

        # System Tools
        print("\n--- System Tools ---")
        for dep in results:
            if dep.check_type == "binary":
                status = "✅ FOUND" if dep.installed else "⚠️  MISSING"
                print(f"{status.ljust(12)} {dep.name.ljust(15)} {dep.description}")
                if not dep.installed and dep.feature:
                    print(f"             └─ Impact: {dep.feature} will be disabled")

        print("\n" + "="*60)

        missing_required = [d for d in results if not d.installed and d.category == "Required"]
        if missing_required:
            print("\n❌ CRITICAL: Missing required dependencies detected.")

        self._print_install_hints(results, distro_family)

        print("\n" + "="*60 + "\n")

    def has_critical_failures(self) -> bool:
        """Check if any required dependencies are missing."""
        results = self._last_results if self._last_results is not None else self.run_check()
        return any(not dep.installed for dep in results if dep.category == "Required")

    def get_summary(self) -> str:
        """Return a concise summary string of the check."""
        results = self._last_results if self._last_results is not None else self.run_check()
        python_ok = all(d.installed for d in results if d.category == "Required" and d.check_type == "python")
        shared_lib_ok = all(d.installed for d in results if d.category == "Required" and d.check_type == "shared_lib")
        sys_tools = [d for d in results if d.check_type == "binary"]
        found_tools = sum(1 for d in sys_tools if d.installed)

        status = "OK" if python_ok and shared_lib_ok else "CRITICAL MISSING"
        return (
            f"Dependency Status: {status} "
            f"(Python: {'OK' if python_ok else 'Missing Required'}, "
            f"HID library: {'OK' if shared_lib_ok else 'Missing'}, "
            f"System Tools: {found_tools}/{len(sys_tools)} found)"
        )

if __name__ == "__main__":
    checker = DependencyChecker()
    checker.print_report()
