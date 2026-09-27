# SPDX-FileCopyrightText: 2026 Jochen Schmitt and mdview contributors
# SPDX-License-Identifier: GPL-3.0-or-later

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

from .recent import load_recent, remember_file  # noqa: E402
from .render import UnsupportedDocument, read_document, render  # noqa: E402
from .session import load_session, save_session  # noqa: E402
from .state import load_state, save_state  # noqa: E402

APP_ID = "io.github.mdview.Mdview"


class DocumentView(Gtk.Box):
    """One document, with independent rendering, scroll state and monitoring."""

    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        self.window = window
        self.path = None
        self.codes = []
        self.monitor = None
        self.pending_reload = 0
        self.generation = 0
        self.restore_y = 0
        self.closed = False
        self.style = Adw.StyleManager.get_default()
        self.theme_handler = self.style.connect("notify::dark", self.theme_changed)

        manager = WebKit.UserContentManager()
        manager.connect("script-message-received::copy", self.copy_code)
        manager.register_script_message_handler("copy", None)
        self.web = WebKit.WebView(user_content_manager=manager, hexpand=True, vexpand=True,
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
        self.append(self.web)
        self.web.load_html(render("# mdview\n\nOpen a Markdown file with **Ctrl+O**.", Path.cwd(), dark=self.style.get_dark()).html, "about:blank")

    def js(self, script, callback=None):
        if not self.closed:
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

    def load(self, path, preserve):
        try:
            document = render(read_document(path), path.parent, dark=self.style.get_dark())
        except UnsupportedDocument as exc:
            self.error(str(exc))
            return False
        except (OSError, UnicodeError, ValueError) as exc:
            self.error(f"Cannot open {path.name}: {exc}")
            return False
        self.generation += 1
        generation = self.generation

        def display(y=0):
            if self.closed or generation != self.generation:
                return
            changed = self.path != path
            self.path = path
            self.codes = document.codes
            self.restore_y = y
            self.window.document_changed(self)
            self.web.load_html(document.html, "about:blank")
            if not preserve:
                try:
                    remember_file(self.window.recent_path, path)
                except OSError as exc:
                    logging.warning("Could not save recent files: %s", exc)
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

        return True

    def loaded(self, _web, event):
        if not self.closed and event == WebKit.LoadEvent.FINISHED:
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
                    self.window.open_file(Gio.File.new_for_path(str(path)))
                else:
                    self.error("Only Markdown file links can open here.")
        return True

    def link_opened(self, _source, result):
        try:
            Gio.AppInfo.launch_default_for_uri_finish(result)
        except GLib.Error as exc:
            self.error(f"Cannot open link: {exc.message}")

    def error(self, message):
        self.window.error(message)

    def dispose_document(self):
        if self.closed:
            return
        self.closed = True
        self.generation += 1
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        if self.pending_reload:
            GLib.source_remove(self.pending_reload)
            self.pending_reload = 0
        self.style.disconnect(self.theme_handler)
        self.web.stop_loading()


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        self.state_path = Path(GLib.get_user_state_dir()) / "mdview" / "window.json"
        self.recent_path = self.state_path.with_name("recent.json")
        self.session_path = self.state_path.with_name("session.json")
        self.restore_errors = None
        self.restoring_path = None
        state = load_state(self.state_path)
        super().__init__(application=app, title="mdview",
                         default_width=state["width"], default_height=state["height"])
        if state["maximized"]:
            self.maximize()
        self.closed = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        # Our info button replaces the decoration's application icon/menu.
        layout = self.get_settings().get_property("gtk-decoration-layout")
        header.set_decoration_layout(":".join(
            ",".join(button for button in side.split(",")
                     if button not in ("icon", "menu"))
            for side in layout.split(":")
        ))
        self.info_button = Gtk.MenuButton(tooltip_text="About mdview", has_frame=False)
        icon_path = Path(__file__).resolve().parent.parent / "data" / f"{APP_ID}.svg"
        icon = (Gtk.Image.new_from_file(str(icon_path)) if icon_path.is_file()
                else Gtk.Image.new_from_icon_name(APP_ID))
        icon.set_pixel_size(24)
        self.info_button.set_child(icon)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_top=16, margin_bottom=16, margin_start=24, margin_end=24)
        title = Gtk.Label(label="mdview")
        title.add_css_class("title-1")
        info.append(title)
        info.append(Gtk.Label(label="simple md file viewer"))
        credits = Gtk.Label(label="© 2026 Jochen Schmitt")
        credits.add_css_class("dim-label")
        info.append(credits)
        info.append(Gtk.LinkButton(uri="https://www.gnu.org/licenses/gpl-3.0.html",
                                   label="GNU GPL v3.0 or later"))
        warranty = Gtk.Label(label="Free software, provided without warranty.")
        warranty.add_css_class("dim-label")
        info.append(warranty)
        self.info_button.set_popover(Gtk.Popover(child=info))
        header.pack_start(self.info_button)
        open_controls = Gtk.Box(spacing=0)
        open_controls.add_css_class("linked")
        self.recent_button = Gtk.MenuButton(direction=Gtk.ArrowType.DOWN,
                                            tooltip_text="Recently opened files")
        recent_popover = Gtk.Popover(halign=Gtk.Align.START)
        recent_popover.connect("show", self.populate_recent)
        self.recent_button.set_popover(recent_popover)
        open_button = Gtk.Button(label="Open", tooltip_text="Open (Ctrl+O)")
        open_button.connect("clicked", lambda *_: self.choose_file())
        open_controls.append(open_button)
        open_controls.append(self.recent_button)
        header.pack_start(open_controls)
        self.new_file_button = Gtk.Button(icon_name="tab-new-symbolic",
                                          tooltip_text="Open another file (Ctrl+T)")
        self.new_file_button.connect("clicked", lambda *_: self.choose_file())
        header.pack_start(self.new_file_button)
        self.reload_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload (Ctrl+R)", sensitive=False)
        self.reload_button.connect("clicked", lambda *_: self.reload())
        header.pack_end(self.reload_button)
        box.append(header)
        self.heading = Adw.WindowTitle(title="mdview")
        header.set_title_widget(self.heading)
        self.tab_view = Adw.TabView(vexpand=True)
        self.tab_bar = Adw.TabBar(view=self.tab_view, autohide=True)
        box.append(self.tab_bar)
        self.toast = Adw.ToastOverlay(vexpand=True)
        box.append(self.toast)
        self.toast.set_child(self.tab_view)
        self.set_content(box)
        self.tab_view.connect("notify::selected-page", self.selection_changed)
        self.tab_view.connect("close-page", self.close_page)
        self.add_document()

        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop.connect("drop", self.drop_file)
        self.add_controller(drop)
        files_drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        files_drop.connect("drop", self.drop_files)
        self.add_controller(files_drop)
        self.connect("close-request", self.cleanup)
        self.restore_session()

    def error(self, message):
        if self.restore_errors is not None:
            self.restore_errors.append(f"{self.restoring_path}\n{message}")
            return
        self.toast.add_toast(Adw.Toast.new(str(message)))

    def restore_session(self):
        session = load_session(self.session_path)
        self.restore_errors = []
        try:
            for filename in session["files"]:
                self.restoring_path = filename
                self.open_file(Gio.File.new_for_path(filename))
            for index in range(self.tab_view.get_n_pages()):
                page = self.tab_view.get_nth_page(index)
                if str(page.get_child().path) == session["active"]:
                    self.tab_view.set_selected_page(page)
                    break
        finally:
            failures = self.restore_errors
            self.restore_errors = None
            self.restoring_path = None
        if failures:
            GLib.idle_add(self.show_restore_errors, failures)

    def show_restore_errors(self, failures):
        if self.closed:
            return GLib.SOURCE_REMOVE
        dialog = Adw.MessageDialog(transient_for=self, modal=True, destroy_with_parent=True,
                                   heading="Files could not be reopened",
                                   body="The following files could not be restored:")
        details = Gtk.Label(label="\n\n".join(failures), selectable=True, wrap=True,
                            xalign=0, max_width_chars=65)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                     max_content_height=300, propagate_natural_height=True,
                                     child=details)
        dialog.set_extra_child(scroller)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        dialog.present()
        return GLib.SOURCE_REMOVE

    def save_session(self):
        paths = [str(document.path) for document in self.documents() if document.path]
        document = self.active_document
        active = str(document.path) if document and document.path else None
        try:
            save_session(self.session_path, paths, active)
        except OSError as exc:
            logging.warning("Could not save open tabs: %s", exc)

    def populate_recent(self, popover):
        items = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                        margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        recent = load_recent(self.recent_path)
        if not recent:
            items.append(Gtk.Label(label="No recently opened files", margin_top=12,
                                   margin_bottom=12))
        for filename in recent:
            path = Path(filename)
            label = Gtk.Label(label=path.name, xalign=0, wrap=False, single_line_mode=True)
            button = Gtk.Button(child=label, has_frame=False)
            button.connect("clicked", self.open_recent, filename)
            items.append(button)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                     propagate_natural_width=True, max_content_height=400,
                                     propagate_natural_height=True, child=items)
        popover.set_child(scroller)

    def open_recent(self, _button, filename):
        self.recent_button.popdown()
        self.open_file(Gio.File.new_for_path(filename))

    def choose_file(self):
        # Native/portal choosers do not expose window sizing to the application.
        dialog = Gtk.FileChooserDialog(title="Open Markdown", transient_for=self,
                                       modal=True, destroy_with_parent=True, resizable=True,
                                       action=Gtk.FileChooserAction.OPEN, select_multiple=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        surface = self.get_surface()
        monitor = self.get_display().get_monitor_at_surface(surface) if surface else None
        if monitor:
            geometry = monitor.get_geometry()
            width, height = geometry.width * 2 // 3, geometry.height * 2 // 3
        else:
            width, height = 800, 600
        markdown = Gtk.FileFilter(name="Markdown files")
        for pattern in ("*.md", "*.markdown", "*.MD"):
            markdown.add_pattern(pattern)
        dialog.add_filter(markdown)
        everything = Gtk.FileFilter(name="All files")
        everything.add_pattern("*")
        dialog.add_filter(everything)

        def response(chooser, result):
            if result == Gtk.ResponseType.ACCEPT:
                files = chooser.get_files()
                for index in range(files.get_n_items()):
                    self.open_file(files.get_item(index))
            chooser.destroy()

        dialog.connect("response", response)
        dialog.present()
        # Apply after GTK restores its saved chooser size during presentation.
        dialog.unmaximize()
        dialog.unfullscreen()
        dialog.set_default_size(width, height)

    @property
    def active_document(self):
        page = self.tab_view.get_selected_page()
        return page.get_child() if page else None

    def documents(self):
        return [self.tab_view.get_nth_page(index).get_child()
                for index in range(self.tab_view.get_n_pages())]

    def add_document(self, document=None):
        document = document or DocumentView(self)
        page = self.tab_view.append(document)
        page.set_title(document.path.name if document.path else "mdview")
        if document.path:
            page.set_tooltip(str(document.path))
        self.tab_view.set_selected_page(page)
        self.selection_changed()
        return document

    def selection_changed(self, *_):
        document = self.active_document
        path = document.path if document else None
        self.heading.set_title(path.name if path else "mdview")
        self.heading.set_subtitle(str(path.parent) if path else "")
        self.heading.set_tooltip_text(str(path) if path else None)
        self.set_title(f"{path.name} — mdview" if path else "mdview")
        self.reload_button.set_sensitive(path is not None)

    def document_changed(self, document):
        for index in range(self.tab_view.get_n_pages()):
            page = self.tab_view.get_nth_page(index)
            if page.get_child() is document:
                page.set_title(document.path.name)
                page.set_tooltip(str(document.path))
                break
        if document is self.active_document:
            self.selection_changed()

    def open_file(self, file):
        filename = file.get_path()
        if filename is None:
            self.error("Only local files are supported.")
            return False
        path = Path(filename).absolute()
        for index in range(self.tab_view.get_n_pages()):
            page = self.tab_view.get_nth_page(index)
            if page.get_child().path == path:
                self.tab_view.set_selected_page(page)
                try:
                    remember_file(self.recent_path, path)
                except OSError as exc:
                    logging.warning("Could not save recent files: %s", exc)
                return True
        document = self.active_document
        new_document = document is None or document.path is not None
        if new_document:
            document = DocumentView(self)
        if not document.load(path, preserve=False):
            if new_document:
                document.dispose_document()
            return False
        if new_document:
            self.add_document(document)
        return True

    def reload(self):
        if self.active_document:
            self.active_document.reload()

    def close_page(self, view, page):
        page.get_child().dispose_document()
        if view.get_n_pages() == 1 and not self.closed:
            self.add_document()
        view.close_page_finish(page, True)
        return True

    def close_current_tab(self):
        page = self.tab_view.get_selected_page()
        if page:
            self.tab_view.close_page(page)

    def drop_file(self, _target, file, _x, _y):
        return self.open_file(file)

    def drop_files(self, _target, files, _x, _y):
        opened = False
        for file in files.get_files():
            opened = self.open_file(file) or opened
        return opened

    def cleanup(self, *_):
        if not self.closed:
            self.save_window_state()
            self.save_session()
            self.closed = True
            for document in self.documents():
                document.dispose_document()
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
            ("new-tab", ["<Primary>t"], lambda *_: self.window().choose_file()),
            ("close-tab", ["<Primary>w"], lambda *_: self.window().close_current_tab()),
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
        active = self.get_active_window()
        windows = [window for window in self.get_windows() if isinstance(window, Window)]
        # Save the active window last, matching the existing state behavior.
        for window in sorted(windows, key=lambda item: item is active):
            window.cleanup()
        Adw.Application.do_shutdown(self)

    def do_activate(self):
        self.window().present()

    def do_open(self, files, _count, _hint):
        window = self.window()
        for file in files:
            window.open_file(file)
        window.present()
