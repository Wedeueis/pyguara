"""The in-game HUD, built from UI widgets on their own layer.

Everything here is a stock component -- `Panel`, `ProgressBar`, `Label` --
plus two small glyphs that had to be drawn because the demo ships no
textures. Nothing is positioned by a magic number: each cluster carries
`LayoutConstraints` anchoring it to a corner, so the HUD is correct at any
window size and the layout engine does the arithmetic.

It lives on `UILayer.HUD`, which is what keeps it *under* the pause menu
and the options panel no matter which was built first, and out of the focus
ring while either is up.

Every readout is real gameplay state:

- the health bar is `Health.current / max_health`
- the boost pips are what is left of `SpeedBoostEffect`'s five seconds
- the counter is collectibles picked up against the number in the level
"""

from __future__ import annotations

from games.guara_falcao.components import Health, Score
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.entity import Entity
from pyguara.graphics.protocols import UIRenderer
from pyguara.kits.effects import EffectContainer
from pyguara.ui.base import UIElement
from pyguara.ui.components.panel import Panel
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.text import Label
from pyguara.ui.constraints import create_anchored_constraints
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins
from pyguara.ui.manager import UIManager
from pyguara.ui.types import UIAnchor, UILayer

BOOST_KEY = "speed_boost"
BOOST_PIPS = 3

BAR_WIDTH = 168
HEALTH_HEIGHT = 14
BOOST_HEIGHT = 9


class GuaraGlyph(UIElement):
    """The hero's face, at portrait size, from four rectangles.

    A stand-in for the avatar art the mockups use. It is drawn rather than
    loaded because this demo deliberately ships no assets -- and a HUD
    portrait is small enough that four rects read as a muzzle and two ears.
    """

    def __init__(self, position: Vector2, size: int = 28) -> None:
        """Initialize the glyph.

        Args:
            position: Top-left corner.
            size: Box size in pixels.
        """
        super().__init__(position, Vector2(size, size))

    def render(self, renderer: UIRenderer) -> None:
        """Draw the face."""
        from games.guara_falcao import art

        rect = self.rect
        unit = rect.width / 8

        renderer.draw_rect(rect, art.COAT)
        # Ears, then the cream muzzle, then an eye.
        renderer.draw_rect(
            Rect(rect.x, rect.y - int(unit), int(unit * 2), int(unit * 2)), art.MANE
        )
        renderer.draw_rect(
            Rect(
                rect.x + int(unit * 6), rect.y - int(unit), int(unit * 2), int(unit * 2)
            ),
            art.MANE,
        )
        renderer.draw_rect(
            Rect(
                rect.x + int(unit * 2),
                rect.y + int(unit * 4),
                int(unit * 4),
                int(unit * 3),
            ),
            art.CREAM,
        )
        renderer.draw_rect(
            Rect(rect.x + int(unit * 2), rect.y + int(unit * 2), int(unit), int(unit)),
            art.EYE,
        )


class PipRow(UIElement):
    """A row of small squares, `lit` of them filled.

    The mockup's falcão charges. Here they count down the speed boost, so
    the row is a meter you can read at a glance without a number on it.
    """

    PIP = 11
    GAP = 4

    def __init__(self, position: Vector2, count: int = BOOST_PIPS) -> None:
        """Initialize the row.

        Args:
            position: Top-left corner.
            count: How many pips to draw.
        """
        width = count * self.PIP + (count - 1) * self.GAP
        super().__init__(position, Vector2(width, self.PIP))
        self.count = count
        self.lit = 0

    def render(self, renderer: UIRenderer) -> None:
        """Draw the pips, filled up to `lit`."""
        colors = self.theme.colors
        for index in range(self.count):
            box = Rect(
                self.rect.x + index * (self.PIP + self.GAP),
                self.rect.y,
                self.PIP,
                self.PIP,
            )
            if index < self.lit:
                renderer.draw_rect(box, colors.action_secondary)
            renderer.draw_rect(box, colors.edge_strong, width=1)


class KeycapHints(UIElement):
    """The control prompts along the bottom edge.

    Drawn rather than composed from `Label`s so the caps can be bevelled
    boxes with the key inside them, which is what makes a prompt read as a
    key rather than as a sentence.
    """

    CAP = 26
    GAP = 6

    def __init__(self, position: Vector2, keys: tuple[str, ...]) -> None:
        """Initialize the hints.

        Args:
            position: Top-left corner.
            keys: Cap labels, left to right.
        """
        width = len(keys) * self.CAP + (len(keys) - 1) * self.GAP
        super().__init__(position, Vector2(width, self.CAP))
        self.keys = keys

    def render(self, renderer: UIRenderer) -> None:
        """Draw each cap and its letter."""
        colors = self.theme.colors
        size = self.theme.fonts.size_small
        for index, key in enumerate(self.keys):
            box = Rect(
                self.rect.x + index * (self.CAP + self.GAP),
                self.rect.y,
                self.CAP,
                self.CAP,
            )
            renderer.draw_rect(box, colors.surface_card)
            renderer.draw_rect(box, colors.edge_strong, width=1)

            text_w, text_h = renderer.get_text_size(key, size)
            renderer.draw_text(
                key,
                Vector2(
                    box.x + (box.width - text_w) // 2,
                    box.y + (box.height - text_h) // 2,
                ),
                colors.text_body,
                size,
            )


