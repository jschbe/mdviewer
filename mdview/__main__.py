import sys

from .app import Application

raise SystemExit(Application().run(sys.argv))
