# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional PDF export test; needs a display and Poppler's pdftotext/pdfinfo."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["LC_ALL"] = "C.UTF-8"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdview.app import Adw, Application, Gio, GLib, Gtk, Window


def wait_for(predicate):
    deadline = time.monotonic() + 30
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('PDF test timed out')


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    os.environ['XDG_STATE_HOME'] = str(root / 'state')
    source = root / 'Test document.md'
    text = '# PDF export test\n\nGrüße from mdview.\n\n```python\nprint("PDF code")\n```\n\n'
    text += 'A paragraph for pagination.\n\n' * 150
    source.write_text(text)
    app = Application()
    app.set_application_id('io.github.mdview.PdfTest')
    app.register(None)
    window = Window(app)
    window.present()
    assert not window.lookup_action('export-pdf').get_enabled()
    window.open_file(Gio.File.new_for_path(str(source)))
    document = window.active_document
    wait_for(lambda: not document.web.is_loading() and document.web.get_height() > 0)
    assert window.lookup_action('export-pdf').get_enabled()
    assert window.menu_button.get_next_sibling() == window.reload_button
    window.lookup_action('export-pdf').activate(None)
    dialogs = [w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.FileChooserDialog)]
    assert len(dialogs) == 1
    assert dialogs[0].get_current_name() == 'Test document.pdf'
    assert dialogs[0].get_action() == Gtk.FileChooserAction.SAVE
    dialogs[0].response(Gtk.ResponseType.CANCEL)
    assert not list(root.glob('*.pdf'))
    errors = []
    window.error = errors.append
    window.export_pdf(document, Gio.File.new_for_path(str(source)))
    assert errors and source.read_text() == text
    errors.clear()
    target = root / 'Test document.pdf'
    document.style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    window.lookup_action('export-pdf').activate(None)
    save_dialog = next(w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.FileChooserDialog))
    wait_for(lambda: save_dialog.get_current_folder() is not None
             and save_dialog.get_current_folder().get_path() == str(root))
    save_dialog.response(Gtk.ResponseType.ACCEPT)
    wait_for(lambda: bool(errors) or (target.exists() and not window.print_operations))
    assert not errors, errors
    assert target.read_bytes().startswith(b'%PDF-')
    output = subprocess.run(['pdftotext', str(target), '-'], check=True, capture_output=True, text=True).stdout
    assert 'PDF export test' in output and 'PDF code' in output and 'Grüße' in output
    assert 'Copy' not in output
    info = subprocess.run(['pdfinfo', str(target)], check=True, capture_output=True, text=True).stdout
    pages = int(next(line.split(':')[1] for line in info.splitlines() if line.startswith('Pages:')))
    assert pages > 1
    assert source.read_text() == text
    window.export_pdf(document, Gio.File.new_for_path(str(root / 'missing' / 'failed.pdf')))
    wait_for(lambda: not window.print_operations)
    assert errors and 'Could not export PDF' in errors[-1]
    assert app.get_accels_for_action('win.export-pdf') == ['<Control>e']
    assert app.get_accels_for_action('win.print') == ['<Control>p']
    model = window.menu_button.get_menu_model()
    assert [model.get_item_attribute_value(i, 'label', None).get_string()
            for i in range(model.get_n_items())] == ['Export as PDF', 'Print']
    seen = []

    def cancel_print_dialog():
        for dialog in Gtk.Window.list_toplevels():
            if type(dialog).__name__ == 'PrintUnixDialog':
                seen.append(dialog.get_transient_for() == window)
                dialog.response(Gtk.ResponseType.CANCEL)
                return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    cancel_source = GLib.timeout_add(100, cancel_print_dialog)
    window.lookup_action('print').activate(None)
    assert seen == [True], 'The standard print dialog was not shown'
    assert not window.print_operations
    window.close()
    print(f'PASS: menu actions, shortcuts, standard print dialog cancellation, PDF save defaults, cancel, source protection, PDF content and {pages} pages.')
