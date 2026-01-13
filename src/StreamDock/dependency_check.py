"""
Dependency checking and reporting for StreamDock.
Checks for both system binaries and Python packages.
"""
import importlib.util
import logging
import shutil
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class Dependency:
    name: str
    category: str  # "Required", "Optional", "System Tool"
    description: str
    display_name: Optional[str] = None
    installed: bool = False
    version: Optional[str] = None
    feature: Optional[str] = None

class DependencyChecker:
    """Checks for system and Python dependencies."""

    def __init__(self):
        self.system_tools = [
            Dependency("xdotool", "System Tool", "X11 key emulation and window manipulation", feature="X11 support"),
            Dependency("kdotool", "System Tool", "Wayland (KDE) window manipulation", feature="Wayland/KDE support"),
            Dependency("wmctrl", "System Tool", "Legacy window management", feature="Fallback window focus"),
            Dependency("pgrep", "System Tool", "Process detection", feature="Auto-launch detection"),
            Dependency("qdbus", "System Tool", "Qt D-Bus communication", feature="KDE integration"),
            Dependency("qdbus6", "System Tool", "Qt6 D-Bus communication", feature="Plasma 6 support"),
            Dependency("dbus-send", "System Tool", "Generic D-Bus communication", feature="Media controls"),
            Dependency("pactl", "System Tool", "PulseAudio/PipeWire volume control", feature="Volume actions"),
            Dependency("journalctl", "System Tool", "Systemd journal access", feature="KWin script logging"),
        ]

        self.python_packages = [
            Dependency("PIL", "Required", "Image processing", display_name="Pillow"),
            Dependency("yaml", "Required", "YAML configuration parsing", display_name="PyYAML"),
            Dependency("cairosvg", "Required", "SVG image support"),
            Dependency("pyudev", "Required", "USB device monitoring"),
            Dependency("PyQt6", "Required", "GUI and event loop"),
            Dependency("dbus", "Optional", "D-Bus python bindings", feature="Lock monitor (KDE)"),
            Dependency("gi", "Optional", "GObject introspection", feature="Lock monitor (GNOME)"),
        ]

    def _check_system_tool(self, dep: Dependency) -> bool:
        """Check if a system tool is in PATH."""
        return shutil.which(dep.name) is not None

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
            except:
                pass
                
            return True
        except (ImportError, TypeError):
            return False

    def run_check(self) -> List[Dependency]:
        """Run all checks and return the results."""
        results = []
        
        for dep in self.python_packages:
            dep.installed = self._check_python_package(dep)
            results.append(dep)
            
        for dep in self.system_tools:
            dep.installed = self._check_system_tool(dep)
            results.append(dep)
            
        return results

    def print_report(self):
        """Print a formatted report to the console."""
        results = self.run_check()
        
        print("\n" + "="*60)
        print(" StreamDock Dependency Check ".center(60, "="))
        print("="*60 + "\n")

        # Python Packages
        print("--- Python Packages ---")
        for dep in results:
            if dep.category != "System Tool":
                status = "✅ INSTALLED" if dep.installed else "❌ MISSING"
                version_str = f" (v{dep.version})" if dep.version and dep.version != 'unknown' else ""
                name_to_show = dep.display_name or dep.name
                print(f"{status.ljust(12)} {name_to_show.ljust(15)} {dep.description.ljust(20)}{version_str}")
                if not dep.installed and dep.feature:
                    print(f"             └─ Required for: {dep.feature}")

        # System Tools
        print("\n--- System Tools ---")
        for dep in results:
            if dep.category == "System Tool":
                status = "✅ FOUND" if dep.installed else "⚠️  MISSING"
                print(f"{status.ljust(12)} {dep.name.ljust(15)} {dep.description}")
                if not dep.installed and dep.feature:
                    print(f"             └─ Impact: {dep.feature} will be disabled")

        print("\n" + "="*60)
        
        # Installation Hints
        missing_required = [d for d in results if not d.installed and d.category == "Required"]
        missing_optional = [d for d in results if not d.installed and (d.category == "Optional" or d.category == "System Tool")]
        
        if missing_required:
            print("\n❌ CRITICAL: Missing required Python packages!")
            print("Run: pip install -r requirements.txt")
        
        if missing_optional:
            print("\n💡 Installation Hints:")
            # Simple distro detection (very basic)
            print("  Ubuntu/Debian: sudo apt install xdotool wmctrl dbus-x11 libhidapi-libusb0")
            print("  Arch Linux:    sudo pacman -S xdotool kdotool wmctrl hidapi")
            print("  Fedora:        sudo dnf install xdotool wmctrl hidapi")
            
        print("\n" + "="*60 + "\n")

    def has_critical_failures(self) -> bool:
        """Check if any required dependencies are missing."""
        results = self.run_check()
        return any(not dep.installed for dep in results if dep.category == "Required")

    def get_summary(self) -> str:
        """Return a concise summary string of the check."""
        results = self.run_check()
        python_ok = all(d.installed for d in results if d.category == "Required")
        sys_tools = [d for d in results if d.category == "System Tool"]
        found_tools = sum(1 for d in sys_tools if d.installed)
        
        status = "OK" if python_ok else "CRITICAL MISSING"
        return f"Dependency Status: {status} (Python: {'OK' if python_ok else 'Missing Required'}, System Tools: {found_tools}/{len(sys_tools)} found)"

if __name__ == "__main__":
    checker = DependencyChecker()
    checker.print_report()
