"""
Test-suite wide setup.

Must run before anything imports Qt: the GUI tests instantiate real widgets,
and without an offscreen platform plugin they need a display server and fail
in CI or over SSH.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")
