"""2D vector math utilities."""

from __future__ import annotations

import math
from typing import Tuple


class Vector2:
    """Simple 2D vector with common operations."""

    __slots__ = ("x", "y")

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)

    def copy(self) -> Vector2:
        """Return a copy of this vector."""
        return Vector2(self.x, self.y)

    def set(self, x: float, y: float) -> Vector2:
        """Set components and return self."""
        self.x = x
        self.y = y
        return self

    def add(self, other: Vector2) -> Vector2:
        """Add another vector."""
        self.x += other.x
        self.y += other.y
        return self

    def sub(self, other: Vector2) -> Vector2:
        """Subtract another vector."""
        self.x -= other.x
        self.y -= other.y
        return self

    def scale(self, factor: float) -> Vector2:
        """Multiply by scalar."""
        self.x *= factor
        self.y *= factor
        return self

    def length(self) -> float:
        """Return magnitude."""
        return math.hypot(self.x, self.y)

    def length_sq(self) -> float:
        """Return squared magnitude."""
        return self.x * self.x + self.y * self.y

    def normalize(self) -> Vector2:
        """Normalize to unit length."""
        length = self.length()
        if length > 0:
            self.x /= length
            self.y /= length
        return self

    def dot(self, other: Vector2) -> float:
        """Dot product."""
        return self.x * other.x + self.y * other.y

    def distance_to(self, other: Vector2) -> float:
        """Distance to another vector."""
        return math.hypot(self.x - other.x, self.y - other.y)

    def angle(self) -> float:
        """Return angle in radians."""
        return math.atan2(self.y, self.x)

    def rotated(self, radians: float) -> Vector2:
        """Return rotated copy."""
        cos_a = math.cos(radians)
        sin_a = math.sin(radians)
        return Vector2(
            self.x * cos_a - self.y * sin_a,
            self.x * sin_a + self.y * cos_a,
        )

    def lerp(self, other: Vector2, t: float) -> Vector2:
        """Linear interpolation toward other."""
        self.x += (other.x - self.x) * t
        self.y += (other.y - self.y) * t
        return self

    def clamp_to_rect(self, width: float, height: float, margin: float = 0.0) -> Vector2:
        """Clamp position within rectangle."""
        self.x = max(margin, min(width - margin, self.x))
        self.y = max(margin, min(height - margin, self.y))
        return self

    def as_tuple(self) -> Tuple[float, float]:
        """Return (x, y) tuple."""
        return (self.x, self.y)

    def __add__(self, other: Vector2) -> Vector2:
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vector2) -> Vector2:
        return Vector2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vector2:
        return Vector2(self.x * scalar, self.y * scalar)

    def __truediv__(self, scalar: float) -> Vector2:
        return Vector2(self.x / scalar, self.y / scalar)

    def __repr__(self) -> str:
        return f"Vector2({self.x:.2f}, {self.y:.2f})"
