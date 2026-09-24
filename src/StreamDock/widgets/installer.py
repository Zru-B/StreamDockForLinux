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
from typing import Optional

from StreamDock.widgets.registry import ENTRY_FILE, MANIFEST_FILE, WidgetRegistry, WidgetSpec, file_digests
from StreamDock.widgets.validator import ValidationReport, validate_widget


class InstallError(Exception):
    pass


class WidgetInstaller:
    def __init__(self, registry: WidgetRegistry):
        self._registry = registry

    @property
    def install_dir(self) -> str:
        return self._registry.install_dir

    def validate(self, source: str) -> ValidationReport:
        return validate_widget(source, reserved_ids=self._registry.builtin_ids())

    def installed(self, widget_id: str) -> Optional[WidgetSpec]:
        spec = self._registry.get(widget_id)
        return spec if spec is not None and not spec.builtin else None

    def install(self, source: str, report: ValidationReport) -> WidgetSpec:
        """
        Copy a validated widget into place, replacing an older copy of the same id.

        ``report`` must come from ``validate`` on the same source; the user's
        consent to its capabilities is recorded with the files.
        """
        if not report.ok or report.manifest is None:
            raise InstallError('the widget did not pass validation')
        widget_id = report.manifest['id']
        os.makedirs(self.install_dir, exist_ok=True)
        staging = tempfile.mkdtemp(prefix=f'.{widget_id}-', dir=self.install_dir)
        try:
            if os.path.isdir(source):
                shutil.copytree(source, staging, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns('__pycache__', '.*', MANIFEST_FILE))
            else:
                shutil.copyfile(source, os.path.join(staging, ENTRY_FILE))
            self._write_record(staging, report)
            target = os.path.join(self.install_dir, widget_id)
            if os.path.exists(target):
                shutil.rmtree(target)
            os.replace(staging, target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        self._registry.refresh()
        return self._registry.get(widget_id)

    def remove(self, widget_id: str) -> None:
        if self.installed(widget_id) is None:
            raise InstallError(f"'{widget_id}' is not an installed widget")
        shutil.rmtree(os.path.join(self.install_dir, widget_id))
        self._registry.refresh()

    def revalidate(self, widget_id: str) -> ValidationReport:
        spec = self.installed(widget_id)
        if spec is None:
            raise InstallError(f"'{widget_id}' is not an installed widget")
        report = self.validate(spec.folder)
        if report.ok and report.manifest['id'] != widget_id:
            report.errors.append(f"the files now declare id '{report.manifest['id']}'")
        return report

    def approve(self, widget_id: str, report: ValidationReport) -> WidgetSpec:
        """Record consent to the current files of an installed widget."""
        spec = self.installed(widget_id)
        if spec is None or not report.ok:
            raise InstallError('nothing to approve')
        self._write_record(spec.folder, report)
        self._registry.refresh()
        return self._registry.get(widget_id)

    @staticmethod
    def _write_record(folder: str, report: ValidationReport) -> None:
        record = {
            'manifest': report.manifest,
            'capabilities': report.capabilities,
            'files': file_digests(folder),
            'approved_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        }
        with open(os.path.join(folder, MANIFEST_FILE), 'w', encoding='utf-8') as handle:
            json.dump(record, handle, indent=2)
