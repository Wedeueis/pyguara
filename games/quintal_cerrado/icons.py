"""The HUD's icons, drawn from primitives.

The same house style as `art.py`: no textures, only rects, circles, lines
and polygons in brand-palette colours. Every icon is laid out in a unit
box (0.0-1.0 on both axes) and scaled to whatever `Rect` it is given, so
one drawing serves a 44px dock slot and a 14px chip alike.

`ICONS` is the seam. It maps an icon id to a draw function, so an icon
set drawn some other way -- a sprite sheet, say -- replaces entries here
and nothing that calls `draw_icon` changes.

Every colour goes through `_Pen.color`, which lerps it towards the card
behind it by `dim`. That is how an unaffordable slot greys out. It is a
lerp rather than alpha on purpose: an icon is several overlapping shapes,
and each translucent one would blend over the last, so the overlaps would
show through as darker seams instead of the whole icon fading evenly.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.design_system.tokens import (
    Falcao,
    Guara,
    Sand,
    Verdant,
    Water,
    Wood,
)

DIM_TARGET = Color(35, 28, 38)
"""What `dim` fades towards: the HUD card's own colour, opaque."""

METAL = Falcao.C400.lerp(Color.WHITE, 0.45)
METAL_DARK = Falcao.C400
TRUNK = Wood.C500
HANDLE = Wood.C400
"""Tool handles are lighter than tree trunks: they sit on a slot face, and
an active slot is itself wood-brown."""
LEAF = Verdant.COLONIAL_500
LEAF_LIGHT = Verdant.SAGE_500
CLOUD = Sand.C100
SUN = Sand.C300
SNOW = Water.C300.lerp(Color.WHITE, 0.5)


class _Pen:
    """Unit-box drawing onto one `Rect`, with every colour dimmed alike."""

    def __init__(self, renderer: UIRenderer, rect: Rect, dim: float) -> None:
        self.renderer = renderer
        self.rect = rect
        self.dim = dim
        self.size = min(rect.width, rect.height)
        # Centre the square unit box inside a non-square rect.
        self.x0 = rect.x + (rect.width - self.size) / 2
        self.y0 = rect.y + (rect.height - self.size) / 2

    def color(self, color: Color) -> Color:
        return color.lerp(DIM_TARGET, self.dim) if self.dim > 0.0 else color

    def xy(self, u: float, v: float) -> tuple[int, int]:
        return (round(self.x0 + u * self.size), round(self.y0 + v * self.size))

    def pt(self, u: float, v: float) -> Vector2:
        x, y = self.xy(u, v)
        return Vector2(x, y)

    def px(self, length: float) -> int:
        """A unit-box length in whole pixels, never below one."""
        return max(1, round(length * self.size))

    def circle(
        self, u: float, v: float, r: float, color: Color, width: float = 0.0
    ) -> None:
        self.renderer.draw_circle(
            self.pt(u, v),
            max(1.0, r * self.size),
            self.color(color),
            self.px(width) if width else 0,
        )

    def line(
        self, u0: float, v0: float, u1: float, v1: float, color: Color, width: float
    ) -> None:
        self.renderer.draw_line(
            self.pt(u0, v0), self.pt(u1, v1), self.color(color), self.px(width)
        )

    def polyline(
        self, points: list[tuple[float, float]], color: Color, width: float
    ) -> None:
        for (u0, v0), (u1, v1) in zip(points, points[1:], strict=False):
            self.line(u0, v0, u1, v1, color, width)

    def poly(self, points: list[tuple[float, float]], color: Color) -> None:
        self.renderer.draw_polygon(
            [self.xy(u, v) for u, v in points], self.color(color)
        )

    def box(
        self,
        u: float,
        v: float,
        w: float,
        h: float,
        color: Color,
        radius: float = 0.0,
    ) -> None:
        x, y = self.xy(u, v)
        self.renderer.draw_rect(
            Rect(x, y, self.px(w), self.px(h)),
            self.color(color),
            border_radius=round(radius * self.size),
        )

    def ellipse(
        self,
        u: float,
        v: float,
        ru: float,
        rv: float,
        color: Color,
        angle: float = 0.0,
    ) -> None:
        self.poly(_ellipse(u, v, ru, rv, angle), color)


