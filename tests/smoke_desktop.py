# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check application identity; run on Wayland or with X11 and xprop."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Gio validates Exec against PATH; exercise the renamed checkout command too.
os.environ['PATH'] = str(Path(__file__).resolve().parents[1] / 'bin') + os.pathsep + os.environ['PATH']
from mdviewer.app import APP_ID, Application, Gio, GLib, Gtk


with tempfile.TemporaryDirectory() as directory:
    os.environ['XDG_STATE_HOME'] = directory
    app = Application()
    assert APP_ID == 'com.github.jschbe.mdviewer'
    assert app.get_application_id() == APP_ID
    assert app.get_flags() & Gio.ApplicationFlags.HANDLES_OPEN
    desktop = Gio.DesktopAppInfo.new_from_filename(str(
        Path(__file__).resolve().parents[1] / 'data' / f'{APP_ID}.desktop'))
    assert desktop is not None
    assert desktop.get_id() == f'{APP_ID}.desktop'
    assert desktop.get_executable() == 'mdviewer'
    assert desktop.get_icon().to_string() == APP_ID
    assert desktop.get_startup_wm_class() == APP_ID
    errors = []
    checked = []

    def activated(app):
        try:
            window = app.get_windows()[0]
            assert GLib.get_prgname() == APP_ID
            assert GLib.get_application_name() == 'mdviewer'
            assert window.get_title() == 'mdviewer'
            assert Gtk.Window.get_default_icon_name() == APP_ID
            surface = window.get_surface()
            if surface.get_display().__gtype__.name == 'GdkX11Display':
                import gi
                gi.require_version('GdkX11', '4.0')
                from gi.repository import GdkX11

                xid = GdkX11.X11Surface.get_xid(surface)
                properties = subprocess.check_output(
                    ['xprop', '-id', str(xid), 'WM_CLASS', '_GTK_APPLICATION_ID'], text=True)
                assert f'WM_CLASS(STRING) = "{APP_ID}", "{APP_ID}"' in properties, properties
                assert f'_GTK_APPLICATION_ID(UTF8_STRING) = "{APP_ID}"' in properties, properties
            checked.append(True)
        except Exception as exc:
            errors.append(exc)
        finally:
            app.quit()

    app.connect_after('activate', activated)
    app.run(['mdviewer'])
    if errors:
        raise errors[0]
    assert checked
    print('PASS: application ID, desktop entry, CLI, icon and window identity')
