# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

import ast
import string
import unittest
from pathlib import Path
from unittest.mock import patch

from mdview.i18n import gettext, select_language
from mdview.translations import TRANSLATIONS
from mdview.render import render


class TranslationTests(unittest.TestCase):
    def test_locale_selection_and_fallback(self):
        for locale, expected in [('de_DE.UTF-8', 'de'), ('de_CH', 'de'), ('fr_CH.UTF-8', 'fr'),
                                 ('it_IT@euro', 'it'), ('es-MX', 'es'), ('en_GB.UTF-8', 'en'),
                                 ('uk_UA.UTF-8', 'uk'), ('uk', 'uk'), ('ru_RU.UTF-8', 'uk'),
                                 ('ru_RU', 'uk'), ('ru-RU', 'uk'), ('ru_RU@variant', 'uk'),
                                 ('ru', 'en'), ('ru_BY.UTF-8', 'en'),
                                 ('pt_BR.UTF-8', 'en'), ('ja_JP', 'en'), ('C.UTF-8', 'en'),
                                 ('POSIX', 'en')]:
            with self.subTest(locale=locale):
                self.assertEqual(select_language({'LANG': locale}), expected)
        self.assertEqual(select_language({}), 'en')
        self.assertEqual(select_language({'LANG': 'ru_RU.UTF-8', 'LANGUAGE': 'en'}), 'uk')
        self.assertEqual(select_language({'LANG': 'en_US.UTF-8', 'LANGUAGE': 'ru_RU:en'}), 'uk')
        self.assertEqual(select_language({'LANG': 'ru_RU', 'LC_MESSAGES': 'de_DE'}), 'de')
        self.assertEqual(select_language({'LANG': 'ru_RU', 'LC_ALL': 'C', 'LANGUAGE': 'ru_RU'}), 'en')
        self.assertEqual(select_language({'LANG': 'de_DE', 'LC_MESSAGES': 'fr_FR'}), 'fr')
        self.assertEqual(select_language({'LANG': 'de_DE', 'LC_MESSAGES': 'fr_FR', 'LC_ALL': 'it_IT'}), 'it')
        self.assertEqual(select_language({'LANG': 'de_DE', 'LANGUAGE': 'es:de'}), 'es')
        self.assertEqual(select_language({'LANG': 'de_DE', 'LANGUAGE': 'nl:fr:de'}), 'fr')
        self.assertEqual(select_language({'LANG': 'de_DE', 'LANGUAGE': 'en:de'}), 'en')
        self.assertEqual(select_language({'LANG': 'de_DE', 'LC_ALL': 'C', 'LANGUAGE': 'fr'}), 'en')

    def test_catalog_coverage_and_format_fields(self):
        root = Path(__file__).resolve().parents[1] / 'mdview'
        messages = set()
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_':
                    self.assertIsInstance(node.args[0], ast.Constant)
                    messages.add(node.args[0].value)
        formatter = string.Formatter()
        for language, catalog in TRANSLATIONS.items():
            self.assertEqual(set(catalog), messages, language)
            for original, translated in catalog.items():
                self.assertTrue(translated)
                fields = lambda text: sorted(field for _, field, _, _ in formatter.parse(text) if field)
                self.assertEqual(fields(original), fields(translated), (language, original))
                self.assertEqual(original.count('%s'), translated.count('%s'))

    def test_translated_controls_do_not_translate_document(self):
        for language, label in [('de', 'Kopieren'), ('fr', 'Copier'), ('it', 'Copia'), ('es', 'Copiar'), ('uk', 'Копіювати'), ('en', 'Copy')]:
            with patch('mdview.i18n.LANGUAGE', language):
                self.assertEqual(gettext('Copy'), label)
                self.assertEqual(gettext('Unknown message'), 'Unknown message')
                document = render('# Open\n\n```\nCopy\n```', Path.cwd())
                self.assertIn('>Open</h1>', document.html)
                self.assertEqual(document.codes, ['Copy\n'])
                self.assertIn(f'data-copy-label="{label}"', document.html)
                self.assertIn(f'data-copied-label="{gettext("Copied")}"', document.html)
