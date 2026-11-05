# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validate locally built Arch/Debian artifacts without installing them.

Usage: python tests/check_packages.py path/to/package [path/to/other/package]
Requires the application's runtime libraries for the extracted launcher checks.
Only use packages built from this repository: they are extracted and executed.
"""

import configparser
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdviewer import __version__

APP_ID = 'com.github.jschbe.mdviewer'


def command(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout


def check_package(package):
    with tempfile.TemporaryDirectory(prefix='mdviewer-package-') as directory:
        root = Path(directory)
        if package.suffix == '.deb':
            assert package.name == f'mdviewer_{__version__}-1_all.deb'
            for field, expected in (('Package', 'mdviewer'), ('Version', f'{__version__}-1'),
                                    ('Architecture', 'all'), ('Conflicts', 'mdview'), ('Replaces', 'mdview')):
                assert command('dpkg-deb', '-f', str(package), field).strip() == expected, field
            dependencies = command('dpkg-deb', '-f', str(package), 'Depends')
            for dependency in ('python3 (>= 3.10)', 'python3-gi', 'gir1.2-gtk-4.0', 'gir1.2-adw-1',
                               'gir1.2-webkit-6.0', 'python3-markdown-it', 'python3-pygments'):
                assert dependency in dependencies, dependency
            command('dpkg-deb', '-x', str(package), str(root))
            assert (root / 'usr/share/doc/mdviewer/copyright').is_file()
        else:
            assert package.name.startswith(f'mdviewer-{__version__}-1-any.pkg.tar.')
            command('bsdtar', '-xf', str(package), '-C', str(root))
            metadata = (root / '.PKGINFO').read_text().splitlines()
            for line in ('pkgname = mdviewer', f'pkgver = {__version__}-1', 'arch = any',
                         'conflict = mdview', 'replaces = mdview'):
                assert line in metadata, line
            for dependency in ('python', 'python-gobject', 'gtk4', 'libadwaita', 'webkitgtk-6.0',
                               'python-markdown-it-py', 'python-pygments'):
                assert f'depend = {dependency}' in metadata, dependency
        installed = root / 'usr'
        module = installed / 'share/mdviewer/mdviewer'
        assert runpy.run_path(str(module / '__init__.py'))['__version__'] == __version__
        for asset in ('bridge.js', 'style.css'):
            assert (module / 'assets' / asset).is_file()
        assert (installed / 'share/licenses/mdviewer/LICENSE').is_file()
        assert (installed / f'share/icons/hicolor/scalable/apps/{APP_ID}.svg').is_file()
        desktop = installed / f'share/applications/{APP_ID}.desktop'
        entry = configparser.ConfigParser(interpolation=None)
        entry.read(desktop)
        for key, expected in (('Name', 'mdviewer'), ('Exec', 'mdviewer %F'),
                              ('Icon', APP_ID), ('StartupWMClass', APP_ID),
                              ('MimeType', 'text/markdown;text/x-markdown;')):
            assert entry['Desktop Entry'][key] == expected, key
        assert list((installed / 'share/applications').glob('*.desktop')) == [desktop]
        for legacy in ('bin/mdview', 'share/mdview', 'share/licenses/mdview', 'share/doc/mdview'):
            assert not (installed / legacy).exists(), legacy
        assert not list(root.rglob('__pycache__'))
        if shutil.which('desktop-file-validate'):
            command('desktop-file-validate', str(desktop))
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        # Resolve the installed layout away from the source checkout.
        command(str(installed / 'bin/mdviewer'), '--help', cwd=root, env=environment)
        print(f'PASS: {package.name}: metadata, dependencies, layout, desktop entry, version and launcher')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for argument in sys.argv[1:]:
        check_package(Path(argument).resolve())
