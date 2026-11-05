# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional GUI test for session restore, including missing and binary files."""

import os
import json
import sys
import tempfile
from pathlib import Path

os.environ["LC_ALL"] = "C.UTF-8"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdviewer.app import Adw, Application, Gio, GLib, Gtk, Window
from mdviewer.session import load_session
from mdviewer.recent import load_recent
from gui_helpers import wait_for


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    os.environ['XDG_STATE_HOME'] = str(root / 'state')
    files = [root / name for name in ('a.md', 'b.md', 'c.md', 'd.md')]
    for file in files:
        file.write_text('# Session test\n')
    legacy = root / 'state/mdview'
    legacy.mkdir(parents=True)
    (legacy / 'window.json').write_text(json.dumps({'zoom': 125}))
    (legacy / 'session.json').write_text(json.dumps({'files': [str(files[0])], 'active': str(files[0])}))
    (legacy / 'recent.json').write_text(json.dumps([str(files[0])]))
    originals = {path.name: path.read_bytes() for path in legacy.iterdir()}
    app = Application()
    app.set_application_id('com.github.jschbe.mdviewer.SessionTest')
    app.register(None)
    window = Window(app)
    window.present()
    assert window.state_path.parent == root / 'state/mdviewer'
    assert window.zoom == 125 and window.active_document.path == files[0]
    for file in files:
        window.open_file(Gio.File.new_for_path(str(file)))
    window.tab_view.set_selected_page(window.tab_view.get_nth_page(0))
    window.open_file(Gio.File.new_for_path(str(files[1])))
    window.tab_view.reorder_page(window.tab_view.get_nth_page(3), 0)
    expected_order = [files[3], files[0], files[1], files[2]]
    history = load_recent(window.recent_path)
    assert history == [str(files[1]), str(files[3]), str(files[2]), str(files[0])]
    session_path = window.session_path
    window.close()
    assert load_session(session_path) == {'files': [str(p) for p in expected_order], 'active': str(files[1])}
    restored = Window(app)
    restored.present()
    assert [doc.path for doc in restored.documents()] == expected_order
    assert restored.active_document.path == files[1]
    assert load_recent(restored.recent_path) == history
    # Closing a tab should remove it from the next session.
    restored.tab_view.close_page(restored.tab_view.get_nth_page(2))
    restored.close()
    assert load_session(session_path)['files'] == [str(files[3]), str(files[0]), str(files[2])]
    files[0].unlink()
    files[2].write_bytes(b'\0binary')
    failed = Window(app)
    failed.present()
    wait_for(lambda: any(isinstance(w, Adw.MessageDialog) for w in Gtk.Window.list_toplevels()),
             'Session restoration did not show the grouped error dialog')
    assert [doc.path for doc in failed.documents()] == [files[3]]
    dialogs = [w for w in Gtk.Window.list_toplevels() if isinstance(w, Adw.MessageDialog)]
    assert len(dialogs) == 1, [(type(w).__name__, w.get_visible()) for w in Gtk.Window.list_toplevels()]
    details = dialogs[0].get_extra_child().get_child().get_child().get_label()
    assert str(files[0]) in details and str(files[2]) in details
    assert 'File cannot be displayed' in details
    dialogs[0].close()
    # Surviving files remain usable, and new files can still be opened.
    failed.close_current_tab()
    failed.open_file(Gio.File.new_for_path(str(files[1])))
    failed.close()
    assert load_session(session_path)['files'] == [str(files[1])]
    final = Window(app)
    final.present()
    assert final.active_document.path == files[1]
    final.close_current_tab()
    final.close()
    assert load_session(session_path)['files'] == []
    assert {path.name: path.read_bytes() for path in legacy.iterdir()} == originals
    print('PASS: saved tab order and selection, closed tabs removed, missing/binary errors grouped, surviving files restored, recovery and empty session.')
