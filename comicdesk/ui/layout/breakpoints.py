"""Width breakpoints for responsive UI behavior."""

from comicdesk.ui.theme import ACTION_BAR_COMPACT_WIDTH, NAV_COMPACT_WIDTH


def is_nav_compact(width: int) -> bool:
    return width < NAV_COMPACT_WIDTH


def is_action_bar_compact(width: int) -> bool:
    return width < ACTION_BAR_COMPACT_WIDTH
