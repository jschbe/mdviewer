# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

PREFIX ?= /usr
PYTHON ?= python3
VERSION := $(shell $(PYTHON) -c 'from mdview import __version__; print(__version__)')

.PHONY: run test install dist
run:
	$(PYTHON) -m mdview $(if $(FILE),"$(FILE)")
test:
	$(PYTHON) -m unittest discover -s tests -v
install:
	install -Dm755 bin/mdview "$(DESTDIR)$(PREFIX)/bin/mdview"
	install -d "$(DESTDIR)$(PREFIX)/share/mdview/mdview/assets"
	install -m644 mdview/*.py "$(DESTDIR)$(PREFIX)/share/mdview/mdview/"
	install -m644 mdview/assets/* "$(DESTDIR)$(PREFIX)/share/mdview/mdview/assets/"
	install -Dm644 data/io.github.mdview.Mdview.desktop "$(DESTDIR)$(PREFIX)/share/applications/io.github.mdview.Mdview.desktop"
	install -Dm644 data/io.github.mdview.Mdview.svg "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/io.github.mdview.Mdview.svg"
	install -Dm644 LICENSE "$(DESTDIR)$(PREFIX)/share/licenses/mdview/LICENSE"
dist:
	mkdir -p dist
	tar --transform='s,^,mdview-$(VERSION)/,' -czf dist/mdview-$(VERSION).tar.gz mdview/*.py mdview/assets bin data tests/*.py Makefile build.sh packaging/PKGBUILD README.md LICENSE
