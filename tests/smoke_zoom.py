# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional zoom integration test; run on a desktop or with xvfb-run."""

import os
import json
import sys
import tempfile
from pathlib import Path

os.environ["LC_ALL"] = "C.UTF-8"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdview.app import Adw, Application, Gio, Gtk, Window
from mdview.state import load_state
from gui_helpers import javascript, wait_for


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    os.environ["XDG_STATE_HOME"] = str(root / "state")
    files = [root / name for name in ("first.md", "second.md", "third.md")]
    source = '# Zoom\n\nParagraph.\n\n| A |\n|---|\n| B |\n\n```\ncode\n```\n\n'
    for file in files:
        file.write_text(source + "Paragraph for scrolling.\n\n" * 200)
    app = Application()
    app.set_application_id("io.github.mdview.ZoomTest")
    app.register(None)
    window = Window(app)
    window.present()
    assert window.zoom == 100 and window.zoom_label.get_text() == "100%"
    window.menu_button.popup()
    wait_for(lambda: window.zoom_label.get_mapped(), "Zoom control is not in the menu")
    assert isinstance(window.zoom_label, Gtk.Label) and not window.zoom_label.get_selectable()
    row = window.zoom_label.get_parent()
    assert row.get_first_child().get_next_sibling() is window.zoom_minus
    assert window.zoom_minus.get_next_sibling() is window.zoom_label
    assert window.zoom_label.get_next_sibling() is window.zoom_plus
    assert window.zoom_plus.get_next_sibling() is None
    for button in (window.zoom_minus, window.zoom_plus):
        assert not button.get_has_frame()
        assert button.has_css_class("flat") and button.has_css_class("circular")
        assert button.get_tooltip_text()
        assert button.get_icon_name() is None
    assert window.zoom_minus.get_label() == "−" and window.zoom_plus.get_label() == "+"
    assert window.zoom_minus.get_action_name() == "win.zoom-out"
    assert window.zoom_plus.get_action_name() == "win.zoom-in"

    def labels(widget):
        if isinstance(widget, Gtk.Label):
            yield widget
        child = widget.get_first_child()
        while child:
            yield from labels(child)
            child = child.get_next_sibling()

    print_label = next(label for label in labels(window.menu_button.get_popover())
                       if label.get_text() == "Print")
    menu_font = print_label.get_pango_context().get_font_description()
    for label in (row.get_first_child(), window.zoom_label,
                  window.zoom_minus.get_child(), window.zoom_plus.get_child()):
        assert label.get_pango_context().get_font_description().equal(menu_font)
    for action in ("zoom-in", "zoom-out"):
        assert window.lookup_action(action)
    assert set(app.get_accels_for_action("win.zoom-in")) == {
        "<Control>plus", "<Control>equal", "<Shift><Control>plus", "<Control>KP_Add"}
    assert set(app.get_accels_for_action("win.zoom-out")) == {"<Control>minus", "<Control>KP_Subtract"}

    # Native button geometry and control positions stay compact in both themes.
    for scheme in (Adw.ColorScheme.FORCE_LIGHT, Adw.ColorScheme.FORCE_DARK):
        Adw.StyleManager.get_default().set_color_scheme(scheme)
        layouts = []
        for value in (50, 100, 300):
            window.set_zoom(value)
            frame_clock = row.get_frame_clock()
            previous_frame = frame_clock.get_frame_counter()
            row.queue_allocate()
            wait_for(lambda: frame_clock.get_frame_counter() > previous_frame)
            assert window.zoom_label.get_text() == f"{value}%"
            layouts.append((window.zoom_label.get_width(),
                            window.zoom_minus.get_allocation().x,
                            window.zoom_plus.get_allocation().x))
            for button in (window.zoom_minus, window.zoom_plus):
                assert button.get_width() == button.get_height() <= 28
            assert window.zoom_plus.get_allocation().x + window.zoom_plus.get_width() == row.get_width()
        assert layouts[0] == layouts[1] == layouts[2], layouts
    window.set_zoom(100)
    window.menu_button.popdown()
    for file in files[:2]:
        assert window.open_file(Gio.File.new_for_path(str(file)))
    wait_for(lambda: all(not doc.web.is_loading() for doc in window.documents()))

    def at_zoom(value):
        wait_for(lambda: all(doc.web.get_zoom_level() == value / 100 for doc in window.documents()),
                 "Tabs did not share WebKit zoom")

    for initial, button, expected in ((100, window.zoom_plus, 110), (100, window.zoom_minus, 90),
                                     (125, window.zoom_plus, 130), (125, window.zoom_minus, 120),
                                     (120, window.zoom_minus, 110)):
        window.set_zoom(initial)
        button.emit("clicked")
        assert window.zoom == expected and window.zoom_label.get_text() == f"{expected}%"
        at_zoom(expected)
    for value in (50, 125, 300):
        window.set_zoom(value)
        assert window.zoom == value and window.zoom_label.get_text() == f"{value}%"
        assert window.zoom_minus.get_sensitive() == (value > 50)
        assert window.zoom_plus.get_sensitive() == (value < 300)
        assert window.lookup_action("zoom-out").get_enabled() == (value > 50)
        assert window.lookup_action("zoom-in").get_enabled() == (value < 300)
        if value in (50, 300):
            action = "zoom-out" if value == 50 else "zoom-in"
            window.lookup_action(action).activate(None)
            assert window.zoom == value
        at_zoom(value)
    for value in (49, 301, True, 125.5):
        window.set_zoom(value)
        assert window.zoom == 300 and window.zoom_label.get_text() == "300%"
    window.zoom_minus.emit("clicked")
    assert window.zoom == 290 and window.zoom_label.get_text() == "290%"
    # The same actions operate on each selected tab and update every view.
    for index in range(window.tab_view.get_n_pages()):
        window.tab_view.set_selected_page(window.tab_view.get_nth_page(index))
        window.set_zoom(100)
        window.lookup_action("zoom-in").activate(None)
        assert window.zoom == 110
        at_zoom(110)
        window.lookup_action("zoom-out").activate(None)
        assert window.zoom == 100
        at_zoom(100)
    window.set_zoom(125)
    assert window.open_file(Gio.File.new_for_path(str(files[2])))
    document = window.active_document
    wait_for(lambda: not document.web.is_loading() and document.web.get_width() > 0)
    at_zoom(125)
    assert not document.web.get_settings().get_zoom_text_only()

    # Compare physical sizes: CSS dimensions multiplied by native page zoom.
    def sizes():
        return [size * document.web.get_zoom_level() for size in javascript(document,
            '[...document.querySelectorAll("h1, main > p, table, pre")].slice(0, 4).map(e => e.getBoundingClientRect().height)')]

    window.set_zoom(100)
    at_zoom(100)
    baseline = sizes()
    javascript(document, "window.scrollTo(0, 700); true")
    anchor = javascript(document, "window.mdviewZoomPosition()")
    window.set_zoom(200)
    at_zoom(200)
    wait_for(lambda: javascript(document, "window.mdviewZoomPosition()")[0] == anchor[0],
             "Zoom moved away from the visible paragraph")
    assert all(abs(after / before - 2) < 0.1 for before, after in zip(baseline, sizes()))
    # Reload and theme changes retain the window zoom.
    document.reload()
    wait_for(lambda: not document.web.is_loading())
    at_zoom(200)
    document.style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    wait_for(lambda: javascript(document, 'document.documentElement.className') == "dark")
    at_zoom(200)
    # Pending callbacks are harmless when a tab closes or another file loads.
    window.set_zoom(235)
    window.close_current_tab()
    at_zoom(235)
    window.close()
    assert load_state(window.state_path)["zoom"] == 235
    restored = Window(app)
    restored.present()
    assert restored.zoom == 235 and restored.zoom_label.get_text() == "235%"
    assert len(restored.documents()) == 2
    assert all(doc.web.get_zoom_level() == 2.35 for doc in restored.documents())
    restored.zoom_plus.emit("clicked")
    assert restored.zoom == 240 and restored.zoom_label.get_text() == "240%"
    restored.close()
    for saved, expected in ((10, 50), (500, 300)):
        state = json.loads(window.state_path.read_text())
        state["zoom"] = saved
        window.state_path.write_text(json.dumps(state))
        restored = Window(app)
        restored.present()
        assert restored.zoom == expected and restored.zoom_label.get_text() == f"{expected}%"
        assert all(doc.web.get_zoom_level() == expected / 100 for doc in restored.documents())
        restored.close()
        assert load_state(window.state_path)["zoom"] == expected
    print("PASS: text zoom buttons, right alignment/light-dark geometry, shortcut registration/shared actions, stepping, 50–300% limits, all-tab/new-tab zoom, text/table/code scaling, scroll position, theme/reload, closed callbacks, persistence and old-state clamping")
