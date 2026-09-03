"""
Test-suite wide setup.

Must run before anything imports Qt: the GUI tests instantiate real widgets,
and without an offscreen platform plugin they need a display server and fail
in CI or over SSH.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")


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
