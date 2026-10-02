"""Defensive helpers for reading persistent save data."""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Dict, List, Optional, TypeVar

from blob_evolution import config

T = TypeVar("T")

# Largest whole number accepted from a save (2**53 - 1, the biggest int a float holds exactly).
# Bigger ints load fine but raise OverflowError once the game multiplies them by a float (e.g. NG+ bonuses).
INT_MAX = 2**53 - 1


def warn(message: str) -> None:
    """Print a save-system warning to stderr."""
    print(f"[save] {message}", file=sys.stderr)


def read_save(path: str) -> Optional[dict]:
    """Return the parsed save, {} if the file doesn't exist, or None if it's unreadable."""
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, RecursionError) as exc:
        warn(f"could not read {path} ({type(exc).__name__}); using defaults")
        return None
    if not isinstance(data, dict):
        warn(f"{path} is not a JSON object; using defaults")
        return None
    return data


def write_save(path: str, data: dict) -> bool:
    """Write the save atomically (temp file + fsync + os.replace); True on success."""
    target = os.path.realpath(path)  # replace a symlink's target, not the link itself
    tmp = target + config.SAVE_TEMP_SUFFIX
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except (OSError, TypeError, ValueError) as exc:
        warn(f"could not write {path} ({type(exc).__name__}); previous save left untouched")
        return False
    return True


def backup_paths(path: str) -> List[str]:
    """Backup slots in order: <save>.bak, <save>.bak.1, ..."""
    base = path + config.SAVE_BACKUP_SUFFIX
    return [base] + [f"{base}.{n}" for n in range(1, config.SAVE_BACKUP_LIMIT)]


def backup_save(path: str) -> bool:
    """Copy a bad save into a free backup slot; True if the save may now be overwritten."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return True
    except OSError as exc:
        warn(f"could not back up {path} ({type(exc).__name__}); progress will not be saved")
        return False
    for candidate in backup_paths(path):
        try:
            with open(candidate, "rb") as f:
                if f.read() == raw:
                    warn(f"{path} is already backed up as {candidate}")
                    return True
            continue
        except FileNotFoundError:
            pass
        except OSError:
            continue
        try:
            with open(candidate, "xb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            continue
        except OSError as exc:
            warn(f"could not back up {path} ({type(exc).__name__}); progress will not be saved")
            return False
        warn(f"backed up {path} to {candidate}")
        return True
    warn(f"all {config.SAVE_BACKUP_LIMIT} backup slots for {path} are full; progress will not be saved")
    return False


def _is_number(value: object) -> bool:
    """Return True for finite ints/floats (bools excluded); ints must be within +-INT_MAX."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return abs(value) <= INT_MAX if isinstance(value, int) else math.isfinite(value)


def _is_count(value: object) -> bool:
    """Return True for a whole number from 0 to INT_MAX; bools and floats (even 3.0) are not counts."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= INT_MAX


class SaveSection:
    """Type-checked reader over one save section; valid turns False on bad data.

    table_reset turns True when a whole table (a dict or list field of the wrong type) fell back to its
    default, which loses every entry in it; one bad field or one bad entry only clears valid.
    """

    def __init__(self, data: object) -> None:
        self.valid = isinstance(data, dict)
        self.table_reset = False
        self.data: dict = data if isinstance(data, dict) else {}

    def _reject(self, default: T) -> T:
        """Mark the section invalid and return the fallback."""
        self.valid = False
        return default

    def _reject_table(self, default: T) -> T:
        """Mark the section invalid because a whole table was the wrong type; return the fallback."""
        self.table_reset = True
        return self._reject(default)

    def number(self, key: str, default: float) -> float:
        """Read a finite number (for genuine fractions such as bonuses), else default."""
        value = self.data.get(key, default)
        return value if _is_number(value) else self._reject(default)

    def integer(self, key: str, default: int) -> int:
        """Read a whole number 0..INT_MAX (a count or level), else default; floats like 3.0 are rejected too."""
        value = self.data.get(key, default)
        return value if _is_count(value) else self._reject(default)

    def boolean(self, key: str, default: bool) -> bool:
        """Read a real JSON true/false, else default; "false", 0, 1, 1.0 and null are rejected."""
        value = self.data.get(key, default)
        return value if isinstance(value, bool) else self._reject(default)

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
            return self._reject_table(list(default))
        items = [v for v in value if isinstance(v, str)]
        if len(items) != len(value):
            self.valid = False
        return items

    def integer_dict(
        self, key: str, default: Dict[str, int], limits: Optional[Dict[str, int]] = None,
    ) -> Dict[str, int]:
        """Read a str->count mapping, dropping entries that are not whole numbers 0..INT_MAX.

        With limits, an entry whose key is not in limits, or whose value is above its limit, is dropped too.
        """
        if key not in self.data:
            return default
        value = self.data[key]
        if not isinstance(value, dict):
            return self._reject_table(default)
        items = {
            k: v for k, v in value.items()
            if _is_count(v) and (limits is None or (k in limits and v <= limits[k]))
        }
        if len(items) != len(value):
            self.valid = False
        return items

    def number_dict(
        self, key: str, default: Dict[str, float], non_negative: bool = False,
    ) -> Dict[str, float]:
        """Read a str->number mapping, dropping non-numeric values (and negative ones if non_negative)."""
        if key not in self.data:
            return default
        value = self.data[key]
        if not isinstance(value, dict):
            return self._reject_table(default)
        items = {k: v for k, v in value.items() if _is_number(v) and (not non_negative or v >= 0)}
        if len(items) != len(value):
            self.valid = False
        return items
