"""Module 6: a level authored in Tiled, not in Python.

Every other module in this series builds its world in code. That is fine
for a tutorial and wrong for a game: a level is content, and content wants
an editor. This module loads a `.tmx` file authored in Tiled and derives
everything from it -- what to draw, where the walls are, where the player
starts, and which tiles hurt.

The lesson is the *separation*. `assets/cerrado_cave.tmx` can be opened in
Tiled, edited, and saved, and this file does not change. Nothing here
knows the shape of the cave; it knows that a tile with `solid` is a wall,
a tile with `spawn` is where the player goes, and a tile with `damage`
hurts. Those three names are the whole interface between the map and the
game, and they are custom properties the map author sets.

Two things worth seeing in the code below:

* **`Tilemap.collision_rects()` does not produce one collider per tile.**
  It merges runs of solid tiles into the fewest rectangles that cover
  them, so this 450-tile map becomes 9 static bodies rather than 139. A
  per-tile collider is the obvious first implementation and it is how a
  tile-based game ends up with a physics step it cannot afford.
* **The tiles are drawn as primitives, not from a tileset image.** The
  loader reads tile *data* and properties, not tileset artwork, so the
  `kind` property picks a colour here. A game with a tileset PNG would
  blit from it instead; the map and the collision are identical either
  way, which is the point.
"""

from __future__ import annotations

from pathlib import Path

from pyguara.common.components import Transform
from pyguara.common.grid import Cell
from pyguara.common.types import Color, Rect, Vector2
from pyguara.config.manager import ConfigManager
from pyguara.ecs.entity import Entity
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.physics.types import BodyType
from pyguara.scene.base import Scene
from pyguara.tilemap import EMPTY_GID, Tilemap, load_tmx

MAP_PATH = Path(__file__).parent / "assets" / "cerrado_cave.tmx"

# The layer the map author put the terrain on. Named, not indexed: a map
# with a second decorative layer should not shift what the game reads.
TERRAIN_LAYER = "terrain"

# One colour per `kind` property. The map says "stone"; this says what
# stone looks like. A game with a tileset image would look up a source
# rect here instead -- same mapping, different right-hand side.
TILE_COLORS: dict[str, Color] = {
    "stone": Color(72, 64, 78),
    "soil": Color(120, 82, 54),
    "grass": Color(118, 148, 68),
    "hazard": Color(176, 72, 58),
}

BACKGROUND = Color(26, 24, 32)
PLAYER_COLOR = Color(240, 226, 180)
PLAYER_SIZE = 24

# Where the caption sits, below the 576-pixel-tall map.
CAPTION_Y = 580


