# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional GUI integration test for wrapped document search."""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ['LC_ALL'] = 'C.UTF-8'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdview.app import Application, Gio, GLib, Window


def wait_for(predicate):
    deadline = time.monotonic() + 20
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Find test timed out')


def scroll_y(web):
    values = []
    def result(view, response):
        values.append(view.evaluate_javascript_finish(response).to_double())
    web.evaluate_javascript('window.scrollY', -1, None, None, None, result)
    wait_for(lambda: values)
    return values[0]


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    os.environ['XDG_STATE_HOME'] = str(root / 'state')
    source = root / 'search.md'
    source.write_text('# Needle\n\n' + 'Filler paragraph.\n\n' * 150 + 'NEEDLE\n')
    other = root / 'other.md'
    other.write_text('Different content.\n')
    app = Application()
    app.set_application_id('io.github.mdview.FindTest')
    app.register(None)
    window = Window(app)
    window.present()
    assert not window.lookup_action('find').get_enabled()
    assert '<Control>f' in app.get_accels_for_action('win.find')
    menu = window.menu_button.get_menu_model()
    assert [menu.get_item_attribute_value(i, 'label', None).get_string()
            for i in range(menu.get_n_items())] == ['Export as PDF', 'Find', 'Print']
    window.open_file(Gio.File.new_for_path(str(source)))
    web = window.active_document.web
    wait_for(lambda: not web.is_loading() and web.get_height() > 0)
    window.lookup_action('find').activate(None)
    dialog = window.find_window
    assert dialog.get_title() == 'Find in (search.md)'
    assert not dialog.case_sensitive.get_active()
    assert not dialog.get_modal() and dialog.get_decorated()
    window.show_find()
    assert window.find_window is dialog
    found = []
    dialog.controller.connect('found-text', lambda _controller, count: found.append(count))
    dialog.entry.set_text('needle')
    for index in range(3):
        dialog.find_button.emit('clicked')
        wait_for(lambda: len(found) > index)
        position = scroll_y(web)
        if index == 1:
            assert position > 1000, position
        else:
            assert position < 200, position
        assert not dialog.message.get_text()
    dialog.case_sensitive.set_active(True)
    dialog.find()
    wait_for(lambda: dialog.message.get_text() == 'not found')
    dialog.entry.set_text('NEEDLE')
    count = len(found)
    dialog.find()
    wait_for(lambda: len(found) > count)
    assert scroll_y(web) > 1000
    count = len(found)
    dialog.find()
    wait_for(lambda: len(found) > count)
    assert scroll_y(web) > 1000
    dialog.case_sensitive.set_active(False)
    dialog.entry.set_text('no such phrase')
    dialog.find()
    wait_for(lambda: dialog.message.get_text() == 'not found')
    assert dialog.get_visible()
    window.open_file(Gio.File.new_for_path(str(other)))
    wait_for(lambda: not window.active_document.web.is_loading())
    assert dialog.web is window.active_document.web
    assert dialog.get_title() == 'Find in (other.md)'
    assert not dialog.message.get_text()
    window.close_current_tab()
    assert dialog.web is web
    assert dialog.get_title() == 'Find in (search.md)'
    dialog.close()
    assert window.find_window is None
    window.show_find()
    assert window.find_window is not dialog
    assert not window.find_window.case_sensitive.get_active()
    window.cleanup()
    assert window.find_window is None
    window.destroy()
    app.quit()
    print('PASS: menu, shortcut, non-modal window, first/next/wrapped matches, case-insensitivity, no match, tab changes and cleanup.')
