# mdview

A small, read-only Markdown viewer for GNOME, built with Python, GTK4,
libadwaita and WebKitGTK 6.0. No editor, accounts, telemetry or services.

## License

Copyright © 2026 Jochen Schmitt. Developed with Codex.

mdview is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version
(`GPL-3.0-or-later`).

mdview is distributed without any warranty, including the implied warranties of
merchantability or fitness for a particular purpose. See [LICENSE](LICENSE) for
the full GNU GPL text. It is included in source archives and installed at
`/usr/share/licenses/mdview/LICENSE` by the Arch package.

## Install dependencies (Arch Linux)

```sh
sudo pacman -S --needed python python-gobject gtk4 libadwaita webkitgtk-6.0 python-markdown-it-py python-pygments
```

All runtime dependencies are in the official repositories; no AUR packages
or pip environment are needed. WebKitGTK is the largest dependency.

## Run from this checkout

```sh
python -m mdview README.md
# or
./bin/mdview README.md
# or open the file chooser after launch
make run
```

Open: **Ctrl+O**. Open another file: **Ctrl+T** or the **+** button.
Close the active tab: **Ctrl+W**. Reload: **Ctrl+R** or **F5**. Quit: **Ctrl+Q**.
Click the application icon in the upper-left corner for app information and credits.
The **Open** button opens a resizable file chooser, initially about two thirds of
the current monitor's width and height. The down-arrow button to its right lists
the ten most recently opened files, newest first; click an entry to reopen it in
the current window. Entries show filenames only, without folder paths. Refresh
is on the right of the header bar.
Open files appear in separate tabs within the same window. The tab bar is hidden
when only one file is open. The **Open** and **+** buttons both offer a file chooser
with multiple selection; dropping files onto the window or passing several files
on the command line also opens tabs. Opening an already open file selects its tab.
The header shows the active filename with its absolute folder path underneath;
hover over the title or a tab to see the full file path. Each tab keeps its own
scroll position, code blocks and file monitor. Close tabs with their close button
or **Ctrl+W**; closing the last one returns to the welcome view.

Open tabs, their order and the active tab are saved when closing the window or
quitting with **Ctrl+Q**, then restored on the next launch. Missing, unreadable or
unsupported files are skipped and listed together in an error dialog; the other
files still open. Files passed on the command line open alongside the restored
tabs. The session is stored in `$XDG_STATE_HOME/mdview/session.json` (normally
`~/.local/state/mdview/session.json`). Delete it to reset the saved tabs, or close
all tabs before quitting to start with an empty session. Scroll positions are
not saved across restarts.
GNOME's light/dark preference is followed automatically. Each fenced code block
has a Copy button; the desktop clipboard receives only the original code text.
Markdown and plain text files must be UTF-8 (an optional BOM is accepted).
Content is checked regardless of the filename extension: invalid UTF-8, binary
control characters, and PDF headers are rejected with “File cannot be displayed”.
This is a basic content check, not a complete file-format detector. Rejected files
leave the current document and recent-file history unchanged.

The window's normal size and maximized state are restored on launch. State is
saved to `$XDG_STATE_HOME/mdview/window.json` (normally
`~/.local/state/mdview/window.json`) on close or Ctrl+Q. With multiple windows,
the last closed window wins; Ctrl+Q saves the active window. Missing or invalid
state falls back to the default size. Delete this file to reset the window.

Recent files are saved separately to `$XDG_STATE_HOME/mdview/recent.json`
(normally `~/.local/state/mdview/recent.json`) and shared by all mdview windows.
The order is always most recently opened to oldest. Explicitly reopening a file,
including one already in a tab, moves it to the front. Automatic reloads and
session restoration do not change the history. Restored tabs retain their saved
tab order, independently of this history.
Delete this file to clear the history. Missing files show an error when selected
and leave the current document visible.

Each document's parent directory is monitored, including atomic file replacements,
even when its tab is inactive.
Reloads preserve the vertical pixel offset; substantial edits can move the text
at that offset. An unreadable file shows a toast and leaves the previous document
visible. Relative Markdown links open or select a tab in the current window; heading anchors
scroll within the document, and HTTP/HTTPS/mail links use the desktop handler.

## Tests

```sh
make test
# Optional real GTK/WebKit integration test, in a desktop session:
python tests/smoke_gui.py
python tests/smoke_tabs.py
python tests/smoke_session.py
# Headless alternative, if xorg-server-xvfb and xorg-xauth are installed:
GDK_BACKEND=x11 GSETTINGS_BACKEND=memory xvfb-run -a python tests/smoke_gui.py
GDK_BACKEND=x11 GSETTINGS_BACKEND=memory xvfb-run -a python tests/smoke_tabs.py
GDK_BACKEND=x11 GSETTINGS_BACKEND=memory xvfb-run -a python tests/smoke_session.py
```

Parser and state tests use Python's unittest and the runtime parser/highlighter.
The packaging test also uses `make`, `tar` and `install`, and skips itself if
these tools are unavailable. It builds a source archive and stages installation
in a temporary directory, including paths with spaces; it does not install on
the system.
The integration test checks the actual WebKit message bridge, desktop clipboard,
atomic-save monitoring, scroll preservation, theme updates and CSP script blocking.
It temporarily changes the clipboard.
The tab integration test checks single/multiple-tab layouts, file locations,
independent scrolling and monitoring, duplicate/invalid opens, and memory release
when closing tabs.
The session integration test covers restored tab order and selection, closed tabs,
unchanged recent-file history, and errors for files that can no longer be opened.

## Build and install packages

Install `base-devel` if your system is not already configured for `makepkg`:

