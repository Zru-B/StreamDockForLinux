"""
Test-suite wide setup.

Must run before anything imports Qt: the GUI tests instantiate real widgets,
and without an offscreen platform plugin they need a display server and fail
in CI or over SSH.
"""

import atexit
import os
import shutil
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

# Point every configuration read at a directory of the run's own, before Qt
# has a chance to resolve one. Two things live there: the QSettings file the
# application remembers preferences in, which a test run must not rewrite, and
# the kdeglobals the theme reads its colours from, which would otherwise make
# the palettes depend on whose desktop the suite is running on.
_CONFIG_HOME = tempfile.mkdtemp(prefix="streamdock-tests-")
os.environ["XDG_CONFIG_HOME"] = _CONFIG_HOME
atexit.register(shutil.rmtree, _CONFIG_HOME, ignore_errors=True)


import pytest

CONFIG_FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")


@pytest.fixture
def config_fixture():
    """
    Resolve a checked-in configuration fixture by name.

    Usage: `config_fixture("multiple_defaults")` -> path to
    tests/configs/multiple_defaults.yml
    """
    def resolve(name: str) -> str:
        path = os.path.join(CONFIG_FIXTURE_DIR, f"{name}.yml")
        assert os.path.exists(path), f"missing fixture: {path}"
        return path

    return resolve