def _ellipse(
    u: float, v: float, ru: float, rv: float, angle: float = 0.0, steps: int = 18
) -> list[tuple[float, float]]:
    """The outline of an ellipse, rotated by `angle` radians."""
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    points = []
    for index in range(steps):
        t = 2 * math.pi * index / steps
        x, y = ru * math.cos(t), rv * math.sin(t)
        points.append((u + x * cos_a - y * sin_a, v + x * sin_a + y * cos_a))
    return points


def _arc(
    u: float, v: float, r: float, start: float, end: float, steps: int = 12
) -> list[tuple[float, float]]:
    """Points along a circular arc, `start` to `end` in radians."""
    return [
        (
            u + r * math.cos(start + (end - start) * i / steps),
            v + r * math.sin(start + (end - start) * i / steps),
        )
        for i in range(steps + 1)
    ]


# -- tools -----------------------------------------------------------------


def _till(pen: _Pen) -> None:
    """Enxada: a hoe, blade at the top of a diagonal handle."""
    pen.line(0.2, 0.9, 0.66, 0.2, HANDLE, 0.1)
    pen.poly([(0.5, 0.1), (0.9, 0.24), (0.84, 0.42), (0.56, 0.28)], METAL)
    pen.line(0.56, 0.28, 0.84, 0.42, METAL_DARK, 0.04)


def _water(pen: _Pen) -> None:
    """Regador: a watering can with a spout and a few drops."""
    pen.polyline(_arc(0.42, 0.42, 0.2, math.pi, 2 * math.pi), Water.C400, 0.07)
    pen.poly([(0.6, 0.55), (0.9, 0.26), (0.95, 0.32), (0.66, 0.68)], Water.C400)
    pen.box(0.16, 0.42, 0.52, 0.44, Water.C400, radius=0.08)
    pen.box(0.22, 0.5, 0.4, 0.06, Water.C300, radius=0.03)
    for u, v in ((0.94, 0.46), (0.86, 0.56), (0.97, 0.62)):
        pen.circle(u, v, 0.035, Water.C300)


def _harvest(pen: _Pen) -> None:
    """Colher: a sickle -- a crescent blade on a short handle."""
    outer = _arc(0.52, 0.44, 0.34, math.radians(200), math.radians(370))
    inner = _arc(0.58, 0.5, 0.25, math.radians(370), math.radians(200))
    pen.poly(outer + inner, METAL)
    pen.line(0.26, 0.58, 0.14, 0.92, HANDLE, 0.1)


def _compost(pen: _Pen) -> None:
    """Adubo: a heap of dark earth with a sprout on top."""
    pen.poly(
        [(0.08, 0.86), (0.26, 0.56), (0.5, 0.44), (0.74, 0.56), (0.92, 0.86)],
        Wood.C500,
    )
    for u, v, r in ((0.32, 0.72, 0.07), (0.56, 0.62, 0.06), (0.7, 0.76, 0.07)):
        pen.circle(u, v, r, Wood.C700)
    pen.line(0.5, 0.46, 0.5, 0.26, LEAF, 0.05)
    pen.ellipse(0.4, 0.26, 0.1, 0.05, LEAF_LIGHT, angle=-0.5)
    pen.ellipse(0.6, 0.22, 0.1, 0.05, LEAF, angle=0.5)


def _spray(pen: _Pen) -> None:
    """Calda: a spray bottle with a trigger head and a mist."""
    pen.box(0.28, 0.44, 0.36, 0.46, LEAF_LIGHT, radius=0.08)
    pen.box(0.36, 0.32, 0.2, 0.13, Verdant.SAGE_100)
    pen.poly([(0.3, 0.16), (0.72, 0.16), (0.72, 0.32), (0.3, 0.32)], Sand.C500)
    pen.line(0.42, 0.32, 0.36, 0.44, Sand.C500, 0.05)
    for u, v in ((0.82, 0.18), (0.9, 0.12), (0.9, 0.26), (0.97, 0.19)):
        pen.circle(u, v, 0.03, Verdant.SAGE_100)