```sh
sudo pacman -S --needed base-devel
./build.sh
```

Run `build.sh` as your normal user. It removes old generated archives, signatures,
logs, `.deb` files and the `src/` and `pkg/` build directories from `packaging/`,
preserving `PKGBUILD`. It builds an Arch package by default; `-deb` selects a
Debian package instead. Without `-i`, it builds without installing. The script
stops if any command fails and can be invoked from any working directory.
The PKGBUILD disables separate debug packages, including when debug builds are
enabled in your system's `makepkg` configuration.

```sh
./build.sh -i       # Build and install; skip an already installed version.
./build.sh -i -f    # Build and install, even if the same version is installed.
./build.sh -deb     # Build packaging/mdview_<version>-1_all.deb.
./build.sh -deb -i  # Build the .deb and install it with sudo dpkg -i.
./build.sh -h       # Show help without building or installing.
```

`-install` is an alias for `-i`; `-force` is an alias for `-f`. For Arch,
installation uses `sudo pacman -U --needed`; the force option omits `--needed`.
With `-deb`, installation uses `sudo dpkg -i`, which also permits reinstalling
the same version; `-f` has no effect in this mode. Both installation commands
may prompt for your password. The force option alone never enables installation.

The `-deb` build requires `dpkg-deb` (from `dpkg`, version 1.19.0 or newer),
`make`, `tar`, Python 3.10 or newer, `python3-markdown-it`, and `python3-pygments`.
It runs the unit tests and packages the application, desktop entry, icon and GPL
license without creating a debug package. The package declares its runtime
dependencies, including `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1` and
`gir1.2-webkit-6.0`; the target distribution must provide these packages.
`dpkg -i` does not download missing dependencies. Install them beforehand or
resolve them afterward with `sudo apt --fix-broken install`.

To run the build and installation steps manually:

```sh
make dist
cp dist/mdview-1.1.1.tar.gz packaging/
cd packaging
makepkg -f
sudo pacman -U --needed mdview-1.1.1-1-any.pkg.tar.zst
```

The PKGBUILD uses a locally generated source archive (hence `SKIP` for its checksum).
Release versions in `mdview/__init__.py` and `packaging/PKGBUILD` match the Git tag
without its `v` prefix (version `1.1.1` corresponds to tag `v1.1.1`). `make dist` reads the application
version automatically. For future releases, update both version fields and these
example commands, build and test, then tag the release commit as `vX.Y.Z`.
It runs the unit tests before packaging. It installs the command, assets, desktop
entry and icon under `/usr`; pacman's desktop integration hooks update the caches.
After installation:

```sh
mdview README.md
# Optional: choose mdview as the default Markdown application.
xdg-mime default io.github.mdview.Mdview.desktop text/markdown
```

The desktop entry advertises `text/markdown` and `text/x-markdown` for Nautilus's
Open With menu. No new MIME definition is needed. To remove: `sudo pacman -R mdview`.
For inspecting the installation without changing the system:

```sh
make DESTDIR=/tmp/mdview-stage PREFIX=/usr install
```

## Design and security

`mdview/app.py` owns GTK actions, WebKit, monitoring and the clipboard.
`mdview/render.py` is independent of GTK and transforms Markdown into a complete
HTML document. `mdview/assets/` contains the stylesheet and small bundled bridge.
markdown-it-py handles CommonMark plus tables and strikethrough; Pygments supplies
local syntax highlighting. There is no CDN or JavaScript highlighting framework.

- Raw Markdown HTML is escaped, including scripts, event handlers and frames.
- A content security policy denies resources by default. Only the exact bundled
  script (SHA-256 allowlist), inline application CSS and embedded raster images
  are allowed. No network resources, remote scripts, forms or frames are loaded.
- Relative PNG/JPEG/GIF/WebP images are embedded by Python, only if their resolved
  paths stay inside the document's directory. Parent traversal and symlinks outside
  that directory are blocked. SVG, remote images and Markdown data URLs are blocked.
  Use a local raster copy when an image is unavailable.
- WebKit uses an ephemeral session, disables local storage and file access, denies
  permission requests, and intercepts navigation. Only user-clicked HTTP/HTTPS/mail
  links are handed to the desktop; only Markdown local links reopen in the viewer.
- Copy messages carry a validated block index, not an arbitrary clipboard payload.
  Python copies the corresponding original code. There are no line numbers.
- Documents are limited to 8 MiB and individual images to 10 MiB. Embedded image
  data is additionally limited to 32 MiB per document, including base64 encoding
  and repeated references. Exceeding this total rejects the document with an error.
  Parsing runs on
  the UI thread to keep this MVP small; unusually complex documents may pause it.
  This is a viewer with restricted content, not a replacement for OS sandboxing.

## Intentionally deferred

Editing/saving, navigation history, search, printing/PDF export, remote images, raw HTML,
SVG, math, Mermaid, task-list checkboxes, full GFM autolinking, cross-file anchor
restoration, watching image changes, and AppStream/store publishing metadata.
The app ID is a working identifier and should be changed to a namespace owned by
the publisher before public distribution.

## Project layout

```text
bin/mdview
mdview/
  __init__.py
  __main__.py
  app.py
  render.py
  recent.py
  state.py
  session.py
  storage.py
  assets/
    bridge.js
    style.css
data/
  io.github.mdview.Mdview.desktop
  io.github.mdview.Mdview.svg
packaging/PKGBUILD
tests/
  test_render.py
  test_recent.py
  test_state.py
  test_session.py
  test_storage.py
  test_packaging.py
  smoke_gui.py
  smoke_tabs.py
  smoke_session.py
Makefile
build.sh
README.md
LICENSE
.gitignore
```
