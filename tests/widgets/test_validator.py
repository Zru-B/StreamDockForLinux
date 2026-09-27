"""Checking third-party widgets before install: static pass and dry run."""

import os

import pytest

from StreamDock.widgets.validator import validate_widget

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')
BUILTINS = ['digital_clock']


def check(name, dry_run=True):
    return validate_widget(os.path.join(FIXTURES, name), reserved_ids=BUILTINS, dry_run=dry_run)


def test_good_widget_passes_with_manifest_from_source():
    report = check('good.py')

    assert report.ok, report.errors
    assert report.manifest['id'] == 'fixture_good'
    assert [option['key'] for option in report.manifest['options']] == ['label', 'start']
    assert report.manifest['events'] == ['press']
    assert report.capabilities == []


@pytest.mark.parametrize('name, message', [
    ('no_widget.py', 'exactly one class'),
    ('two_widgets.py', 'exactly one class'),
    ('nonliteral_id.py', 'plain literal'),
    ('too_new.py', 'SDK version 99'),
    ('clash.py', 'already used by a built-in'),
    ('bad_option.py', 'must be one of'),
    ('bad_states.py', "'states' must be a list"),
])
def test_static_problems_are_errors(name, message):
    report = check(name, dry_run=False)

    assert not report.ok
    assert any(message in error for error in report.errors), report.errors


def test_static_failures_never_run_the_script():
    # A script that fails the static pass must not be imported at all.
    report = check('two_widgets.py')
    assert not any('test run' in error for error in report.errors)


def test_wrong_frame_size_fails_the_dry_run():
    report = check('wrong_size.py')

    assert not report.ok
    assert any('50x50' in error for error in report.errors), report.errors


def test_hanging_import_times_out():
    report = check('hang_import.py')

    assert not report.ok
    assert any('did not finish' in error for error in report.errors), report.errors


def test_printing_does_not_break_the_protocol():
    report = check('printing.py')
    assert report.ok, report.errors


def test_capabilities_are_reported_not_refused():
    report = check('capabilities.py')

    assert report.ok, report.errors
    assert report.capabilities == ['runs code built at runtime', 'runs other programs', 'uses the network']


def test_folder_widget_imports_its_helpers():
    report = check('folder_widget')
    assert report.ok, report.errors


def test_folder_without_entry_file_is_refused(tmp_path):
    report = validate_widget(str(tmp_path))
    assert report.errors == ['widget.py not found in the folder']


def test_states_and_badge_come_from_the_source():
    report = check('stateful.py')
    assert report.ok, report.errors
    assert report.manifest['states'] == ['on', 'off']
    assert report.manifest['supports_badge'] is True


def test_watching_window_focus_is_a_capability_to_consent_to():
    report = check('stateful.py')
    assert 'sees which window you focus, and its title' in report.capabilities
    assert report.manifest['window_focus'] is True
    assert report.manifest['run_while_hidden'] is False


def test_data_dir_is_usable_during_the_test_run():
    # The widget writes into ctx.data_dir in setup; the dry run lends it a scratch folder.
    assert check('uses_data_dir.py').ok


@pytest.mark.parametrize('name', ['hello_counter.py', 'reachability.py'])
def test_documented_examples_pass_validation(name):
    examples = os.path.join(os.path.dirname(__file__), '..', '..', 'examples', 'widgets')
    report = validate_widget(os.path.join(examples, name))
    assert report.ok, report.errors


@pytest.mark.parametrize('call', ['os.system("x")', 'os.execlp("x", "x")', 'os.spawnlp(0, "x", "x")',
                                  'os.posix_spawnp("x", ["x"], {})', 'os.popen("x")'])
def test_every_os_program_call_is_a_capability(tmp_path, call):
    script = tmp_path / 'w.py'
    script.write_text(f"""import os
from streamdock_sdk import Widget, draw


class W(Widget):
    id = 'fixture_os_call'
    name = 'W'
    version = '1'

    def render(self, ctx):
        return draw.text_key('x', size=ctx.size)

    def later(self):
        {call}
""")
    report = validate_widget(str(script), dry_run=False)
    assert report.capabilities == ['runs other programs']


