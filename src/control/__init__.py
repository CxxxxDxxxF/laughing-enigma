"""Control layer for survivability enforcement.

This module provides deterministic control mechanisms to prevent
position size violations during capital allocation.
"""

from .survivability_controller import (
    SurvivabilityControlConfig,
    ControlEvent,
    ControlEventSeverity,
    apply_survivability_controls,
)

__all__ = [
    "SurvivabilityControlConfig",
    "ControlEvent",
    "ControlEventSeverity",
    "apply_survivability_controls",
]
