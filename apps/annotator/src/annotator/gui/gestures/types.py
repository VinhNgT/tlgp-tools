"""Shared types and events for the gestures package."""

from dataclasses import dataclass


@dataclass
class GestureEvent:
    """Framework-agnostic gesture event data."""
    x: float
    y: float
    screen_x: int
    screen_y: int
    shift: bool
    ctrl: bool

