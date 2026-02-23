"""
Guild Wars 2 copper → gold / silver / copper formatting utilities.
"""


def copper_to_gsc(copper: int) -> tuple[int, int, int]:
    """Convert a copper integer to (gold, silver, copper)."""
    copper = int(copper)
    gold = copper // 10_000
    silver = (copper % 10_000) // 100
    rem = copper % 100
    return gold, silver, rem


def format_gsc(copper: int) -> str:
    """Return a human-readable 'Xg Ys Zc' string."""
    g, s, c = copper_to_gsc(copper)
    parts: list[str] = []
    if g:
        parts.append(f"{g:,}g")
    if s or g:  # show silver if there's gold (even if 0s)
        parts.append(f"{s}s")
    parts.append(f"{c}c")
    return " ".join(parts)