class Hud:
    """Builds the HUD, and keeps it showing what the game actually holds."""

    def __init__(self, ui_manager: UIManager, total_collectibles: int) -> None:
        """Build every cluster and add it to the HUD layer.

        Args:
            ui_manager: The manager to add the roots to.
            total_collectibles: How many pickups the level contains, for
                the counter's denominator.
        """
        self._total = max(1, total_collectibles)

        self.health_bar = ProgressBar(
            Vector2(0, 0), Vector2(BAR_WIDTH, HEALTH_HEIGHT), value=1.0
        )
        self.boost_bar = ProgressBar(
            Vector2(0, 0), Vector2(BAR_WIDTH, BOOST_HEIGHT), value=0.0
        )
        self.pips = PipRow(Vector2(0, 0))
        self.counter = Label(f"00 / {self._total:02d}", Vector2(0, 0), font_size=18)

        vitals = self._build_vitals(ui_manager)
        self._build_companion(ui_manager)
        self._build_counter(ui_manager)
        self._build_hints(ui_manager)

        self.pause_button = BevelButton(
            "Pause", Vector2(0, 0), Vector2(120, 38), skin=Skins.GHOST
        )
        self.pause_button.constraints = create_anchored_constraints(
            UIAnchor.BOTTOM_RIGHT, margin=20
        )
        ui_manager.add_element(self.pause_button, UILayer.HUD)

        self._roots = vitals

    def _build_vitals(self, ui_manager: UIManager) -> BevelPanel:
        """The portrait, the health bar and the boost bar, top-left."""
        panel = BevelPanel(Vector2(0, 0), Vector2(228, 62), border_width=2)
        panel.constraints = create_anchored_constraints(UIAnchor.TOP_LEFT, margin=18)

        glyph = GuaraGlyph(Vector2(10, 16))
        glyph.constraints = create_anchored_constraints(
            UIAnchor.TOP_LEFT, offset_x=10, offset_y=16
        )
        self.health_bar.constraints = create_anchored_constraints(
            UIAnchor.TOP_LEFT, offset_x=48, offset_y=12
        )
        self.boost_bar.constraints = create_anchored_constraints(
            UIAnchor.TOP_LEFT, offset_x=48, offset_y=32
        )

        for child in (glyph, self.health_bar, self.boost_bar):
            panel.add_child(child)
        ui_manager.add_element(panel, UILayer.HUD)
        return panel

    def _build_companion(self, ui_manager: UIManager) -> None:
        """The falcão's row of boost pips, under the vitals."""
        panel = Panel(Vector2(0, 0), Vector2(120, 34), border_width=2)
        panel.constraints = create_anchored_constraints(
            UIAnchor.TOP_LEFT, offset_x=18, offset_y=92
        )
        self.pips.constraints = create_anchored_constraints(
            UIAnchor.TOP_LEFT, offset_x=12, offset_y=11
        )
        panel.add_child(self.pips)
        ui_manager.add_element(panel, UILayer.HUD)

    def _build_counter(self, ui_manager: UIManager) -> None:
        """The fruit counter, top-right."""
        panel = BevelPanel(Vector2(0, 0), Vector2(132, 44), border_width=2)
        panel.constraints = create_anchored_constraints(UIAnchor.TOP_RIGHT, margin=18)

        dot = _FruitDot(Vector2(0, 0))
        dot.constraints = create_anchored_constraints(
            UIAnchor.TOP_LEFT, offset_x=12, offset_y=13
        )
        self.counter.constraints = create_anchored_constraints(
            UIAnchor.TOP_LEFT, offset_x=44, offset_y=12
        )
        panel.add_child(dot)
        panel.add_child(self.counter)
        ui_manager.add_element(panel, UILayer.HUD)

    def _build_hints(self, ui_manager: UIManager) -> None:
        """The keycap prompts, bottom-centre."""
        hints = KeycapHints(Vector2(0, 0), ("<", ">", "^", "R", "F1"))
        hints.constraints = create_anchored_constraints(
            UIAnchor.BOTTOM_CENTER, margin=18
        )
        ui_manager.add_element(hints, UILayer.HUD)

    def update(self, player: Entity | None) -> None:
        """Pull this frame's numbers out of the player entity.

        Args:
            player: The player, or None while the level is rebuilding.
        """
        if player is None:
            return

        health = player.get_component(Health)
        if health is not None and health.max_health > 0:
            self.health_bar.set_value(health.current / health.max_health)

        self.boost_bar.set_value(self._boost_fraction(player))
        self.pips.lit = round(self.boost_bar.value * BOOST_PIPS)

        score = player.get_component(Score)
        if score is not None:
            collected = min(score.coins_collected, self._total)
            self.counter.set_text(f"{collected:02d} / {self._total:02d}")

    @staticmethod
    def _boost_fraction(player: Entity) -> float:
        """How much of the speed boost is left, 0.0 when none is active.

        Args:
            player: The player entity.

        Returns:
            Remaining boost as a fraction of its full duration.
        """
        container = player.get_component(EffectContainer)
        if container is None:
            return 0.0
        for effect in container.effects:
            if effect.key == BOOST_KEY and effect.duration:
                remaining = max(0.0, effect.duration - effect.elapsed)
                return remaining / effect.duration
        return 0.0


class _FruitDot(UIElement):
    """The counter's lime, as a disc with a rind ring."""

    def __init__(self, position: Vector2, size: int = 20) -> None:
        """Initialize the dot.

        Args:
            position: Top-left corner.
            size: Diameter in pixels.
        """
        super().__init__(position, Vector2(size, size))

    def render(self, renderer: UIRenderer) -> None:
        """Draw the disc."""
        from games.guara_falcao import art

        radius = self.rect.width / 2
        center = Vector2(self.rect.x + radius, self.rect.y + radius)
        renderer.draw_circle(center, radius, art.FRUIT_RIPE)
        renderer.draw_circle(
            center, radius, Color(art.TRUNK.r, art.TRUNK.g, art.TRUNK.b), width=2
        )
