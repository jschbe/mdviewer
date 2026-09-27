# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional GUI test for session restore, including missing and binary files."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["LC_ALL"] = "C.UTF-8"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdview.app import Adw, Application, Gio, GLib, Gtk, Window
from mdview.session import load_session
from mdview.recent import load_recent


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    os.environ['XDG_STATE_HOME'] = str(root / 'state')
    files = [root / name for name in ('a.md', 'b.md', 'c.md', 'd.md')]
    for file in files:
        file.write_text('# Session test\n')
    app = Application()
    app.set_application_id('io.github.mdview.SessionTest')
    app.register(None)
    window = Window(app)
    window.present()
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
    loop = GLib.MainLoop()
    GLib.timeout_add(300, lambda: (loop.quit(), False)[1])
    loop.run()
    assert [doc.path for doc in failed.documents()] == [files[3]]
    dialogs = [w for w in Gtk.Window.list_toplevels() if isinstance(w, Adw.MessageDialog)]
    assert len(dialogs) == 1
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
    print('PASS: saved tab order and selection, closed tabs removed, missing/binary errors grouped, surviving files restored, recovery and empty session.')
