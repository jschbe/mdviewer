# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Select the UI language from the standard desktop locale environment."""

import os

from .translations import TRANSLATIONS


def select_language(environment=None):
    environment = os.environ if environment is None else environment
    locale = (environment.get("LC_ALL") or environment.get("LC_MESSAGES")
              or environment.get("LANG") or "C")
    base = locale.split(".")[0].split("@")[0]
    if base.upper() in ("C", "POSIX"):
        return "en"
    if base.replace("-", "_").lower() == "ru_ru":
        return "uk"
    preferences = environment.get("LANGUAGE") or locale
    for preference in preferences.split(":"):
        normalized = preference.split(".")[0].split("@")[0].replace("-", "_").lower()
        if normalized == "ru_ru":
            return "uk"
        language = normalized.split("_")[0]
        if language == "en" or language in TRANSLATIONS:
            return language
    return "en"


LANGUAGE = select_language()


def gettext(message):
    return TRANSLATIONS.get(LANGUAGE, {}).get(message, message)
