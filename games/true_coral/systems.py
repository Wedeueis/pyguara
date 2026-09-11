"""True Coral - Game Systems.

Logic processors for the snake game.
"""

from games.true_coral.components import Food, MoveState, Score
from games.true_coral.events import (
    FoodEatenEvent,
    GameOverEvent,
    SnakeDiedEvent,
    StarEffectEnded,
    StarEffectStarted,
)
from games.true_coral.food_director import FoodDirector
from pyguara.common.grid import Cell
from pyguara.common.modifiers import Modifier, ModifierType
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.action_combat import Health, apply_damage
from pyguara.kits.effects import Effect, EffectContainer, StackingRule, add_effect
from pyguara.kits.stats import DamageType, StatBlock, get_stat
from pyguara.kits.trail import Trail, advance, grow, overlaps_self, reset

MOVE_RATE_STAT = "move_rate"
BASE_MOVE_RATE = 4.0  # Moves per second

# (growth segments, points) per food type.
_FOOD_VALUE = {
    "larva": (1, 10),
    "beetle": (2, 30),
    "star": (1, 50),
}


class StarEffect(Effect):
    """The star's temporary speed boost + immortality (`makes it rain`).

    Doubles `move_rate` and grants invincibility for its duration; the
    scene reacts to `StarEffectStarted`/`StarEffectEnded` to start and
    stop the rain overlay -- this effect knows nothing about rendering,
    only the core event dispatch it's already coupled through.
    """

    MOVE_RATE_BOOST_PERCENT = 1.0  # +100% = double speed
    DURATION = 6.0

    def __init__(self, stat_block: StatBlock, health: Health) -> None:
        """Bind this effect to the stats/health it will modify.

        Args:
            stat_block: Must already have a `MOVE_RATE_STAT` entry.
            health: Whose `invincible_timer` this extends.
        """
        super().__init__(key="star", duration=self.DURATION)
        self._stat_block = stat_block
        self._health = health

    def on_apply(self, entity_id: str, dispatcher: EventDispatcher) -> None:
        """Boost move_rate, grant invincibility, and announce the rain cue."""
        self._stat_block.stats[MOVE_RATE_STAT].add_modifier(
            Modifier(self.MOVE_RATE_BOOST_PERCENT, ModifierType.PERCENT_ADD, self.key)
        )
        self._health.invincible_timer = max(
            self._health.invincible_timer, self.DURATION
        )
        dispatcher.dispatch(StarEffectStarted(entity_id=entity_id))

    def on_remove(self, entity_id: str, dispatcher: EventDispatcher) -> None:
        """Remove the speed boost and announce the rain should stop."""
        self._stat_block.stats[MOVE_RATE_STAT].remove_source(self.key)
        dispatcher.dispatch(StarEffectEnded(entity_id=entity_id))


