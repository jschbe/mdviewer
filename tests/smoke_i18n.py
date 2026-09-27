# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional GUI localization test, including system selection and English fallback."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if len(sys.argv) == 1:
    for language in ('de_CH', 'fr_FR', 'it_IT', 'es_MX', 'en_GB', 'nl_NL'):
        environment = dict(os.environ, LC_ALL='en_US.UTF-8', LANGUAGE=language)
        subprocess.run([sys.executable, __file__, language], env=environment, check=True)
    raise SystemExit(0)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdview.app import Application, Gio, GLib, Window
from mdview.i18n import LANGUAGE

expected = {
    'de': ('Öffnen', 'Als PDF exportieren', 'Drucken', 'Kopiert'),
    'fr': ('Ouvrir', 'Exporter au format PDF', 'Imprimer', 'Copié'),
    'it': ('Apri', 'Esporta come PDF', 'Stampa', 'Copiato'),
    'es': ('Abrir', 'Exportar como PDF', 'Imprimir', 'Copiado'),
    'en': ('Open', 'Export as PDF', 'Print', 'Copied'),
}
selected = sys.argv[1].split('_')[0]
selected = selected if selected in expected else 'en'
assert LANGUAGE == selected
labels = expected[selected]


def wait_for(predicate):
    deadline = time.monotonic() + 15
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Localized GUI timed out')


with tempfile.TemporaryDirectory() as directory:
    os.environ['XDG_STATE_HOME'] = directory
    path = Path(directory) / 'Open.md'
    path.write_text('# Open\n\n```\nCopy\n```')
    app = Application()
    app.set_application_id('io.github.mdview.LanguageTest')
    app.register(None)
    window = Window(app)
    window.present()
    controls = window.info_button.get_next_sibling()
    assert controls.get_first_child().get_label() == labels[0]
    model = window.menu_button.get_menu_model()
    assert [model.get_item_attribute_value(i, 'label', None).get_string() for i in range(2)] == list(labels[1:3])
    window.open_file(Gio.File.new_for_path(str(path)))
    document = window.active_document
    wait_for(lambda: not document.web.is_loading())
    result = []

    def done(web, value, _data):
        result.append(web.evaluate_javascript_finish(value).to_string())

    document.js('window.mdviewCopied(0); document.querySelector("button[data-copy]").textContent', done)
    wait_for(lambda: bool(result))
    assert result == [labels[3]], result
    assert document.codes == ['Copy\n'] and window.heading.get_title() == 'Open.md'
    window.close()
    print(f'PASS: {sys.argv[1]} → {LANGUAGE}: native UI, menu, Copy confirmation, unchanged document.')
