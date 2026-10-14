# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helpers for optional real GTK/WebKit integration tests."""

import json
import time

from mdview.app import GLib


def wait_for(predicate, message="GUI test timed out"):
    deadline = time.monotonic() + 20
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
        try:
            values.append(json.loads(web.evaluate_javascript_finish(result).to_json(0)))
        except GLib.Error as exc:
            values.append(exc)

    document.js(script, completed)
    wait_for(lambda: bool(values), "JavaScript did not complete")
    if isinstance(values[0], Exception):
        raise AssertionError(f"JavaScript failed: {script}: {values[0]}")
    return values[0]


def clipboard_text(window):
    values = []

    def completed(clipboard, result):
        values.append(clipboard.read_text_finish(result))

    window.get_clipboard().read_text_async(None, completed)
    wait_for(lambda: bool(values), "Clipboard read did not complete")
    return values[0]


class X11Mouse:
    """Send trusted mouse clicks with XTest; only needed by smoke_links.py."""

    def __init__(self, window):
        import ctypes
        import gi

        gi.require_version("GdkX11", "4.0")
        gi.require_version("Graphene", "1.0")
        from gi.repository import GdkX11, Graphene

        self.ctypes, self.Graphene, self.window = ctypes, Graphene, window
        self.x11 = ctypes.CDLL("libX11.so.6")
        self.xtest = ctypes.CDLL("libXtst.so.6")
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self.x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.x11.XTranslateCoordinates.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
            ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong)]
        self.x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.xtest.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        self.xtest.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint,
            ctypes.c_int, ctypes.c_ulong]
        self.display = self.x11.XOpenDisplay(None)
        assert self.display, "XTest integration test needs an X11 display"
        self.xid = GdkX11.X11Surface.get_xid(window.get_surface())

    def click(self, document, selector, button=1):
        x, y = javascript(document, f"""(() => {{
          const element = document.querySelector({json.dumps(selector)});
          element.scrollIntoView({{block: 'center'}});
          const rect = element.getBoundingClientRect();
          return [rect.x + rect.width / 2, rect.y + rect.height / 2];
        }})()""")
        ok, point = document.web.compute_point(self.window, self.Graphene.Point().init(0, 0))
        assert ok
        root_x, root_y, child = self.ctypes.c_int(), self.ctypes.c_int(), self.ctypes.c_ulong()
        zoom = document.web.get_zoom_level()
        self.x11.XTranslateCoordinates(self.display, self.xid,
            self.x11.XDefaultRootWindow(self.display), int(point.x + x * zoom),
            int(point.y + y * zoom), self.ctypes.byref(root_x), self.ctypes.byref(root_y),
            self.ctypes.byref(child))
        self.xtest.XTestFakeMotionEvent(self.display, -1, root_x.value, root_y.value, 0)
        self.xtest.XTestFakeButtonEvent(self.display, button, True, 0)
        self.xtest.XTestFakeButtonEvent(self.display, button, False, 0)
        self.x11.XSync(self.display, False)

    def close(self):
        self.x11.XCloseDisplay(self.display)


class X11Keyboard(X11Mouse):
    """Send real Ctrl shortcuts, resolving Shift from the current X11 keymap."""

    def __init__(self, window):
        super().__init__(window)
        from mdview.app import Gtk

        self.key_releases = []
        self.key_controller = Gtk.EventControllerKey()
        self.key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.key_controller.connect("key-released", lambda *_: self.key_releases.append(True))
        window.add_controller(self.key_controller)
        self.x11.XKeysymToKeycode.argtypes = [self.ctypes.c_void_p, self.ctypes.c_ulong]
        self.x11.XKeysymToKeycode.restype = self.ctypes.c_uint
        self.x11.XKeycodeToKeysym.argtypes = [self.ctypes.c_void_p, self.ctypes.c_uint,
                                           self.ctypes.c_int]
        self.x11.XKeycodeToKeysym.restype = self.ctypes.c_ulong
        self.x11.XSetInputFocus.argtypes = [self.ctypes.c_void_p, self.ctypes.c_ulong,
                                          self.ctypes.c_int, self.ctypes.c_ulong]
        self.xtest.XTestFakeKeyEvent.argtypes = [self.ctypes.c_void_p, self.ctypes.c_uint,
                                               self.ctypes.c_int, self.ctypes.c_ulong]

    def shortcut(self, symbol):
        from mdview.app import Gdk

        keyval = Gdk.keyval_from_name(symbol)
        keycode = self.x11.XKeysymToKeycode(self.display, keyval)
        assert keycode, f"Keymap does not contain {symbol}"
        modifiers = [self.x11.XKeysymToKeycode(self.display, Gdk.KEY_Control_L)]
        if self.x11.XKeycodeToKeysym(self.display, keycode, 0) != keyval:
            assert self.x11.XKeycodeToKeysym(self.display, keycode, 1) == keyval
            modifiers.append(self.x11.XKeysymToKeycode(self.display, Gdk.KEY_Shift_L))
        self.x11.XSetInputFocus(self.display, self.xid, 2, 0)
        previous_releases = len(self.key_releases)
        for code in modifiers + [keycode]:
            self.xtest.XTestFakeKeyEvent(self.display, code, True, 0)
        for code in reversed(modifiers + [keycode]):
            self.xtest.XTestFakeKeyEvent(self.display, code, False, 0)
        self.x11.XSync(self.display, False)
        # Wait for GTK, not merely the X server, before another test changes
        # zoom/enables an action. Otherwise an old keypress can arrive late.
        wait_for(lambda: len(self.key_releases) >= previous_releases + len(modifiers) + 1,
                 f"GTK did not finish Ctrl+{symbol}")

    def close(self):
        self.window.remove_controller(self.key_controller)
        super().close()
