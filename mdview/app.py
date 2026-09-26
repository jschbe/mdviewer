"""Native application shell; rendering lives in render.py."""

import json
import logging
from pathlib import Path
from urllib.parse import unquote, urlsplit

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, WebKit  # noqa: E402

from .render import read_document, render  # noqa: E402
from .state import load_state, save_state  # noqa: E402

APP_ID = "io.github.mdview.Mdview"


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        self.state_path = Path(GLib.get_user_state_dir()) / "mdview" / "window.json"
        state = load_state(self.state_path)
        super().__init__(application=app, title="mdview",
                         default_width=state["width"], default_height=state["height"])
        if state["maximized"]:
            self.maximize()
        self.path = None
        self.codes = []
        self.monitor = None
        self.pending_reload = 0
        self.generation = 0
        self.restore_y = 0
        self.closed = False
        self.style = Adw.StyleManager.get_default()
        self.theme_handler = self.style.connect("notify::dark", self.theme_changed)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        open_button = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Open (Ctrl+O)")
        open_button.connect("clicked", lambda *_: self.choose_file())
        header.pack_start(open_button)
        self.reload_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload (Ctrl+R)", sensitive=False)
        self.reload_button.connect("clicked", lambda *_: self.reload())
        header.pack_end(self.reload_button)
        box.append(header)
        self.toast = Adw.ToastOverlay(vexpand=True)
        box.append(self.toast)
        self.set_content(box)

        manager = WebKit.UserContentManager()
        manager.connect("script-message-received::copy", self.copy_code)
        manager.register_script_message_handler("copy", None)
        self.web = WebKit.WebView(user_content_manager=manager,
                                  network_session=WebKit.NetworkSession.new_ephemeral())
        settings = self.web.get_settings()
        settings.set_enable_developer_extras(False)
        settings.set_enable_html5_database(False)
        settings.set_enable_html5_local_storage(False)
        settings.set_allow_file_access_from_file_urls(False)
        settings.set_allow_universal_access_from_file_urls(False)
        self.web.connect("decide-policy", self.decide_policy)
        self.web.connect("permission-request", lambda _web, request: (request.deny(), True)[1])
        self.web.connect("context-menu", lambda *_: True)
        self.web.connect("load-changed", self.loaded)
        self.web.connect("web-process-terminated", lambda *_: self.error("The renderer stopped. Try Reload."))
        self.toast.set_child(self.web)
        self.web.load_html(render("# mdview\n\nOpen a Markdown file with **Ctrl+O**.", Path.cwd(), dark=self.style.get_dark()).html, "about:blank")
        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop.connect("drop", self.drop_file)
        self.add_controller(drop)
        self.connect("close-request", self.cleanup)

    def error(self, message):
        self.toast.add_toast(Adw.Toast.new(str(message)))

    def js(self, script, callback=None):
        self.web.evaluate_javascript(script, -1, None, None, None, callback, None)

    def theme_changed(self, *_):
        self.js("document.documentElement.className = " + json.dumps("dark" if self.style.get_dark() else "light"))

    def copy_code(self, _manager, value):
        try:
            index = json.loads(value.to_json(0))
            if type(index) is not int or not 0 <= index < len(self.codes):
                return
            self.get_clipboard().set(self.codes[index])
            self.js(f"window.mdviewCopied({index})")
        except (ValueError, TypeError, GLib.Error):
            self.error("Could not copy this code block.")

    def choose_file(self):
        dialog = Gtk.FileChooserNative(title="Open Markdown", transient_for=self,
                                      action=Gtk.FileChooserAction.OPEN,
                                      accept_label="Open", cancel_label="Cancel")
        markdown = Gtk.FileFilter(name="Markdown files")
        for pattern in ("*.md", "*.markdown", "*.MD"):
            markdown.add_pattern(pattern)
        dialog.add_filter(markdown)
        everything = Gtk.FileFilter(name="All files")
        everything.add_pattern("*")
        dialog.add_filter(everything)

        def response(chooser, result):
            if result == Gtk.ResponseType.ACCEPT:
                self.open_file(chooser.get_file())
            chooser.destroy()

        dialog.connect("response", response)
        dialog.show()

    def open_file(self, file):
        path = file.get_path()
        if path is None:
            self.error("Only local files are supported.")
            return
        self.load(Path(path).absolute(), preserve=False)

    def load(self, path, preserve):
        try:
            document = render(read_document(path), path.parent, dark=self.style.get_dark())
        except (OSError, UnicodeError, ValueError) as exc:
            self.error(f"Cannot open {path.name}: {exc}")
            return
        self.generation += 1
        generation = self.generation

        def display(y=0):
            if self.closed or generation != self.generation:
                return
            changed = self.path != path
            self.path = path
            self.codes = document.codes
            self.restore_y = y
            self.set_title(f"{path.name} — mdview")
            self.reload_button.set_sensitive(True)
            self.web.load_html(document.html, "about:blank")
            if changed:
                self.watch()

        if preserve:
            def position(web, result, _data):
                try:
                    y = web.evaluate_javascript_finish(result).to_double()
                except GLib.Error:
                    y = 0
                display(y)
            self.js("window.scrollY", position)
        else:
            display()

    def loaded(self, _web, event):
        if event == WebKit.LoadEvent.FINISHED:
            self.theme_changed()
            self.js(f"window.scrollTo(0, {float(self.restore_y)})")

    def reload(self):
        if self.path:
            self.load(self.path, preserve=True)

    def watch(self):
        if self.monitor:
            self.monitor.cancel()
        try:
            self.monitor = Gio.File.new_for_path(str(self.path.parent)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
            self.monitor.connect("changed", self.file_changed)
        except GLib.Error as exc:
            self.error(f"Automatic reload unavailable: {exc.message}")

    def file_changed(self, _monitor, file, other, _event):
        if not any(item and item.get_path() == str(self.path) for item in (file, other)):
            return
        if self.pending_reload:
            GLib.source_remove(self.pending_reload)
        self.pending_reload = GLib.timeout_add(250, self.monitored_reload)

    def monitored_reload(self):
        self.pending_reload = 0
        self.reload()
        return GLib.SOURCE_REMOVE

    def decide_policy(self, _web, decision, kind):
        if kind == WebKit.PolicyDecisionType.RESPONSE:
            return False
        action = decision.get_navigation_action()
        uri = action.get_request().get_uri()
        if kind == WebKit.PolicyDecisionType.NAVIGATION_ACTION and (uri == "about:blank" or uri.startswith("about:blank#")):
            decision.use()
            return True
        decision.ignore()
        if action.is_user_gesture() and action.get_navigation_type() == WebKit.NavigationType.LINK_CLICKED:
            parsed = urlsplit(uri)
            if parsed.scheme in ("https", "http", "mailto"):
                Gio.AppInfo.launch_default_for_uri_async(uri, self.get_display().get_app_launch_context(), None, self.link_opened)
            elif parsed.scheme == "file" and parsed.netloc in ("", "localhost"):
                path = Path(unquote(parsed.path))
                if path.suffix.lower() in (".md", ".markdown"):
                    self.open_file(Gio.File.new_for_path(str(path)))
                else:
                    self.error("Only Markdown file links can open here.")
        return True

    def link_opened(self, _source, result):
        try:
            Gio.AppInfo.launch_default_for_uri_finish(result)
        except GLib.Error as exc:
            self.error(f"Cannot open link: {exc.message}")

    def drop_file(self, _target, file, _x, _y):
        self.open_file(file)
        return True

    def cleanup(self, *_):
        self.save_window_state()
        self.closed = True
        if self.monitor:
            self.monitor.cancel()
        if self.pending_reload:
            GLib.source_remove(self.pending_reload)
        self.style.disconnect(self.theme_handler)
        return False

    def save_window_state(self):
        width, height = self.get_default_size()
        try:
            save_state(self.state_path, width, height, self.is_maximized())
        except OSError as exc:
            logging.warning("Could not save window state: %s", exc)


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def do_startup(self):
        Adw.Application.do_startup(self)
        for name, shortcuts, callback in (
            ("open", ["<Primary>o"], lambda *_: self.window().choose_file()),
            ("reload", ["<Primary>r", "F5"], lambda *_: self.window().reload()),
            ("quit", ["<Primary>q"], lambda *_: self.quit()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
            self.set_accels_for_action(f"app.{name}", shortcuts)

    def window(self):
        return self.get_active_window() or Window(self)

    def do_shutdown(self):
        # Application.quit() (Ctrl+Q) does not emit window close-request.
        window = self.get_active_window()
        if window is not None and not window.closed:
            window.save_window_state()
        Adw.Application.do_shutdown(self)

    def do_activate(self):
        self.window().present()

    def do_open(self, files, _count, _hint):
        for file in files:
            window = Window(self)
            window.open_file(file)
            window.present()
