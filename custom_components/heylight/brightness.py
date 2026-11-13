"""Map user brightness (1..255) onto 30..100% of original output."""

MINIMUM_PHYSICAL_FACTOR = 0.30


def physical_brightness_factor(brightness: int) -> float:
    """Keep 1% visibly lit at former 30%, and 100% unchanged."""
    value = max(1, min(255, int(brightness)))
    return MINIMUM_PHYSICAL_FACTOR + (1.0 - MINIMUM_PHYSICAL_FACTOR) * (value - 1) / 254
