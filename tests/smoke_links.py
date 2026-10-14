# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Real WebKit link clicks/context menus; needs X11 and libXtst (xvfb works)."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

os.environ["LC_ALL"] = "C.UTF-8"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdview.app import Application, Gio, WebKit, Window
from mdview.recent import load_recent
from gui_helpers import X11Mouse, clipboard_text, javascript, wait_for


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    os.environ["XDG_STATE_HOME"] = str(root / "state")
    source, target = root / "index.md", root / "docs" / "café architecture.md"
    target.parent.mkdir()
    target.write_text('# Architecture\n\n' + 'Paragraph.\n\n' * 100 + '# Details\n\nEnd.\n')
    (root / "alias.md").symlink_to(target)
    (root / "loop.md").symlink_to("loop.md")
    (root / "binary.md").write_bytes(b'binary\0')
    unreadable = root / "unreadable.md"
    unreadable.write_text('# Unreadable')
    unreadable.chmod(0)
    url = "https://example.invalid/full/path?q=a%20b&x=one%2Ftwo#section"
    http_url = url.replace("https:", "http:", 1)
    source.write_text(f'''# Index

[external]({url})

[HTTP]({http_url})

[architecture](docs/caf%C3%A9%20architecture.md#details)

[alias](alias.md "Alias target")

[missing](missing.md)

[binary](binary.md)

[unreadable](unreadable.md)

[unsupported](unsupported.txt)

[loop](loop.md)

[scheme](ftp://example.invalid/a.md)

[anchor](#bottom)

```python
print("copy still works")
```

''' + 'Paragraph.\n\n' * 100 + '# Bottom\n\nEnd.\n')
    app = Application()
    app.set_application_id("io.github.mdview.LinkTest")
    app.register(None)
    window = Window(app)
    window.present()
    window.open_file(Gio.File.new_for_path(str(source)))
    document = window.active_document
    wait_for(lambda: not document.web.is_loading() and document.web.get_width() > 0)
    mouse = X11Mouse(window)
    errors = []
    window.error = errors.append
    menus = []

    def capture_menu(_web, menu, hit_test):
        # Inspect the menu built by the app's handler from an actual WebKit hit.
        menus.append((menu, hit_test.get_link_uri()))
        return True  # Suppress presentation so the test can activate its action.

    document.web.connect("context-menu", capture_menu)

    def copy_link(selector, expected):
        menus.clear()
        mouse.click(document, selector, button=3)
        wait_for(lambda: bool(menus), "Right-click did not produce a WebKit link menu")
        menu, uri = menus[-1]
        assert menu.get_n_items() == 1
        action = menu.get_item_at_position(0).get_gaction()
        assert action.get_name() == "copy-link"
        action.activate(None)
        assert clipboard_text(window) == expected
        assert window.active_document is document
        return uri

    with patch.object(Gio.AppInfo, "launch_default_for_uri_async") as launch:
        for scheme, expected in (("https", url), ("http", http_url)):
            selector = f'a[href^="{scheme}:"]'
            assert copy_link(selector, expected) == expected
            assert not launch.called
            mouse.click(document, selector)
            wait_for(lambda: launch.called, "External click did not launch the desktop handler")
            assert launch.call_args.args[0] == expected
            assert document.web.get_uri() == "about:blank"
            launch.reset_mock()
        # Application evaluate_javascript itself grants a gesture in WebKit;
        # exercise the policy's untrusted branch explicitly instead.
        action = Mock()
        action.get_request.return_value.get_uri.return_value = url
        action.is_user_gesture.return_value = False
        decision = Mock()
        decision.get_navigation_action.return_value = action
        assert document.decide_policy(document.web, decision, WebKit.PolicyDecisionType.NAVIGATION_ACTION)
        decision.ignore.assert_called_once()
        assert not launch.called

    assert copy_link('a[href$="#details"]', str(target)) == target.as_uri().replace('file:', 'mdview:', 1) + '#details'
    assert window.tab_view.get_n_pages() == 1
    mouse.click(document, 'a[href$="#details"]')
    wait_for(lambda: window.active_document.path == target, "Local link did not open in mdview")
    target_view = window.active_document
    wait_for(lambda: not target_view.web.is_loading())
    wait_for(lambda: javascript(target_view, 'window.scrollY') > 1000,
             "Cross-file heading was not restored")
    assert window.tab_view.get_n_pages() == 2
    assert load_recent(window.recent_path)[0] == str(target)
    assert window.open_file(Gio.File.new_for_path(str(source)))
    mouse.click(document, 'a[title="Alias target"]')
    wait_for(lambda: window.active_document is target_view, "Alias opened a duplicate tab")
    assert window.tab_view.get_n_pages() == 2
    window.open_file(Gio.File.new_for_path(str(source)))
    mouse.click(document, 'a[href$="#details"]')
    wait_for(lambda: window.active_document is target_view, "Existing tab was not selected")
    assert window.tab_view.get_n_pages() == 2
    window.open_file(Gio.File.new_for_path(str(source)))

    # Missing, binary, unreadable and unsupported links leave the document intact.
    history = load_recent(window.recent_path)
    for name in ("missing.md", "binary.md", "unreadable.md", "unsupported.txt", "loop.md"):
        errors.clear()
        mouse.click(document, f'a[href$="{name}"]')
        wait_for(lambda: bool(errors), f"No error for {name}")
        assert window.active_document is document and window.tab_view.get_n_pages() == 2
        assert load_recent(window.recent_path) == history
    mouse.click(document, 'a[href="#bottom"]')
    wait_for(lambda: document.web.get_uri() == 'about:blank#bottom', "In-page anchor did not navigate")
    assert javascript(document, 'window.scrollY') > 1000
    assert copy_link('a[href="#bottom"]', str(source)) == 'about:blank#bottom'

    # Arbitrary schemes and non-links never gain browser context-menu actions.
    for uri in ('ftp://example.invalid/a.md', 'file:///etc/passwd', 'file://remote/tmp/a.md',
                'file:///tmp/a.md?query', 'javascript:alert(1)'):
        menu = WebKit.ContextMenu.new()
        hit = WebKit.HitTestResult(context=WebKit.HitTestResultContext.LINK, link_uri=uri)
        assert document.context_menu(document.web, menu, hit)
        assert menu.get_n_items() == 0
    with patch.object(Gio.AppInfo, "launch_default_for_uri_async") as launch:
        mouse.click(document, 'a[href^="ftp:"]')
        javascript(document, 'true')
        assert not launch.called and window.active_document is document
    mouse.click(document, 'button[data-copy="0"]')
    wait_for(lambda: clipboard_text(window) == 'print("copy still works")\n',
             "Code Copy button stopped working")
    assert javascript(document, 'document.querySelector("button[data-copy]").textContent') == 'Copied'
    mouse.close()
    unreadable.chmod(0o600)
    window.close()
    print("PASS: trusted HTTP clicks, original-URL/local-path clipboard, native link hit tests/context actions, local tabs/aliases/anchors, missing/unreadable/invalid links, restricted schemes and code Copy")