def _store(pen: _Pen) -> None:
    """Loja: a market stall with a striped awning."""
    pen.box(0.18, 0.46, 0.64, 0.42, Wood.C500)
    pen.box(0.42, 0.6, 0.16, 0.28, Wood.C700)
    stripes = 5
    for index in range(stripes):
        u = 0.1 + index * 0.8 / stripes
        color = Guara.C500 if index % 2 == 0 else Sand.C100
        pen.poly(
            [
                (u, 0.24),
                (u + 0.8 / stripes, 0.24),
                (u + 0.8 / stripes, 0.44),
                (u, 0.44),
            ],
            color,
        )
    pen.line(0.1, 0.24, 0.9, 0.24, Wood.C700, 0.04)


def _menu(pen: _Pen) -> None:
    """Menu: three bars."""
    for v in (0.24, 0.46, 0.68):
        pen.box(0.18, v, 0.64, 0.1, Sand.C100, radius=0.04)


# -- resources ---------------------------------------------------------------


def _seed(pen: _Pen) -> None:
    """One seed: a tilted oval with a highlight."""
    pen.ellipse(0.5, 0.52, 0.3, 0.38, Sand.C500, angle=0.5)
    pen.ellipse(0.42, 0.42, 0.07, 0.16, Sand.C200, angle=0.5)


def _seed_pouch(pen: _Pen) -> None:
    """The Sementes pouch: a tied sack with a seed on it."""
    pen.circle(0.5, 0.64, 0.32, Wood.C400)
    pen.poly([(0.36, 0.38), (0.64, 0.38), (0.58, 0.24), (0.42, 0.24)], Wood.C400)
    pen.poly([(0.34, 0.24), (0.66, 0.24), (0.74, 0.1), (0.26, 0.1)], Wood.C400)
    pen.line(0.34, 0.33, 0.66, 0.33, Sand.C500, 0.06)
    pen.ellipse(0.5, 0.66, 0.1, 0.14, Wood.C700, angle=0.5)


# -- species -----------------------------------------------------------------


def _species_color(species_id: str, fallback: Color) -> Color:
    species = SPECIES_TABLE.get(species_id)
    return species.color if species is not None else fallback


def _plant_guandu(pen: _Pen) -> None:
    """Guandu: a low shrub hung with pods."""
    color = _species_color("guandu", LEAF_LIGHT)
    pen.line(0.5, 0.92, 0.5, 0.36, TRUNK, 0.06)
    pen.line(0.5, 0.62, 0.3, 0.44, TRUNK, 0.05)
    pen.line(0.5, 0.56, 0.72, 0.4, TRUNK, 0.05)
    for u, v, a in ((0.28, 0.36, -0.6), (0.5, 0.24, 0.0), (0.74, 0.32, 0.6)):
        pen.ellipse(u, v, 0.14, 0.08, color, angle=a)
    for u, v in ((0.36, 0.6), (0.66, 0.56)):
        pen.ellipse(u, v, 0.04, 0.11, Sand.C400, angle=0.3)


def _plant_cagaita(pen: _Pen) -> None:
    """Cagaita: a round-crowned tree with yellow fruit."""
    pen.line(0.5, 0.92, 0.5, 0.5, TRUNK, 0.1)
    pen.circle(0.5, 0.4, 0.3, LEAF)
    pen.circle(0.42, 0.32, 0.12, LEAF_LIGHT)
    color = _species_color("cagaita", Sand.C400)
    for u, v in ((0.36, 0.48), (0.6, 0.34), (0.66, 0.52)):
        pen.circle(u, v, 0.05, color)


def _plant_baru(pen: _Pen) -> None:
    """Baru: a tall tree, its crown in two tiers."""
    color = _species_color("baru", LEAF)
    pen.line(0.5, 0.94, 0.5, 0.3, TRUNK, 0.09)
    pen.ellipse(0.5, 0.52, 0.3, 0.12, color)
    pen.ellipse(0.5, 0.28, 0.22, 0.14, color.lerp(Verdant.SAGE_100, 0.25))
    pen.ellipse(0.66, 0.66, 0.05, 0.08, Wood.C400, angle=0.4)


