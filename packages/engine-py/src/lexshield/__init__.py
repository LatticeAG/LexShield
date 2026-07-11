"""LexShield — open-source policy firewall for agent tool calls."""

from lexshield.errors import (
    LexShieldBlockedError,
    LexShieldChallengeError,
    LexShieldConfigError,
    LexShieldError,
)
from lexshield.shield import Shield
from lexshield.version import __version__

__all__ = [
    "Shield",
    "LexShieldError",
    "LexShieldBlockedError",
    "LexShieldChallengeError",
    "LexShieldConfigError",
    "__version__",
]
