PREFIX ?= /usr
PYTHON ?= python3

.PHONY: run test install dist
run:
	$(PYTHON) -m mdview $(FILE)
test:
	$(PYTHON) -m unittest discover -s tests -v
install:
	install -Dm755 bin/mdview $(DESTDIR)$(PREFIX)/bin/mdview
	install -d $(DESTDIR)$(PREFIX)/share/mdview/mdview/assets
	install -m644 mdview/*.py $(DESTDIR)$(PREFIX)/share/mdview/mdview/
	install -m644 mdview/assets/* $(DESTDIR)$(PREFIX)/share/mdview/mdview/assets/
	install -Dm644 data/io.github.mdview.Mdview.desktop $(DESTDIR)$(PREFIX)/share/applications/io.github.mdview.Mdview.desktop
	install -Dm644 data/io.github.mdview.Mdview.svg $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/io.github.mdview.Mdview.svg
	install -Dm644 LICENSE $(DESTDIR)$(PREFIX)/share/licenses/mdview/LICENSE
dist:
	mkdir -p dist
	tar --transform='s,^,mdview-0.1.0/,' -czf dist/mdview-0.1.0.tar.gz mdview/*.py mdview/assets bin data tests/*.py Makefile README.md LICENSE
