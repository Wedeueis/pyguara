"""Where everything sits on the 960x640 garden screen.

One place for the screen's regions, so the grid, the HUD cards and the
dock cannot drift into each other one hard-coded offset at a time::

    RIBBON  [ resources ][ weather / day   ][ resilience        ]
    GRID    [ 12x8 plot, 576x384           ][ right column:     ]
            [                              ][ inspector, tool,  ]
            [                              ][ toast             ]
    DOCK    [ ESPÉCIES      ][ FERRAMENTAS    ][ BASE ]
"""

from __future__ import annotations

from games.quintal_cerrado.bootstrap import WINDOW_HEIGHT, WINDOW_WIDTH
from games.quintal_cerrado.garden_grid import GRID_HEIGHT, GRID_WIDTH, TILE_SIZE
from pyguara.common.types import Rect, Vector2

MARGIN = 16
GAP = 10

RIBBON_Y = 10
RIBBON_HEIGHT = 64

GRID_ORIGIN = Vector2(24, RIBBON_Y + RIBBON_HEIGHT + 12)
GRID_RECT = Rect(
    int(GRID_ORIGIN.x),
    int(GRID_ORIGIN.y),
    GRID_WIDTH * TILE_SIZE,
    GRID_HEIGHT * TILE_SIZE,
)

COLUMN_X = GRID_RECT.right + MARGIN
COLUMN_WIDTH = WINDOW_WIDTH - MARGIN - COLUMN_X
"""The right-hand column beside the grid: the inspector and messages."""

RESOURCE_CARD = Rect(MARGIN, RIBBON_Y, 268, RIBBON_HEIGHT)
WEATHER_CARD = Rect(
    RESOURCE_CARD.right + GAP,
    RIBBON_Y,
    COLUMN_X - GAP - (RESOURCE_CARD.right + GAP),
    RIBBON_HEIGHT,
)
RESILIENCE_CARD = Rect(COLUMN_X, RIBBON_Y, COLUMN_WIDTH, RIBBON_HEIGHT)

TOOL_CARD_HEIGHT = 100
"""The card under the inspector that explains the hovered tool or seed."""

SLOT_SIZE = Vector2(64, 76)
SLOT_SPACING = 6
DOCK_PADDING = 8
DOCK_HEADER = 22
DOCK_HEIGHT = DOCK_HEADER + int(SLOT_SIZE.y) + 2 * DOCK_PADDING
DOCK_Y = GRID_RECT.bottom + (WINDOW_HEIGHT - GRID_RECT.bottom - DOCK_HEIGHT) // 2
"""The dock sits centred in the band between the grid and the window edge."""


def group_width(slot_count: int) -> int:
    """How wide a dock group holding `slot_count` slots is."""
    return (
        slot_count * int(SLOT_SIZE.x)
        + (slot_count - 1) * SLOT_SPACING
        + 2 * DOCK_PADDING
    )
