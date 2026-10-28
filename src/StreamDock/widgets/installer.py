"""
Install, remove and re-approve third-party widgets.

Each widget gets a folder ``<install_dir>/<id>/`` holding ``widget.py``, any
files it shipped with, and ``manifest.json``: the validated manifest, the
capabilities the user agreed to, and a sha256 of every file. The registry
refuses to run a widget whose files no longer match those hashes, so editing
an installed widget needs a fresh approval.
"""

import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from StreamDock.widgets.registry import (
    ENTRY_FILE, MANIFEST_FILE, PYCACHE, WidgetRegistry, WidgetSpec, file_digests,
)
from StreamDock.widgets.validator import ValidationReport, dry_run_widget, validate_widget


class InstallError(Exception):
    pass


def _copy_filter(source: str):
    """
    What copytree leaves out of a staged widget.

    The approval record is dropped only at the top, where the registry writes
    its own; a data/manifest.json the widget ships is one of its files.
    """
    skip_everywhere = shutil.ignore_patterns(PYCACHE, '.*')
    top = os.path.abspath(source)

    def ignore(folder, names):
        skipped = set(skip_everywhere(folder, names))
        if os.path.abspath(folder) == top and MANIFEST_FILE in names:
            skipped.add(MANIFEST_FILE)
        return skipped
    return ignore


@dataclass
class StagedWidget:
    """
    A private copy of a widget, and what checking it found.

    Everything after ``stage`` - consent, the test run, installing - works on
    this copy, so the files the user agreed to are the files that run, however
    the source changes meanwhile. ``files`` are its hashes as first copied.
    """

    folder: str
    report: ValidationReport
    files: Dict[str, str] = field(default_factory=dict)


class WidgetInstaller:
    def __init__(self, registry: WidgetRegistry):
        self._registry = registry

    @property
    def install_dir(self) -> str:
        return self._registry.install_dir

    def installed(self, widget_id: str) -> Optional[WidgetSpec]:
        spec = self._registry.get(widget_id)
        return spec if spec is not None and not spec.builtin else None

    def stage(self, source: str) -> StagedWidget:
        """
        Copy ``source`` somewhere private and run the static checks on the copy.

        Nothing of the widget runs yet; call ``test_run`` once the user has
        agreed. The caller must ``discard`` the result unless it was installed.
        """
        os.makedirs(self.install_dir, exist_ok=True)
        # Under install_dir so installing is a rename; the registry skips dot-folders.
        staging = tempfile.mkdtemp(prefix='.staging-', dir=self.install_dir)
        try:
            if os.path.isdir(source):
                # Links are copied as links, for the static pass to refuse.
                shutil.copytree(source, staging, symlinks=True, dirs_exist_ok=True,
                                ignore=_copy_filter(source))
            else:
                shutil.copyfile(source, os.path.join(staging, ENTRY_FILE))
            files = file_digests(staging)
            report = validate_widget(staging, reserved_ids=self._registry.builtin_ids(), dry_run=False)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return StagedWidget(staging, report, files)

    def stage_installed(self, widget_id: str) -> StagedWidget:
        """Stage an installed widget's current files, to approve them again."""
        spec = self.installed(widget_id)
        if spec is None:
            raise InstallError(f"'{widget_id}' is not an installed widget")
        staged = self.stage(spec.folder)
        if staged.report.ok and staged.report.manifest['id'] != widget_id:
            staged.report.errors.append(f"the files now declare id '{staged.report.manifest['id']}'")
        return staged

    @staticmethod
    def test_run(staged: StagedWidget) -> None:
        """Run the staged copy once; failures land in ``staged.report``."""
        dry_run_widget(staged.report)
        if staged.report.ok and file_digests(staged.folder) != staged.files:
            staged.report.errors.append('the widget changed its own files during the test run')

    @staticmethod
    def discard(staged: StagedWidget) -> None:
        shutil.rmtree(staged.folder, ignore_errors=True)

    def install(self, staged: StagedWidget) -> WidgetSpec:
        """
        Move a staged, test-run widget into place, replacing an older copy of the same id.

        The user's consent to its capabilities is recorded with the files.
        """
        self._check_unchanged(staged)
        widget_id = staged.report.manifest['id']
        self._write_record(staged.folder, staged)
        self._put_in_place(staged.folder, widget_id)
        self._registry.refresh()
        return self._registry.get(widget_id)

    def approve(self, widget_id: str, staged: StagedWidget) -> WidgetSpec:
        """Record consent to the files of an installed widget that ``staged`` copied."""
        spec = self.installed(widget_id)
        if spec is None or not staged.report.ok or staged.report.manifest['id'] != widget_id:
            raise InstallError('nothing to approve')
        self._check_unchanged(staged)
        # Stale bytecode from older versions of the app is dropped, not counted as an edit.
        live = {path: digest for path, digest in file_digests(spec.folder).items()
                if PYCACHE not in path.split(os.sep)}
        if live != staged.files:
            raise InstallError('the files changed while they were being checked; approve them again')
        # The checked copy replaces the folder, so what runs is exactly what was checked.
        self._write_record(staged.folder, staged)
        self._put_in_place(staged.folder, widget_id)
        self._registry.refresh()
        return self._registry.get(widget_id)

    def remove(self, widget_id: str) -> None:
        spec = self.installed(widget_id)
        if spec is None:
            raise InstallError(f"'{widget_id}' is not an installed widget")
        folder = os.path.realpath(spec.folder)
        if os.path.dirname(folder) != os.path.realpath(self.install_dir):
            raise InstallError(f"'{widget_id}' is not inside the widget folder")
        shutil.rmtree(folder)
        self._registry.refresh()

    @staticmethod
    def _check_unchanged(staged: StagedWidget) -> None:
        if not staged.report.ok or staged.report.manifest is None:
            raise InstallError('the widget did not pass validation')
        if file_digests(staged.folder) != staged.files:
            raise InstallError('the checked copy of the widget changed')

    def _put_in_place(self, staging: str, widget_id: str) -> None:
        target = os.path.join(self.install_dir, widget_id)
        old = None
        if os.path.lexists(target):
            old = tempfile.mkdtemp(prefix=f'.old-{widget_id}-', dir=self.install_dir)
            os.replace(target, os.path.join(old, widget_id))
        try:
            os.replace(staging, target)
        except BaseException:
            if old is not None:
                os.replace(os.path.join(old, widget_id), target)
                shutil.rmtree(old, ignore_errors=True)
            raise
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)

    @staticmethod
    def _write_record(folder: str, staged: StagedWidget) -> None:
        record = {
            'manifest': staged.report.manifest,
            'capabilities': staged.report.capabilities,
            'files': staged.files,
            'approved_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        }
        with open(os.path.join(folder, MANIFEST_FILE), 'w', encoding='utf-8') as handle:
            json.dump(record, handle, indent=2)
