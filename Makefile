# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

PREFIX ?= /usr
PYTHON ?= python3
VERSION := $(shell $(PYTHON) -c 'from mdviewer import __version__; print(__version__)')

.PHONY: run test install uninstall dist
run:
	$(PYTHON) -m mdviewer $(if $(FILE),"$(FILE)")
test:
	$(PYTHON) -m unittest discover -s tests -v
install:
	install -Dm755 bin/mdviewer "$(DESTDIR)$(PREFIX)/bin/mdviewer"
	install -d "$(DESTDIR)$(PREFIX)/share/mdviewer/mdviewer/assets"
	install -m644 mdviewer/*.py "$(DESTDIR)$(PREFIX)/share/mdviewer/mdviewer/"
	install -m644 mdviewer/assets/* "$(DESTDIR)$(PREFIX)/share/mdviewer/mdviewer/assets/"
	install -Dm644 data/com.github.jschbe.mdviewer.desktop "$(DESTDIR)$(PREFIX)/share/applications/com.github.jschbe.mdviewer.desktop"
	install -Dm644 data/com.github.jschbe.mdviewer.svg "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/com.github.jschbe.mdviewer.svg"
	install -Dm644 LICENSE "$(DESTDIR)$(PREFIX)/share/licenses/mdviewer/LICENSE"
	# Direct installations need cleanup; package managers remove old tracked files on upgrade.
	rm -f "$(DESTDIR)$(PREFIX)/share/applications/io.github.mdview.Mdview.desktop" \
		"$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/io.github.mdview.Mdview.svg" \
		"$(DESTDIR)$(PREFIX)/share/applications/io.github.jschbe.mdviewer.desktop" \
		"$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/io.github.jschbe.mdviewer.svg"
	rm -f "$(DESTDIR)$(PREFIX)/bin/mdview"
	rm -rf "$(DESTDIR)$(PREFIX)/share/mdview" "$(DESTDIR)$(PREFIX)/share/licenses/mdview" \
		"$(DESTDIR)$(PREFIX)/share/doc/mdview"
uninstall:
	rm -f "$(DESTDIR)$(PREFIX)/bin/mdviewer" "$(DESTDIR)$(PREFIX)/bin/mdview" \
		"$(DESTDIR)$(PREFIX)/share/applications/com.github.jschbe.mdviewer.desktop" \
		"$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/com.github.jschbe.mdviewer.svg" \
		"$(DESTDIR)$(PREFIX)/share/applications/io.github.mdview.Mdview.desktop" \
		"$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/io.github.mdview.Mdview.svg" \
		"$(DESTDIR)$(PREFIX)/share/applications/io.github.jschbe.mdviewer.desktop" \
		"$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/io.github.jschbe.mdviewer.svg"
	rm -rf "$(DESTDIR)$(PREFIX)/share/mdviewer" "$(DESTDIR)$(PREFIX)/share/licenses/mdviewer" \
		"$(DESTDIR)$(PREFIX)/share/doc/mdviewer" "$(DESTDIR)$(PREFIX)/share/mdview" \
		"$(DESTDIR)$(PREFIX)/share/licenses/mdview" "$(DESTDIR)$(PREFIX)/share/doc/mdview"
dist:
	mkdir -p dist
	tar --transform='s,^,mdviewer-$(VERSION)/,' -czf dist/mdviewer-$(VERSION).tar.gz mdviewer/*.py mdviewer/assets bin data tests/*.py Makefile build.sh packaging/PKGBUILD README.md LICENSE