@pytest.mark.parametrize('imports, call, capability', [
    ('from os import system', 'system("x")', 'runs other programs'),
    ('from os import execvp as go', 'go("x", ["x"])', 'runs other programs'),
    ('from os import *', 'popen("x")', 'runs other programs'),
    ('import os as o', 'o.system("x")', 'runs other programs'),
    ('import os as o', 'run = o.popen', 'runs other programs'),
    ('import importlib', 'importlib.import_module("subprocess")', 'runs code built at runtime'),
    ('import builtins', 'getattr(builtins, "ev" + "al")("1")', 'runs code built at runtime'),
    ('import os', 'getattr(__builtins__, "ev" + "al")("1")', 'runs code built at runtime'),
    ('from StreamDock.infrastructure import mpris', 'mpris.current()', "uses the app's own code"),
])
def test_indirect_spellings_are_capabilities(tmp_path, imports, call, capability):
    # Only a bare "os.system(...)" was noticed; an alias or a from-import slipped past.
    script = tmp_path / 'w.py'
    script.write_text(f"""{imports}
from streamdock_sdk import Widget, draw


class W(Widget):
    id = 'fixture_indirect'
    name = 'W'
    version = '1'

    def render(self, ctx):
        return draw.text_key('x', size=ctx.size)

    def later(self):
        {call}
""")
    assert capability in validate_widget(str(script), dry_run=False).capabilities


def test_reading_os_paths_is_not_a_capability(tmp_path):
    script = tmp_path / 'w.py'
    script.write_text("""import os
from streamdock_sdk import Widget, draw


class W(Widget):
    id = 'fixture_os_path'
    name = 'W'
    version = '1'

    def render(self, ctx):
        os.path.join('a', 'b')
        return draw.text_key(os.getcwd()[:1], size=ctx.size)
""")
    assert validate_widget(str(script), dry_run=False).capabilities == []


def widget_source(tmp_path, attributes):
    script = tmp_path / 'w.py'
    script.write_text(f"""from streamdock_sdk import Widget, draw


class W(Widget):
{attributes}

    def render(self, ctx):
        return draw.text_key('x', size=ctx.size)
""")
    return str(script)


@pytest.mark.parametrize('attributes', [
    "    id = {[1]: 2}\n    name = 'W'\n    version = '1'",
    "    id = 'fixture_x'\n    name = 'W'\n    version = '1'\n    states = [{[]: 1}]",
    "    id = 'fixture_x'\n    name = 'W'\n    version = '1'\n    options = [Option.int('n', {[]: 1})]",
])
def test_unhashable_literals_are_errors_not_crashes(tmp_path, attributes):
    report = validate_widget(widget_source(tmp_path, attributes), dry_run=False)
    assert not report.ok


def test_deeply_nested_source_is_an_error_not_a_crash(tmp_path):
    script = tmp_path / 'w.py'
    script.write_text('x = ' + '(' * 100000 + ')' * 100000 + '\n')
    assert not validate_widget(str(script), dry_run=False).ok


@pytest.mark.parametrize('field, value', [
    ('id', "'fixture_x\\n'"),
    ('states', "['on\\n']"),
])
def test_patterns_do_not_accept_a_trailing_newline(tmp_path, field, value):
    attributes = {'id': "'fixture_x'", 'name': "'W'", 'version': "'1'", field: value}
    body = '\n'.join(f'    {key} = {val}' for key, val in attributes.items())
    assert not validate_widget(widget_source(tmp_path, body), dry_run=False).ok


@pytest.mark.parametrize('field, value', [
    ('name', "'Clock\\nInstalled by the app'"),
    ('name', repr('x' * 81)),
    ('name', "'evil\\u202e'"),
    ('author', "'a\\tb'"),
    ('author', repr('a' * 201)),
])
def test_name_and_author_are_single_short_lines(tmp_path, field, value):
    attributes = {'id': "'fixture_x'", 'name': "'W'", 'version': "'1'", field: value}
    body = '\n'.join(f'    {key} = {val}' for key, val in attributes.items())
    report = validate_widget(widget_source(tmp_path, body), dry_run=False)
    assert any('single line' in error for error in report.errors), report.errors


def test_symlinked_folder_is_refused(tmp_path):
    folder = tmp_path / 'widget'
    folder.mkdir()
    (folder / 'widget.py').write_text(open(os.path.join(FIXTURES, 'good.py'), encoding='utf-8').read())
    os.symlink(tmp_path, folder / 'elsewhere')
    report = validate_widget(str(folder), dry_run=False)
    assert any('symbolic links' in error for error in report.errors), report.errors