class TilemapScene(Scene):
    """Builds a level from a Tiled map, then drops a body into it."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialise the scene.

        Args:
            event_dispatcher: The engine's dispatcher.
        """
        super().__init__("TilemapScene", event_dispatcher)
        self.tilemap: Tilemap | None = None
        self.physics_system: PhysicsSystem | None = None
        self._hazard_cells: set[Cell] = set()
        self._player: Entity | None = None

    def on_enter(self) -> None:
        """Load the map and build the world from it."""
        self.tilemap = load_tmx(MAP_PATH)

        physics_config = self.container.get(ConfigManager).config.physics
        self.physics_system = PhysicsSystem(
            engine=self.container.get(IPhysicsEngine),
            entity_manager=self.entity_manager,
            event_dispatcher=self.event_dispatcher,
            gravity=Vector2(physics_config.gravity_x, physics_config.gravity_y),
        )

        self._build_collision(self.tilemap)
        self._hazard_cells = self._cells_with(self.tilemap, "damage")
        self._spawn_player(self._spawn_position(self.tilemap))

    def on_exit(self) -> None:
        """Tear the physics world down."""
        if self.physics_system:
            self.physics_system.cleanup()

    def fixed_update(self, fixed_dt: float) -> None:
        """Step the simulation.

        Args:
            fixed_dt: Seconds per fixed step.
        """
        if self.physics_system:
            self.physics_system.update(fixed_dt)

    def update(self, dt: float) -> None:
        """Nothing to do each frame; the map is static.

        Args:
            dt: Frame time in seconds.
        """

    # -- Building the world from the map --

    def _build_collision(self, tilemap: Tilemap) -> None:
        """Create one static body per merged collision rectangle.

        `collision_rects()` asks each tile's `solid` property and merges
        the runs, so what comes back is a handful of rectangles rather
        than one per tile.

        Args:
            tilemap: The loaded map.
        """
        for index, rect in enumerate(tilemap.collision_rects(TERRAIN_LAYER)):
            body = self.entity_manager.create_entity(f"terrain_{index}")
            # A `Collider`'s origin is its centre, where a tile rect's is
            # its top-left corner. Getting this wrong puts every wall half
            # a wall out of place, which looks like a loader bug.
            body.add_component(
                Transform(
                    position=Vector2(rect.x + rect.width / 2, rect.y + rect.height / 2)
                )
            )
            body.add_component(RigidBody(body_type=BodyType.STATIC))
            body.add_component(Collider(dimensions=[rect.width, rect.height]))

    def _spawn_player(self, position: Vector2) -> None:
        """Drop a dynamic body at `position`.

        It exists to prove the collision came from the map: it falls, and
        it lands on geometry nothing in this file described.

        Args:
            position: Where to put it.
        """
        player = self.entity_manager.create_entity("player")
        player.add_component(Transform(position=position))
        player.add_component(RigidBody(body_type=BodyType.DYNAMIC, mass=1.0))
        player.add_component(Collider(dimensions=[PLAYER_SIZE, PLAYER_SIZE]))
        self._player = player

    def _spawn_position(self, tilemap: Tilemap) -> Vector2:
        """Find the spawn marker, or fall back to the middle of the map.

        A fallback rather than an exception: a map someone is editing may
        not have placed the marker yet, and a demo that refuses to open is
        a worse way to find that out than a player standing in the middle.

        Args:
            tilemap: The loaded map.

        Returns:
            The spawn position in world pixels.
        """
        layer = tilemap.layers[TERRAIN_LAYER]
        for cell in self._cells_with(tilemap, "spawn"):
            x, y = cell
            return Vector2(
                x * tilemap.tile_size + tilemap.tile_size / 2,
                y * tilemap.tile_size + tilemap.tile_size / 2,
            )
        return Vector2(
            layer.width * tilemap.tile_size / 2,
            layer.height * tilemap.tile_size / 2,
        )

    @staticmethod
    def _cells_with(tilemap: Tilemap, property_name: str) -> set[Cell]:
        """Return every terrain cell whose tile carries a truthy property.

        The general form of "where is the spawn" and "which tiles hurt":
        the map author marks tiles, the game asks for the marks.

        Args:
            tilemap: The loaded map.
            property_name: The custom property to look for.

        Returns:
            The matching cells.
        """
        layer = tilemap.layers[TERRAIN_LAYER]
        found: set[Cell] = set()
        for y in range(layer.height):
            for x in range(layer.width):
                gid = layer.get_tile((x, y))
                if gid == EMPTY_GID:
                    continue
                if tilemap.properties_for(gid).get(property_name):
                    found.add((x, y))
        return found

    # -- Drawing --

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the tiles, then the body that fell onto them.

        Args:
            world_renderer: The world renderer.
            ui_renderer: The UI renderer, for the caption.
        """
        world_renderer.clear(BACKGROUND)
        if self.tilemap is None:
            return

        size = self.tilemap.tile_size
        layer = self.tilemap.layers[TERRAIN_LAYER]
        for y in range(layer.height):
            for x in range(layer.width):
                gid = layer.get_tile((x, y))
                if gid == EMPTY_GID:
                    continue
                kind = str(self.tilemap.properties_for(gid).get("kind", ""))
                color = TILE_COLORS.get(kind)
                if color is None:
                    # The spawn marker, and anything else the map author
                    # added that this game has no look for. Skipped rather
                    # than drawn in a default colour: an unrecognised tile
                    # showing up as a magenta block is how a marker ends
                    # up visible in a shipped build.
                    continue
                world_renderer.draw_rect(Rect(x * size, y * size, size, size), color)

        if self._player is not None:
            position = self._player.get_component(Transform).position
            world_renderer.draw_rect(
                Rect(
                    position.x - PLAYER_SIZE / 2,
                    position.y - PLAYER_SIZE / 2,
                    PLAYER_SIZE,
                    PLAYER_SIZE,
                ),
                PLAYER_COLOR,
            )

        ui_renderer.draw_text(
            f"cerrado_cave.tmx: {len(self.tilemap.collision_rects(TERRAIN_LAYER))} "
            f"merged colliders, {len(self._hazard_cells)} hazard tiles",
            Vector2(12, CAPTION_Y),
            Color(188, 184, 196),
            14,
        )