def _plant_pequi(pen: _Pen) -> None:
    """Pequi: a broad, flat canopy dotted with flowers."""
    pen.line(0.5, 0.92, 0.46, 0.46, TRUNK, 0.09)
    pen.line(0.47, 0.6, 0.28, 0.44, TRUNK, 0.05)
    pen.ellipse(0.5, 0.38, 0.42, 0.16, LEAF)
    pen.ellipse(0.4, 0.32, 0.18, 0.08, LEAF_LIGHT)
    color = _species_color("pequi", Guara.C500)
    for u, v in ((0.26, 0.4), (0.52, 0.28), (0.74, 0.4)):
        pen.circle(u, v, 0.05, color)


def _plant_generic(pen: _Pen) -> None:
    """Generic: an unknown seed, already sprouting."""
    pen.ellipse(0.5, 0.7, 0.24, 0.17, Sand.C500)
    pen.line(0.5, 0.56, 0.5, 0.3, LEAF, 0.05)
    pen.ellipse(0.38, 0.3, 0.12, 0.06, LEAF_LIGHT, angle=-0.4)
    pen.ellipse(0.62, 0.26, 0.12, 0.06, LEAF, angle=0.4)


# -- sky ---------------------------------------------------------------------


def _sun_at(pen: _Pen, u: float, v: float, r: float) -> None:
    for index in range(8):
        angle = index * math.pi / 4
        pen.line(
            u + math.cos(angle) * r * 1.35,
            v + math.sin(angle) * r * 1.35,
            u + math.cos(angle) * r * 1.8,
            v + math.sin(angle) * r * 1.8,
            SUN,
            0.06,
        )
    pen.circle(u, v, r, SUN)


def _cloud_at(pen: _Pen, u: float, v: float, scale: float, color: Color) -> None:
    pen.circle(u - 0.16 * scale, v, 0.15 * scale, color)
    pen.circle(u + 0.02 * scale, v - 0.08 * scale, 0.2 * scale, color)
    pen.circle(u + 0.2 * scale, v + 0.02 * scale, 0.14 * scale, color)
    pen.box(u - 0.3 * scale, v, 0.62 * scale, 0.15 * scale, color, radius=0.05)


def _sun(pen: _Pen) -> None:
    _sun_at(pen, 0.5, 0.5, 0.22)


def _moon(pen: _Pen) -> None:
    outer = _arc(0.5, 0.5, 0.34, math.radians(70), math.radians(290), steps=16)
    inner = _arc(0.64, 0.42, 0.26, math.radians(250), math.radians(110), steps=16)
    pen.poly(outer + inner, Sand.C100)


def _calm(pen: _Pen) -> None:
    """Calm: a sun low over still air."""
    _sun_at(pen, 0.5, 0.4, 0.18)
    pen.line(0.14, 0.8, 0.86, 0.8, CLOUD, 0.06)
    pen.line(0.28, 0.92, 0.72, 0.92, CLOUD, 0.06)


def _clear(pen: _Pen) -> None:
    _sun_at(pen, 0.5, 0.5, 0.24)


def _cloudy(pen: _Pen) -> None:
    _sun_at(pen, 0.66, 0.34, 0.14)
    _cloud_at(pen, 0.46, 0.6, 1.1, CLOUD)


def _rainy(pen: _Pen) -> None:
    _cloud_at(pen, 0.5, 0.4, 1.1, Verdant.SAGE_100)
    for u in (0.3, 0.5, 0.7):
        pen.line(u, 0.66, u - 0.06, 0.86, Water.C300, 0.06)


def _windy(pen: _Pen) -> None:
    for v, length in ((0.3, 0.6), (0.52, 0.76), (0.74, 0.5)):
        points = [(0.1, v), (0.1 + length, v)]
        points += _arc(0.1 + length, v - 0.08, 0.08, math.pi / 2, -math.pi, steps=6)
        pen.polyline(points, Verdant.SAGE_100, 0.06)


def _cold_snap(pen: _Pen) -> None:
    """Cold snap: a snowflake."""
    for index in range(3):
        angle = index * math.pi / 3
        du, dv = math.cos(angle) * 0.38, math.sin(angle) * 0.38
        pen.line(0.5 - du, 0.5 - dv, 0.5 + du, 0.5 + dv, SNOW, 0.07)
    for index in range(6):
        angle = index * math.pi / 3
        pen.circle(
            0.5 + math.cos(angle) * 0.38, 0.5 + math.sin(angle) * 0.38, 0.06, SNOW
        )


