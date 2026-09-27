# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from mdview import __version__


@unittest.skipUnless(shutil.which('make') and shutil.which('tar') and shutil.which('install'),
                     'Packaging checks require make, tar and install')
class PackagingTests(unittest.TestCase):
    def test_source_archive_and_install_with_spaces(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / 'source with spaces'
            checkout.mkdir()
            for name in ('mdview', 'bin', 'data', 'tests'):
                shutil.copytree(source / name, checkout / name,
                                ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('Makefile', 'README.md', 'LICENSE', 'build.sh'):
                shutil.copy2(source / name, checkout / name)
            (checkout / 'packaging').mkdir()
            shutil.copy2(source / 'packaging/PKGBUILD', checkout / 'packaging/PKGBUILD')
            subprocess.run(['make', 'dist'], cwd=checkout, check=True, capture_output=True)
            unpacked = root / 'unpacked with spaces'
            with tarfile.open(checkout / f'dist/mdview-{__version__}.tar.gz') as archive:
                # This archive was just generated from our own source tree.
                archive.extractall(unpacked)
            package_source = unpacked / f'mdview-{__version__}'
            self.assertTrue((package_source / 'packaging/PKGBUILD').is_file())
            self.assertTrue(os.access(package_source / 'build.sh', os.X_OK))
            subprocess.run(['./build.sh', '-h'], cwd=package_source, check=True, capture_output=True)
            # The extracted source archive must also be self-contained for make dist.
            subprocess.run(['make', 'dist'], cwd=package_source, check=True, capture_output=True)
            destination = root / 'stage with spaces'
            prefix = '/usr/local with spaces'
            subprocess.run(['make', f'DESTDIR={destination}', f'PREFIX={prefix}', 'install'],
                           cwd=package_source, check=True, capture_output=True)
            installed = destination / prefix.lstrip('/')
            self.assertTrue(os.access(installed / 'bin/mdview', os.X_OK))
            self.assertTrue((installed / 'share/mdview/mdview/storage.py').is_file())
            self.assertTrue((installed / 'share/licenses/mdview/LICENSE').is_file())
