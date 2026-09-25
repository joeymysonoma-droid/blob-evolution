"""Defensive helpers for reading persistent save data."""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Dict, List, Optional, TypeVar

from blob_evolution import config

T = TypeVar("T")


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
