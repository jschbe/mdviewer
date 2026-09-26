"""Optional integration test: run from the project root with a working display."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdview.app import Adw, Application, Gio, GLib, WebKit, Window

temporary = tempfile.TemporaryDirectory()
path = Path(temporary.name) / "smoke.md"
path.write_text('# Smoke\n\n```python\nprint("日本語")\n```\n\n' + 'Paragraph.\n\n' * 150)
app = Application()
app.set_application_id("io.github.mdview.SmokeTest")
state = {"phase": 0, "ok": False}


def fail(message):
    print(message, file=sys.stderr)
    app.quit()
    return GLib.SOURCE_REMOVE


def activated(_app):
    window = app.get_active_window() or Window(app)
    state["window"] = window

    def loaded(_web, event):
        if event != WebKit.LoadEvent.FINISHED:
            return
        if state["phase"] == 0:
            state["phase"] = 1
            window.js('window.scrollTo(0, 600); window.webkit.messageHandlers.copy.postMessage(0)')
            GLib.timeout_add(300, check_clipboard)
        elif state["phase"] == 2:
            state["phase"] = 3
            window.style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            window.js('const attack = document.createElement("script"); attack.textContent = "window.untrustedRan = true"; document.body.append(attack)')
            GLib.timeout_add(300, check_reload)

    window.web.connect("load-changed", loaded)
    window.open_file(Gio.File.new_for_path(str(path)))
    window.present()


def check_clipboard():
    window = state["window"]

    def copied(clipboard, result):
        text = clipboard.read_text_finish(result)
        if text != 'print("日本語")\n':
            fail(f"Clipboard mismatch: {text!r}")
            return
        state["phase"] = 2
        replacement = path.with_suffix('.tmp')
        replacement.write_text(path.read_text().replace('# Smoke', '# Updated'))
        replacement.replace(path)

    window.get_clipboard().read_text_async(None, copied)
    return GLib.SOURCE_REMOVE


def check_reload():
    window = state["window"]

    def checked(web, result, _data):
        value = web.evaluate_javascript_finish(result).to_boolean()
        if not value:
            fail("Reload, scroll restoration, theme or CSP check failed")
            return
        state["ok"] = True
        print("PASS: native window, WebKit bridge, UTF-8 desktop clipboard, atomic-save reload, scroll preservation, dark theme, CSP script blocking")
        window.close()
        app.quit()

    window.js('document.querySelector("h1").textContent === "Updated" && Math.abs(window.scrollY - 600) < 5 && document.documentElement.className === "dark" && window.untrustedRan === undefined', checked)
    return GLib.SOURCE_REMOVE


app.connect("activate", activated)
GLib.timeout_add_seconds(20, lambda: fail("GUI smoke test timed out"))
app.run(["mdview-smoke"])
temporary.cleanup()
raise SystemExit(0 if state["ok"] else 1)
