# SPDX-FileCopyrightText: 2026 Jochen Schmitt and mdview contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional tab integration test; run with a desktop or xvfb-run."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdview.app import Adw, Application, Gdk, Gio, GLib, Gtk, Window
from mdview.recent import load_recent


def wait_for(predicate, message):
    deadline = time.monotonic() + 15
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(message)


def javascript(document, script):
    values = []

    def completed(web, result, _data):
        values.append(json.loads(web.evaluate_javascript_finish(result).to_json(0)))

    document.js(script, completed)
    wait_for(lambda: bool(values), 'JavaScript did not complete')
    return values[0]


def wait_loaded(document):
    wait_for(lambda: not document.web.is_loading(), 'Document did not load')
    wait_for(lambda: document.web.get_height() > 0 and document.web.get_width() > 0,
             'Document loaded but the WebView has no visible area')
    assert document.web.get_height() >= document.get_height() * 0.9
    assert document.web.get_width() >= document.get_width() * 0.9
    assert javascript(document, 'document.querySelector("h1") !== null')


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    os.environ['XDG_STATE_HOME'] = str(root / 'state')
    first, second, third = root / 'a' / 'same.md', root / 'b' / 'same.md', root / 'third.md'
    for index, path in enumerate((first, second, third)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'# Document {index}\n\n```\ncode {index}\n```\n\n' + 'Paragraph.\n\n' * 200)
    binary = root / 'binary.md'
    binary.write_bytes(b'not text\x00')
    app = Application()
    app.set_application_id('io.github.mdview.TabTest')
    app.register(None)
    window = Window(app)
    window.present()
    assert window.tab_view.get_n_pages() == 1
    assert not window.tab_bar.get_tabs_revealed()

    assert window.open_file(Gio.File.new_for_path(str(first)))
    first_view = window.active_document
    wait_loaded(first_view)
    assert not window.tab_bar.get_tabs_revealed()
    assert window.heading.get_title() == first.name
    assert window.heading.get_subtitle() == str(first.parent)
    javascript(first_view, 'window.scrollTo(0, 400); true')
    wait_for(lambda: javascript(first_view, 'window.scrollY') == 400, 'First scroll position')

    assert window.open_file(Gio.File.new_for_path(str(second)))
    second_view = window.active_document
    wait_loaded(second_view)
    assert second_view is not first_view
    assert window.tab_view.get_n_pages() == 2 and window.tab_bar.get_tabs_revealed()
    assert window.heading.get_subtitle() == str(second.parent)
    assert first_view.codes == ['code 0\n'] and second_view.codes == ['code 1\n']
    javascript(second_view, 'window.scrollTo(0, 800); true')
    wait_for(lambda: javascript(second_view, 'window.scrollY') == 800, 'Second scroll position')

    # Inactive files keep their own watcher and must not change the active title.
    replacement = first.with_suffix('.tmp')
    replacement.write_text(first.read_text().replace('# Document 0', '# Updated'))
    replacement.replace(first)
    wait_for(lambda: javascript(first_view, 'document.querySelector("h1").textContent') == 'Updated',
             'Inactive tab did not reload')
    assert window.active_document is second_view
    assert window.heading.get_subtitle() == str(second.parent)
    assert javascript(second_view, 'window.scrollY') == 800
    assert window.open_file(Gio.File.new_for_path(str(first)))
    assert window.active_document is first_view and window.tab_view.get_n_pages() == 2
    wait_for(lambda: javascript(first_view, 'window.scrollY') == 400, 'First tab lost scroll position')

    errors = []
    window.error = errors.append
    history = load_recent(window.recent_path)
    assert not window.open_file(Gio.File.new_for_path(str(binary)))
    assert errors == ['File cannot be displayed']
    assert window.active_document is first_view and window.tab_view.get_n_pages() == 2
    assert load_recent(window.recent_path) == history

    # Both the plus button and Open use a multi-selection chooser; cancel adds no tab.
    window.new_file_button.emit('clicked')
    dialogs = [w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.FileChooserDialog)]
    assert len(dialogs) == 1 and dialogs[0].get_select_multiple()
    dialogs[0].response(Gtk.ResponseType.CANCEL)
    assert window.tab_view.get_n_pages() == 2

    # App file-open requests reuse the window, and skip duplicate tabs.
    app.do_open([Gio.File.new_for_path(str(second)), Gio.File.new_for_path(str(third))], 2, '')
    assert len([w for w in app.get_windows() if isinstance(w, Window)]) == 1
    assert window.tab_view.get_n_pages() == 3
    third_view = window.active_document
    assert third_view.path == third
    wait_loaded(third_view)
    assert window.drop_files(None, Gdk.FileList.new_from_list([Gio.File.new_for_path(str(first))]), 0, 0)
    assert window.active_document is first_view and window.tab_view.get_n_pages() == 3

    # Closing releases the watcher and pending reload without affecting other tabs.
    monitor = first_view.monitor
    first_view.pending_reload = GLib.timeout_add(10000, first_view.monitored_reload)
    window.close_current_tab()
    assert first_view.closed and monitor.is_cancelled() and first_view.pending_reload == 0
    assert window.tab_view.get_n_pages() == 2
    while window.tab_view.get_n_pages() > 1:
        window.close_current_tab()
    assert not window.tab_bar.get_tabs_revealed()
    window.close_current_tab()
    assert window.tab_view.get_n_pages() == 1
    assert window.active_document.path is None and not window.tab_bar.get_tabs_revealed()
    assert window.heading.get_title() == 'mdview' and window.heading.get_subtitle() == ''
    assert not window.reload_button.get_sensitive()
    assert second_view.closed and third_view.closed
    window.close()
    print('PASS: tabs, hidden single-tab bar, file locations, independent scrolling/watching, duplicate and invalid files, plus button, app open, drag/drop, and tab cleanup')
