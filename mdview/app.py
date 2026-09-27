# SPDX-FileCopyrightText: 2026 Jochen Schmitt
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

from . import __version__  # noqa: E402
from .i18n import gettext as _  # noqa: E402
from .recent import load_recent, remember_file  # noqa: E402
from .render import UnsupportedDocument, read_document, render  # noqa: E402
from .session import load_session, save_session  # noqa: E402
from .state import load_state, save_state  # noqa: E402

APP_ID = "io.github.mdview.Mdview"


class FindWindow(Gtk.Window):
    """Movable search window for the currently selected document."""

    def __init__(self, parent):
        super().__init__(title=_("Find"), transient_for=parent,
                         modal=False, destroy_with_parent=True, default_width=360)
        self.owner = parent
        self.controller = None
        self.web = None
        self.handlers = []
        self.query = None
        self.set_titlebar(Gtk.HeaderBar(show_title_buttons=True))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        self.entry = Gtk.Entry(placeholder_text=_("Find"), activates_default=True)
        self.entry.connect("changed", self.changed)
        box.append(self.entry)
        self.case_sensitive = Gtk.CheckButton(label=_("Case sensitive"), active=False)
        self.case_sensitive.connect("toggled", self.changed)
        box.append(self.case_sensitive)
        self.message = Gtk.Label(xalign=0)
        box.append(self.message)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda *_unused: self.close())
        buttons.append(cancel)
        self.find_button = Gtk.Button(label=_("Find"))
        self.find_button.add_css_class("suggested-action")
        self.find_button.connect("clicked", self.find)
        buttons.append(self.find_button)
        box.append(buttons)
        self.set_child(box)
        self.set_default_widget(self.find_button)
        self.connect("close-request", self.cleanup)
        self.bind_document()

    def release_document(self):
        for obj, handler in self.handlers:
            obj.disconnect(handler)
        self.handlers.clear()
        if self.controller:
            self.controller.search_finish()
        self.controller = None
        self.web = None

    def bind_document(self):
        self.release_document()
        document = self.owner.active_document
        self.set_title(_("Find in ({name})").format(name=document.path.name)
                       if document and document.path else _("Find"))
        if document and document.path and not document.closed:
            self.web = document.web
            self.controller = self.web.get_find_controller()
            self.handlers = [
                (self.controller, self.controller.connect("found-text", self.found)),
                (self.controller, self.controller.connect("failed-to-find-text", self.not_found)),
                (self.web, self.web.connect("load-changed", self.changed)),
            ]
        self.changed()

    def changed(self, *_unused):
        self.query = None
        self.message.set_text("")
        if self.controller:
            self.controller.search_finish()
        self.find_button.set_sensitive(bool(self.entry.get_text()) and
                                       self.web is not None and not self.web.is_loading())

    def find(self, *_unused):
        text = self.entry.get_text()
        if not text or not self.web or self.web.is_loading():
            return
        self.message.set_text("")
        if text == self.query:
            self.controller.search_next()
        else:
            self.query = text
            options = WebKit.FindOptions.WRAP_AROUND
            if not self.case_sensitive.get_active():
                options |= WebKit.FindOptions.CASE_INSENSITIVE
            self.controller.search(text, options, 2**32 - 1)

    def found(self, *_unused):
        self.message.set_text("")

    def not_found(self, *_unused):
        if self.query is not None:
            self.message.set_text(_("not found"))

    def cleanup(self, *_unused):
        self.release_document()
        self.owner.find_window = None
        return False


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
        self.manager = manager
        self.copy_handler = manager.connect("script-message-received::copy", self.copy_code)
        manager.register_script_message_handler("copy", None)
        self.web = WebKit.WebView(user_content_manager=manager, hexpand=True, vexpand=True,
                                  network_session=WebKit.NetworkSession.new_ephemeral())
        settings = self.web.get_settings()
        settings.set_enable_developer_extras(False)
        settings.set_enable_html5_database(False)
        settings.set_enable_html5_local_storage(False)
        settings.set_allow_file_access_from_file_urls(False)
        settings.set_allow_universal_access_from_file_urls(False)
        self.web_handlers = [
            self.web.connect("decide-policy", self.decide_policy),
            self.web.connect("permission-request", lambda _web, request: (request.deny(), True)[1]),
            self.web.connect("context-menu", lambda *_unused: True),
            self.web.connect("load-changed", self.loaded),
            self.web.connect("web-process-terminated", lambda *_unused: self.error(_("The renderer stopped. Try Reload."))),
        ]
        self.append(self.web)
        self.web.load_html(render("# mdview\n\n" + _("Open a Markdown file with **Ctrl+O**."), Path.cwd(), dark=self.style.get_dark()).html, "about:blank")

    def js(self, script, callback=None):
        if not self.closed:
            self.web.evaluate_javascript(script, -1, None, None, None, callback, None)

    def theme_changed(self, *_unused):
        self.js("document.documentElement.className = " + json.dumps("dark" if self.style.get_dark() else "light"))

    def copy_code(self, _manager, value):
        try:
            index = json.loads(value.to_json(0))
            if type(index) is not int or not 0 <= index < len(self.codes):
                return
            self.get_clipboard().set(self.codes[index])
            self.js(f"window.mdviewCopied({index})")
        except (ValueError, TypeError, GLib.Error):
            self.error(_("Could not copy this code block."))

    def load(self, path, preserve, *, remember=True):
        try:
            document = render(read_document(path), path.parent, dark=self.style.get_dark())
        except UnsupportedDocument as exc:
            self.error(str(exc))
            return False
        except (OSError, UnicodeError, ValueError) as exc:
            self.error(_("Cannot open {name}: {error}").format(name=path.name, error=exc))
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
            if not preserve and remember:
                try:
                    remember_file(self.window.recent_path, path)
                except OSError as exc:
                    logging.warning(_("Could not save recent files: %s"), exc)
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
            self.error(_("Automatic reload unavailable: {error}").format(error=exc.message))

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
                    self.error(_("Only Markdown file links can open here."))
        return True

    def link_opened(self, _source, result):
        try:
            Gio.AppInfo.launch_default_for_uri_finish(result)
        except GLib.Error as exc:
            self.error(_("Cannot open link: {error}").format(error=exc.message))

    def error(self, message):
        if not self.closed:
            self.window.error(message)

    def dispose_document(self):
        if self.closed:
            return
        self.closed = True
        if self.window.find_window and self.window.find_window.web is self.web:
            self.window.find_window.release_document()
        self.generation += 1
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        if self.pending_reload:
            GLib.source_remove(self.pending_reload)
            self.pending_reload = 0
        self.style.disconnect(self.theme_handler)
        for handler in self.web_handlers:
            self.web.disconnect(handler)
        self.web_handlers.clear()
        self.manager.disconnect(self.copy_handler)
        self.manager.unregister_script_message_handler("copy", None)
        self.web.stop_loading()
        self.remove(self.web)
        self.web = None
        self.manager = None
        self.window = None
        self.codes.clear()


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
        self.info_button = Gtk.MenuButton(tooltip_text=_("About mdview"), has_frame=False)
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
        version = Gtk.Label(label=f"v{__version__}")
        version.add_css_class("dim-label")
        info.append(version)
        info.append(Gtk.Label(label=_("simple md file viewer")))
        credits = Gtk.Label(label="© 2026 Jochen Schmitt")
        credits.add_css_class("dim-label")
        info.append(credits)
        info.append(Gtk.LinkButton(uri="https://www.gnu.org/licenses/gpl-3.0.html",
                                   label=_("GNU GPL v3.0 or later")))
        warranty = Gtk.Label(label=_("Free software, provided without warranty."))
        warranty.add_css_class("dim-label")
        info.append(warranty)
        self.info_button.set_popover(Gtk.Popover(child=info))
        header.pack_start(self.info_button)
        open_controls = Gtk.Box(spacing=0)
        open_controls.add_css_class("linked")
        self.recent_button = Gtk.MenuButton(direction=Gtk.ArrowType.DOWN,
                                            tooltip_text=_("Recently opened files"))
        recent_popover = Gtk.Popover(halign=Gtk.Align.START)
        recent_popover.connect("show", self.populate_recent)
        self.recent_button.set_popover(recent_popover)
        open_button = Gtk.Button(label=_("Open"), tooltip_text=_("Open (Ctrl+O)"))
        open_button.connect("clicked", lambda *_unused: self.choose_file())
        open_controls.append(open_button)
        open_controls.append(self.recent_button)
        header.pack_start(open_controls)
        self.new_file_button = Gtk.Button(icon_name="tab-new-symbolic",
                                          tooltip_text=_("Open another file (Ctrl+T)"))
        self.new_file_button.connect("clicked", lambda *_unused: self.choose_file())
        header.pack_start(self.new_file_button)
        self.reload_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_("Reload (Ctrl+R)"), sensitive=False)
        self.reload_button.connect("clicked", lambda *_unused: self.reload())
        header.pack_end(self.reload_button)
        menu = Gio.Menu()
        self.output_actions = []
        self.find_window = None
        for name, label, callback in (
            ("export-pdf", _("Export as PDF"), self.choose_pdf),
            ("find", _("Find"), self.show_find),
            ("print", _("Print"), self.print_document),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.set_enabled(False)
            action.connect("activate", lambda _action, _parameter, run=callback: run())
            self.add_action(action)
            self.output_actions.append(action)
            menu.append(label, f"win.{name}")
        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic",
                                          tooltip_text=_("Main menu"), menu_model=menu)
        header.pack_end(self.menu_button)
        self.print_operations = set()
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
                self.open_file(Gio.File.new_for_path(filename), remember=False)
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
                                   heading=_("Files could not be reopened"),
                                   body=_("The following files could not be restored:"))
        details = Gtk.Label(label="\n\n".join(failures), selectable=True, wrap=True,
                            xalign=0, max_width_chars=65)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                     max_content_height=300, propagate_natural_height=True,
                                     child=details)
        dialog.set_extra_child(scroller)
        dialog.add_response("close", _("Close"))
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
            logging.warning(_("Could not save open tabs: %s"), exc)

    def populate_recent(self, popover):
        items = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                        margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        recent = load_recent(self.recent_path)
        if not recent:
            items.append(Gtk.Label(label=_("No recently opened files"), margin_top=12,
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
        dialog = Gtk.FileChooserDialog(title=_("Open Markdown"), transient_for=self,
                                       modal=True, destroy_with_parent=True, resizable=True,
                                       action=Gtk.FileChooserAction.OPEN, select_multiple=True)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL, _("Open"), Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        surface = self.get_surface()
        monitor = self.get_display().get_monitor_at_surface(surface) if surface else None
        if monitor:
            geometry = monitor.get_geometry()
            width, height = geometry.width * 2 // 3, geometry.height * 2 // 3
        else:
            width, height = 800, 600
        markdown = Gtk.FileFilter(name=_("Markdown files"))
        for pattern in ("*.md", "*.markdown", "*.MD"):
            markdown.add_pattern(pattern)
        dialog.add_filter(markdown)
        everything = Gtk.FileFilter(name=_("All files"))
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

    def selection_changed(self, *_unused):
        document = self.active_document
        path = document.path if document else None
        self.heading.set_title(path.name if path else "mdview")
        self.heading.set_subtitle(str(path.parent) if path else "")
        self.heading.set_tooltip_text(str(path) if path else None)
        self.set_title(f"{path.name} — mdview" if path else "mdview")
        self.reload_button.set_sensitive(path is not None)
        for action in self.output_actions:
            action.set_enabled(path is not None)
        if self.find_window:
            self.find_window.bind_document()

    def show_find(self):
        if not self.active_document or not self.active_document.path:
            return
        if self.find_window is None:
            self.find_window = FindWindow(self)
        self.find_window.present()
        self.find_window.entry.grab_focus()

    def choose_pdf(self):
        document = self.active_document
        if not document or not document.path:
            return
        if document.web.is_loading():
            self.error(_("Please wait until the document has finished loading."))
            return
        dialog = Gtk.FileChooserDialog(title=_("Export as PDF"), transient_for=self,
                                       modal=True, destroy_with_parent=True,
                                       action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL, _("Export"), Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        dialog.set_current_name(document.path.with_suffix(".pdf").name)
        dialog.set_current_folder(Gio.File.new_for_path(str(document.path.parent)))
        pdf_filter = Gtk.FileFilter(name=_("PDF documents"))
        pdf_filter.add_pattern("*.pdf")
        dialog.add_filter(pdf_filter)

        def response(chooser, result):
            if result == Gtk.ResponseType.ACCEPT:
                target = chooser.get_file()
                if target:
                    self.export_pdf(document, target)
            chooser.destroy()

        dialog.connect("response", response)
        dialog.present()

    def export_pdf(self, document, target):
        if document.closed or document.web.is_loading():
            self.error(_("The document is no longer available or is still loading."))
            return
        filename = target.get_path()
        if filename is None:
            self.error(_("Choose a local file for PDF export."))
            return
        if Path(filename).resolve() == document.path.resolve():
            self.error(_("Choose a different filename to preserve the source document."))
            return
        operation = WebKit.PrintOperation.new(document.web)
        settings = Gtk.PrintSettings()
        settings.set_printer("Print to File")
        settings.set("output-file-format", "pdf")
        settings.set("output-uri", target.get_uri())
        operation.set_print_settings(settings)
        operation.set_page_setup(Gtk.PageSetup())
        self.track_print(operation, _("Could not export PDF"), _("PDF exported: {name}").format(name=Path(filename).name))
        operation.print_()

    def print_document(self):
        document = self.active_document
        if not document or not document.path:
            return
        if document.web.is_loading():
            self.error(_("Please wait until the document has finished loading."))
            return
        operation = WebKit.PrintOperation.new(document.web)
        cleanup = self.track_print(operation, _("Could not print document"))
        # WebKit handles the selected printer, paper size, margins and pagination.
        response = operation.run_dialog(self)
        if response == WebKit.PrintOperationResponse.CANCEL:
            cleanup()

    def track_print(self, operation, error_prefix, success_message=None):
        self.print_operations.add(operation)
        errors = []

        def cleanup():
            if operation in self.print_operations:
                self.print_operations.remove(operation)
                operation.disconnect(failed_handler)
                operation.disconnect(finished_handler)

        def failed(_operation, error):
            errors.append(error.message)
            if not self.closed:
                self.error(f"{error_prefix}: {error.message}")

        def finished(_operation):
            cleanup()
            if success_message and not errors and not self.closed:
                self.toast.add_toast(Adw.Toast.new(success_message))

        failed_handler = operation.connect("failed", failed)
        finished_handler = operation.connect("finished", finished)
        return cleanup

    def document_changed(self, document):
        for index in range(self.tab_view.get_n_pages()):
            page = self.tab_view.get_nth_page(index)
            if page.get_child() is document:
                page.set_title(document.path.name)
                page.set_tooltip(str(document.path))
                break
        if document is self.active_document:
            self.selection_changed()

    def open_file(self, file, *, remember=True):
        filename = file.get_path()
        if filename is None:
            self.error(_("Only local files are supported."))
            return False
        path = Path(filename).absolute()
        for index in range(self.tab_view.get_n_pages()):
            page = self.tab_view.get_nth_page(index)
            if page.get_child().path == path:
                self.tab_view.set_selected_page(page)
                if remember:
                    try:
                        remember_file(self.recent_path, path)
                    except OSError as exc:
                        logging.warning(_("Could not save recent files: %s"), exc)
                return True
        document = self.active_document
        new_document = document is None or document.path is not None
        if new_document:
            document = DocumentView(self)
        if not document.load(path, preserve=False, remember=remember):
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

    def cleanup(self, *_unused):
        if not self.closed:
            self.save_window_state()
            self.save_session()
            self.closed = True
            if self.find_window:
                self.find_window.close()
            for document in self.documents():
                document.dispose_document()
        return False

    def save_window_state(self):
        width, height = self.get_default_size()
        try:
            save_state(self.state_path, width, height, self.is_maximized())
        except OSError as exc:
            logging.warning(_("Could not save window state: %s"), exc)


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.set_accels_for_action("win.export-pdf", ["<Primary>e"])
        self.set_accels_for_action("win.find", ["<Primary>f"])
        self.set_accels_for_action("win.print", ["<Primary>p"])
        for name, shortcuts, callback in (
            ("open", ["<Primary>o"], lambda *_unused: self.window().choose_file()),
            ("new-tab", ["<Primary>t"], lambda *_unused: self.window().choose_file()),
            ("close-tab", ["<Primary>w"], lambda *_unused: self.window().close_current_tab()),
            ("reload", ["<Primary>r", "F5"], lambda *_unused: self.window().reload()),
            ("quit", ["<Primary>q"], lambda *_unused: self.quit()),
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
