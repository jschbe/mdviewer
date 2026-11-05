# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

import configparser
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from mdviewer import __version__

APP_ID = 'com.github.jschbe.mdviewer'
LEGACY_APP_IDS = ('io.github.mdview.Mdview', 'io.github.jschbe.mdviewer')


def desktop_assets(prefix, app_id):
    return (prefix / f'share/applications/{app_id}.desktop',
            prefix / f'share/icons/hicolor/scalable/apps/{app_id}.svg')


@unittest.skipUnless(shutil.which('make') and shutil.which('tar') and shutil.which('install'),
                     'Packaging checks require make, tar and install')
class PackagingTests(unittest.TestCase):
    def test_source_archive_and_install_with_spaces(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / 'source with spaces'
            checkout.mkdir()
            for name in ('mdviewer', 'bin', 'data', 'tests'):
                shutil.copytree(source / name, checkout / name,
                                ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('Makefile', 'README.md', 'LICENSE', 'build.sh'):
                shutil.copy2(source / name, checkout / name)
            (checkout / 'packaging').mkdir()
            shutil.copy2(source / 'packaging/PKGBUILD', checkout / 'packaging/PKGBUILD')
            subprocess.run(['make', 'dist'], cwd=checkout, check=True, capture_output=True)
            unpacked = root / 'unpacked with spaces'
            with tarfile.open(checkout / f'dist/mdviewer-{__version__}.tar.gz') as archive:
                names = archive.getnames()
                self.assertTrue(all(name.startswith(f'mdviewer-{__version__}/') for name in names))
                self.assertFalse(any('/mdview/' in name or name.endswith('/bin/mdview') for name in names))
                # This archive was just generated from our own source tree.
                archive.extractall(unpacked)
            package_source = unpacked / f'mdviewer-{__version__}'
            self.assertTrue((package_source / 'packaging/PKGBUILD').is_file())
            self.assertTrue(os.access(package_source / 'build.sh', os.X_OK))
            self.assertTrue((package_source / f'data/{APP_ID}.desktop').is_file())
            self.assertTrue((package_source / f'data/{APP_ID}.svg').is_file())
            for legacy_id in LEGACY_APP_IDS:
                self.assertFalse(list((package_source / 'data').glob(f'{legacy_id}.*')))
            subprocess.run(['./build.sh', '-h'], cwd=package_source, check=True, capture_output=True)
            # The extracted source archive must also be self-contained for make dist.
            subprocess.run(['make', 'dist'], cwd=package_source, check=True, capture_output=True)
            destination = root / 'stage with spaces'
            prefix = '/usr/local with spaces'
            installed = destination / prefix.lstrip('/')
            # A direct install must remove only this app's obsolete assets in this prefix.
            legacy_assets = tuple(asset for legacy_id in LEGACY_APP_IDS
                                  for asset in desktop_assets(installed, legacy_id))
            other_assets = desktop_assets(installed, 'another-app')
            other_prefix_assets = tuple(asset for legacy_id in LEGACY_APP_IDS
                                        for asset in desktop_assets(destination / 'usr', legacy_id))
            for asset in (*legacy_assets, *other_assets, *other_prefix_assets):
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_text('preserve unless obsolete in the target prefix')
            legacy_files = tuple(installed / name for name in (
                'bin/mdview', 'share/mdview/mdview/app.py',
                'share/licenses/mdview/LICENSE', 'share/doc/mdview/copyright'))
            other_prefix_command = destination / 'usr/bin/mdview'
            user_state = destination / 'home/test/.local/state/mdview/session.json'
            preserved = (*other_assets, *other_prefix_assets, other_prefix_command, user_state)
            for asset in (*legacy_files, other_prefix_command, user_state):
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_text('preserve unless obsolete in the target prefix')
            subprocess.run(['make', f'DESTDIR={destination}', f'PREFIX={prefix}', 'install'],
                           cwd=package_source, check=True, capture_output=True)
            self.assertTrue(os.access(installed / 'bin/mdviewer', os.X_OK))
            self.assertTrue((installed / 'share/mdviewer/mdviewer/storage.py').is_file())
            self.assertTrue((installed / 'share/licenses/mdviewer/LICENSE').is_file())
            self.assertTrue(all(not asset.exists() for asset in legacy_files))
            desktop, icon = desktop_assets(installed, APP_ID)
            self.assertTrue(icon.is_file())
            entry = configparser.ConfigParser(interpolation=None)
            entry.read(desktop)
            self.assertEqual(entry['Desktop Entry']['Name'], 'mdviewer')
            self.assertEqual(entry['Desktop Entry']['Exec'], 'mdviewer %F')
            self.assertEqual(entry['Desktop Entry']['Icon'], APP_ID)
            self.assertEqual(entry['Desktop Entry']['StartupWMClass'], APP_ID)
            self.assertEqual(entry['Desktop Entry']['MimeType'], 'text/markdown;text/x-markdown;')
            self.assertTrue(all(not asset.exists() for asset in legacy_assets))
            self.assertTrue(all(asset.is_file() for asset in preserved))
            # Uninstall also handles leftover assets from the old ID, and is idempotent.
            for asset in (*legacy_assets, *legacy_files):
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_text('obsolete')
            for _ in range(2):
                subprocess.run(['make', f'DESTDIR={destination}', f'PREFIX={prefix}', 'uninstall'],
                               cwd=package_source, check=True, capture_output=True)
            self.assertFalse((installed / 'bin/mdviewer').exists())
            self.assertFalse((installed / 'share/mdviewer').exists())
            self.assertFalse((installed / 'share/licenses/mdviewer').exists())
            self.assertTrue(all(not asset.exists() for asset in (desktop, icon, *legacy_assets)))
            self.assertTrue(all(not asset.exists() for asset in legacy_files))
            self.assertTrue(all(asset.is_file() for asset in preserved))

    @unittest.skipUnless(shutil.which('makepkg'), 'Arch metadata check requires makepkg')
    def test_arch_release_metadata(self):
        source = Path(__file__).resolve().parents[1]
        result = subprocess.run(['makepkg', '--printsrcinfo'], cwd=source / 'packaging',
                                check=True, capture_output=True, text=True)
        metadata = [line.strip() for line in result.stdout.splitlines()]
        for line in ('pkgbase = mdviewer', 'pkgname = mdviewer', f'pkgver = {__version__}',
                     'pkgrel = 1', 'conflicts = mdview', 'replaces = mdview',
                     f'source = mdviewer-{__version__}.tar.gz'):
            self.assertIn(line, metadata)