class SnakeMovementSystem:
    """Ticks the snake forward on its own clock, independent of frame rate.

    One grid step per `1 / move_rate` seconds (`move_rate` read fresh from
    `StatBlock` every tick, so `StarEffect`'s boost takes effect
    immediately). A big `dt` catches up multiple steps in one call, same
    reasoning as `Animator.update()`'s multi-frame catch-up.
    """

    RESPAWN_LENGTH = 3
    RESPAWN_INVINCIBILITY = 1.5

    def __init__(
        self,
        entity_manager: EntityManager,
        event_dispatcher: EventDispatcher,
        food_director: FoodDirector,
        grid_width: int,
        grid_height: int,
    ) -> None:
        """Store collaborators; `set_snake()` is still required before `update()`."""
        self._em = entity_manager
        self._dispatcher = event_dispatcher
        self._food_director = food_director
        self._grid_width = grid_width
        self._grid_height = grid_height
        self._snake: Entity | None = None

    def set_snake(self, snake: Entity) -> None:
        """Set the snake entity this system drives."""
        self._snake = snake

    def queue_direction(self, direction: Cell) -> None:
        """Buffer the next heading, applied (if not a reversal) on the next tick."""
        if not self._snake:
            return
        self._snake.get_component(MoveState).pending_direction = direction

    def update(self, dt: float) -> None:
        """Advance the snake's own movement clock, taking 0+ grid steps."""
        if not self._snake:
            return

        move_state = self._snake.get_component(MoveState)
        trail = self._snake.get_component(Trail)
        stats = self._snake.get_component(StatBlock)
        health = self._snake.get_component(Health)

        move_rate = get_stat(stats, MOVE_RATE_STAT, default=BASE_MOVE_RATE)
        move_interval = 1.0 / move_rate if move_rate > 0 else float("inf")

        move_state.move_timer += dt
        while move_state.move_timer >= move_interval:
            move_state.move_timer -= move_interval
            self._step(move_state, trail, health)

    def _step(self, move_state: MoveState, trail: Trail, health: Health) -> None:
        if move_state.pending_direction is not None:
            dx, dy = move_state.pending_direction
            cx, cy = move_state.direction
            if (dx, dy) != (-cx, -cy):  # reject a 180-degree reversal
                move_state.direction = move_state.pending_direction
            move_state.pending_direction = None

        dx, dy = move_state.direction
        hx, hy = trail.head
        new_head = (hx + dx, hy + dy)

        in_bounds = (
            0 <= new_head[0] < self._grid_width and 0 <= new_head[1] < self._grid_height
        )
        if not in_bounds:
            # The arena boundary always blocks movement, invincible or not
            # -- there's nowhere beyond it to go. Not invincible: a real hit.
            if not health.is_invincible:
                self._handle_death(trail, health, "wall")
            return

        advance(trail, new_head)
        if overlaps_self(trail) and not health.is_invincible:
            self._handle_death(trail, health, "self")
            return
        # Invincible and overlapping self: the advance already happened --
        # the snake passes through its own tail harmlessly, same spirit as
        # a Mario star letting you run through enemies.

        self._check_food(new_head)

    def _check_food(self, cell: Cell) -> None:
        for entity in self._em.get_entities_with(Food):
            food = entity.get_component(Food)
            if food.cell != cell:
                continue
            self._consume_food(entity, food)
            return

    def _consume_food(self, entity: Entity, food: Food) -> None:
        if not self._snake:
            return

        growth, points = _FOOD_VALUE[food.food_type]
        trail = self._snake.get_component(Trail)
        grow(trail, growth)

        score = self._snake.get_component(Score)
        if score:
            score.value += points

        self._food_director.on_food_eaten(food.cell)
        self._em.remove_entity(entity.id)

        self._dispatcher.dispatch(
            FoodEatenEvent(food_type=food.food_type, cell=food.cell, points=points)
        )

        if food.food_type == "star":
            self._apply_star()

    def _apply_star(self) -> None:
        if not self._snake:
            return

        health = self._snake.get_component(Health)
        stats = self._snake.get_component(StatBlock)
        effects = self._snake.get_component(EffectContainer)

        health.current = min(health.max_health, health.current + 1)  # An extra life.

        add_effect(
            self._dispatcher,
            self._snake.id,
            effects,
            StarEffect(stats, health),
            stacking=StackingRule.REFRESH,
        )

    def _handle_death(self, trail: Trail, health: Health, cause: str) -> None:
        if not self._snake:
            return

        apply_damage(
            self._dispatcher,
            self._snake.id,
            health,
            1.0,
            DamageType.TRUE,
            invincibility_duration=self.RESPAWN_INVINCIBILITY,
        )
        self._dispatcher.dispatch(
            SnakeDiedEvent(cause=cause, lives_remaining=int(health.current))
        )

        if health.is_alive:
            self._respawn(trail)
        else:
            score = self._snake.get_component(Score)
            self._dispatcher.dispatch(
                GameOverEvent(final_score=score.value if score else 0)
            )

    def _respawn(self, trail: Trail) -> None:
        if not self._snake:
            return

        cx, cy = self._grid_width // 2, self._grid_height // 2
        reset(trail, [(cx - i, cy) for i in range(self.RESPAWN_LENGTH)])

        move_state = self._snake.get_component(MoveState)
        move_state.direction = (1, 0)
        move_state.pending_direction = None
        move_state.move_timer = 0.0
