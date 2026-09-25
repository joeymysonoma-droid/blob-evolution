"""Defensive helpers for reading persistent save data."""

from __future__ import annotations

import math
from typing import Dict, List, TypeVar

T = TypeVar("T")


def _is_number(value: object) -> bool:
    """Return True for finite ints/floats (bools excluded)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return isinstance(value, int) or math.isfinite(value)


class SaveSection:
    """Type-checked reader over one save section; valid turns False on bad data."""

    def __init__(self, data: object) -> None:
        self.valid = isinstance(data, dict)
        self.data: dict = data if isinstance(data, dict) else {}

    def _reject(self, default: T) -> T:
        """Mark the section invalid and return the fallback."""
        self.valid = False
        return default

    def number(self, key: str, default: float) -> float:
        """Read a finite number, else default."""
        value = self.data.get(key, default)
        return value if _is_number(value) else self._reject(default)

    def text(self, key: str, default: str) -> str:
        """Read a string, else default."""
        value = self.data.get(key, default)
        return value if isinstance(value, str) else self._reject(default)

    def str_list(self, key: str, default: List[str]) -> List[str]:
        """Read a list of strings, dropping non-string items."""
        if key not in self.data:
            return list(default)
        value = self.data[key]
        if not isinstance(value, list):
            return self._reject(list(default))
        items = [v for v in value if isinstance(v, str)]
        if len(items) != len(value):
            self.valid = False
        return items

    def number_dict(self, key: str, default: Dict[str, float]) -> Dict[str, float]:
        """Read a str->number mapping, dropping non-numeric values."""
        if key not in self.data:
            return default
        value = self.data[key]
        if not isinstance(value, dict):
            return self._reject(default)
        items = {k: v for k, v in value.items() if _is_number(v)}
        if len(items) != len(value):
            self.valid = False
        return items
