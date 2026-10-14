# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Window zoom percentages, independent of GTK."""

MIN_ZOOM = 50
MAX_ZOOM = 300
DEFAULT_ZOOM = 100


def valid_zoom(value: object) -> bool:
    return type(value) is int and MIN_ZOOM <= value <= MAX_ZOOM


def clamp_zoom(value: object) -> int:
    if type(value) is not int:
        return DEFAULT_ZOOM
    return max(MIN_ZOOM, min(MAX_ZOOM, value))


def step_zoom(value: int, increase: bool) -> int:
    next_value = (value // 10 + 1) * 10 if increase else ((value - 1) // 10) * 10
    return max(MIN_ZOOM, min(MAX_ZOOM, next_value))
