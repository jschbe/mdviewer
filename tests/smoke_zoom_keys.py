# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Real zoom keyboard shortcuts; needs X11 and libXtst (xvfb works)."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["LC_ALL"] = "C.UTF-8"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdview.app import Application, Gio, Window
from gui_helpers import X11Keyboard, javascript, wait_for


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    os.environ["XDG_STATE_HOME"] = str(root / "state")
    app = Application()
    app.set_application_id("io.github.mdview.ZoomKeysTest")
    app.register(None)
    window = Window(app)
    window.present()
    for filename in ("first.md", "second.md"):
        path = root / filename
        path.write_text("# Keyboard zoom\n\n" + "Paragraph.\n\n" * 100)
        assert window.open_file(Gio.File.new_for_path(str(path)))
    wait_for(lambda: all(not doc.web.is_loading() for doc in window.documents())
             and window.get_surface().get_mapped())
    keyboard = X11Keyboard(window)

    def send_shortcut(symbol):
        # WebKit can defer GTK's shortcut dispatch until its key event is
        # declined. Wait for the document's last modifier release as well.
        document = window.active_document
        javascript(document, '''window.mdviewKeysReleased = false;
          document.addEventListener("keyup", function released(event) {
            if (event.key !== "Control") return;
            window.mdviewKeysReleased = true;
            document.removeEventListener("keyup", released);
          }); true''')
        keyboard.shortcut(symbol)
        wait_for(lambda: javascript(document, "window.mdviewKeysReleased"),
                 f"WebKit did not finish Ctrl+{symbol}")

    for index in range(2):
        window.tab_view.set_selected_page(window.tab_view.get_nth_page(index))
        window.active_document.web.grab_focus()
        for symbol, expected in (("plus", 110), ("equal", 110), ("minus", 90),
                                 ("KP_Add", 110), ("KP_Subtract", 90)):
            window.set_zoom(100)
            send_shortcut(symbol)
            wait_for(lambda: window.zoom == expected, f"Ctrl+{symbol} did not change zoom")
            wait_for(lambda: all(doc.web.get_zoom_level() == expected / 100
                                for doc in window.documents()), "Zoom did not synchronize tabs")
            assert window.zoom_label.get_text() == f"{expected}%"
    for value, symbol in ((50, "minus"), (300, "plus"), (300, "equal")):
        window.set_zoom(value)
        send_shortcut(symbol)
        javascript(window.active_document, "true")
        assert window.zoom == value, (value, symbol, window.zoom)
    # These pre-existing shortcuts retain their registrations.
    assert app.get_accels_for_action("win.find") == ["<Control>f"]
    assert app.get_accels_for_action("win.print") == ["<Control>p"]
    assert app.get_accels_for_action("win.export-pdf") == ["<Control>e"]
    keyboard.close()
    window.close()
    print("PASS: real Ctrl+plus/equal/minus/keypad shortcuts, Shift from the active keymap, all tabs, 50–300% boundaries and existing shortcut registrations")
