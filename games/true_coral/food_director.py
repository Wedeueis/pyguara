"""True Coral - Food Director.

Keeps a target number of food items on the board, topping up via
`kits.spawn.SpawnDirector` whenever the count drops low, and rolling each
new item's type from `kits.loot`. Board-population policy and grid-cell
placement are this game's own job -- neither kit knows what a "board" is.
"""

from collections.abc import Callable, Iterable

from games.true_coral.components import Food
from pyguara.common.grid import Cell
from pyguara.common.random import RandomStream
from pyguara.ecs.manager import EntityManager
from pyguara.kits.loot import LootEntry, LootTable, Rarity, roll_loot
from pyguara.kits.spawn import SpawnDirector, SpawnEntry, Wave

# What a food cell turns out to be. The HUD calls out beetle > larva --
# beetle is rarer and worth more; star is a rare bonus on top of both.
FOOD_LOOT_TABLE = LootTable(
    entries=[
        LootEntry(payload="larva", weight=70.0, rarity=Rarity.COMMON),
        LootEntry(payload="beetle", weight=25.0, rarity=Rarity.RARE),
        LootEntry(payload="star", weight=5.0, rarity=Rarity.LEGENDARY),
    ]
)


class FoodDirector:
    """Tops the board up to `target_population` food items."""

    TARGET_POPULATION = 4
    SPAWN_INTERVAL = 0.3  # Seconds between releases within a top-up wave

    def __init__(
        self,
        entity_manager: EntityManager,
        grid_width: int,
        grid_height: int,
        is_cell_free: Callable[[Cell], bool],
        rng: RandomStream | None = None,
    ) -> None:
        """Create a director with no food on the board yet.

        Args:
            entity_manager: Where food entities are created.
            grid_width: Board width, in cells.
            grid_height: Board height, in cells.
            is_cell_free: Predicate a candidate spawn cell must satisfy --
                not on the snake, not already holding food. This game's
                own occupancy rule; the director never assumes one.
            rng: Seeded stream driving type rolls and cell picks. Defaults
                to a fresh, unseeded stream.
        """
        self._em = entity_manager
        self._grid_width = grid_width
        self._grid_height = grid_height
        self._is_cell_free = is_cell_free
        self._rng = rng if rng is not None else RandomStream()
        self._director = SpawnDirector(budget=0.0, regen_rate=0.0, max_budget=0.0)
        self._active_cells: set[Cell] = set()

    def update(self, dt: float) -> None:
        """Top up the board if it's run low, then let the director release."""
        if self._director.is_idle and len(self._active_cells) < self.TARGET_POPULATION:
            needed = self.TARGET_POPULATION - len(self._active_cells)
            entries = [
                SpawnEntry(factory=self._make_spawn_factory(), cost=0.0)
                for _ in range(needed)
            ]
            self._director.queue_wave(
                Wave(entries=entries, interval=self.SPAWN_INTERVAL)
            )

        self._director.update(dt)

    def on_food_eaten(self, cell: Cell) -> None:
        """Notify the director that `cell`'s food is gone, freeing it up."""
        self._active_cells.discard(cell)

    def _make_spawn_factory(self) -> Callable[[], None]:
        def factory() -> None:
            cell = self._pick_free_cell()
            if cell is None:
                return  # Board too crowded this attempt; the next tick retries.

            entry = roll_loot(self._rng, FOOD_LOOT_TABLE)
            food_type = entry.payload if entry is not None else "larva"

            entity = self._em.create_entity(f"food_{cell[0]}_{cell[1]}")
            entity.add_component(Food(food_type=food_type, cell=cell))
            self._active_cells.add(cell)

        return factory

    def _pick_free_cell(self, max_attempts: int = 50) -> Cell | None:
        for _ in range(max_attempts):
            cell = (
                self._rng.randint(0, self._grid_width - 1),
                self._rng.randint(0, self._grid_height - 1),
            )
            if cell in self._active_cells:
                continue
            if self._is_cell_free(cell):
                return cell
        return None

    @property
    def active_cells(self) -> Iterable[Cell]:
        """Every cell currently holding food, for rendering/lookup."""
        return frozenset(self._active_cells)