# -- soil gauges ---------------------------------------------------------------


def _moisture(pen: _Pen) -> None:
    """Umidade: a drop."""
    pen.circle(0.5, 0.62, 0.26, Water.C300)
    pen.poly([(0.5, 0.1), (0.74, 0.54), (0.26, 0.54)], Water.C300)
    pen.circle(0.42, 0.64, 0.07, Water.C300.lerp(Color.WHITE, 0.5))


def _humus(pen: _Pen) -> None:
    """Húmus: a sprout out of dark earth."""
    pen.box(0.1, 0.66, 0.8, 0.24, Wood.C700, radius=0.06)
    pen.line(0.5, 0.68, 0.5, 0.34, LEAF, 0.06)
    pen.ellipse(0.34, 0.36, 0.16, 0.08, LEAF_LIGHT, angle=-0.5)
    pen.ellipse(0.66, 0.3, 0.16, 0.08, LEAF, angle=0.5)


def _shade(pen: _Pen) -> None:
    """Sombra: the sun behind a leafy branch."""
    _sun_at(pen, 0.62, 0.38, 0.16)
    pen.line(0.08, 0.8, 0.6, 0.66, TRUNK, 0.05)
    pen.ellipse(0.3, 0.6, 0.18, 0.12, LEAF)
    pen.ellipse(0.5, 0.7, 0.14, 0.09, LEAF_LIGHT)


def _pests(pen: _Pen) -> None:
    """Pragas: a caterpillar."""
    for index, (u, v) in enumerate(
        ((0.2, 0.66), (0.36, 0.58), (0.52, 0.62), (0.68, 0.54))
    ):
        pen.circle(u, v, 0.12, Guara.C400 if index % 2 else Guara.C500)
    pen.circle(0.8, 0.44, 0.13, Guara.C400)
    pen.circle(0.84, 0.4, 0.035, Wood.INK_900)
    pen.line(0.82, 0.32, 0.9, 0.2, Wood.INK_900, 0.03)


def _leaf(pen: _Pen) -> None:
    """Resilience: a leaf with its midrib."""
    upper = _arc(0.62, 0.62, 0.52, math.radians(180), math.radians(270), steps=10)
    lower = _arc(0.38, 0.38, 0.52, math.radians(0), math.radians(90), steps=10)
    pen.poly(upper + lower, LEAF)
    pen.line(0.14, 0.86, 0.8, 0.2, Verdant.SAGE_100, 0.04)


ICONS: dict[str, Callable[[_Pen], None]] = {
    "till": _till,
    "water": _water,
    "harvest": _harvest,
    "compost": _compost,
    "spray": _spray,
    "store": _store,
    "menu": _menu,
    "seed": _seed,
    "seed_pouch": _seed_pouch,
    "plant_guandu": _plant_guandu,
    "plant_cagaita": _plant_cagaita,
    "plant_baru": _plant_baru,
    "plant_pequi": _plant_pequi,
    "plant_generic": _plant_generic,
    "sun": _sun,
    "moon": _moon,
    "calm": _calm,
    "clear": _clear,
    "cloudy": _cloudy,
    "rainy": _rainy,
    "windy": _windy,
    "cold_snap": _cold_snap,
    "moisture": _moisture,
    "humus": _humus,
    "shade": _shade,
    "pests": _pests,
    "leaf": _leaf,
}
"""Every icon, by id. The weather ids match `weather.WEATHER_TABLE`'s keys
and the tool ids match `scenes.GardenScene`'s, so a caller never needs a
second lookup table between its own ids and these."""


def draw_icon(
    renderer: UIRenderer, icon_id: str, rect: Rect, *, dim: float = 0.0
) -> None:
    """Draw icon `icon_id`, scaled into `rect`.

    Args:
        renderer: The UI renderer to draw through.
        icon_id: A key of `ICONS`. An unknown id draws nothing, the same
            tolerance `art.draw_structure` gives an unknown kind.
        rect: Where to draw it. The icon keeps its square proportions and
            is centred in a non-square rect.
        dim: 0.0 for full colour, up to 1.0 for faded into the card.
    """
    draw = ICONS.get(icon_id)
    if draw is not None:
        draw(_Pen(renderer, rect, dim))
