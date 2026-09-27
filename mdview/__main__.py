# SPDX-FileCopyrightText: 2026 Jochen Schmitt and mdview contributors
# SPDX-License-Identifier: GPL-3.0-or-later

import sys

from .app import Application

raise SystemExit(Application().run(sys.argv))
