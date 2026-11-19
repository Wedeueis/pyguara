"""The day, the stamina that fills it, and what each action costs.

The garden is turn-based: a day is the turn, and nothing in the simulation
moves while you are in one. Stamina is what makes a day finite -- you wake
with `MAX_STAMINA`, every action on a cell spends some, and when it runs out
there is nothing left to do but sleep (`systems/day_resolver.py` is what a
night actually *does*).

Only acting on the plot costs. Choosing a tool, reading the inspector,
opening the store and the pause menu are free: charging for looking would
make the player stop looking, which is the opposite of what this game is
for. Building is free too -- the structure was already paid for in Sementes
at the store.
"""

from __future__ import annotations

from dataclasses import dataclass

SESSION_DAYS = 12
"""Days a session runs before the evaluation. The PRD's arc -- first seeds,
stratification, the pest fork, automation -- with room to recover from a bad
call and still be scored on the garden it left behind."""

MAX_STAMINA = 12
"""Stamina a full night restores. Around eight to ten actions, so a day is a
real choice between watering what is planted and breaking new ground."""

TILL_COST = 2
PLANT_COST = 1
WATER_COST = 1
COMPOST_COST = 2
SPRAY_COST = 3
HARVEST_COST = 1
BUILD_COST = 0
FREE = 0

_COSTS = {
    "till": TILL_COST,
    "water": WATER_COST,
    "harvest": HARVEST_COST,
    "compost": COMPOST_COST,
    "spray": SPRAY_COST,
}
"""Fixed-cost tools. Species and structures are prefix-matched below, so a
new one costs the right thing without being listed twice."""


def action_cost(tool: str) -> int:
    """What one use of `tool` costs in stamina.

    Args:
        tool: A tool id as `scenes.GardenScene` knows it, e.g. `"till"`,
            `"plant_baru"` or `"build_solar_panel"`.

    Returns:
        The cost. An unknown tool costs nothing rather than raising: a tool
        the table has not been taught about yet should be free, not
        unusable.
    """
    if tool.startswith("plant_"):
        return PLANT_COST
    if tool.startswith("build_"):
        return BUILD_COST
    return _COSTS.get(tool, FREE)


@dataclass
class DayCycle:
    """Which day it is and how much energy is left in it.

    Attributes:
        day: The current day, 1-based.
        stamina: Energy left today.
        max_stamina: What a night restores.
    """

    day: int = 1
    stamina: int = MAX_STAMINA
    max_stamina: int = MAX_STAMINA

    def can_afford(self, cost: int) -> bool:
        """Whether `cost` stamina is available.

        Args:
            cost: The stamina an action would spend.

        Returns:
            Whether there is enough left today.
        """
        return self.stamina >= cost

    def spend(self, cost: int) -> bool:
        """Spend `cost` stamina, if there is enough.

        Call it only once an action has actually happened: an action refused
        for any other reason (untilled ground, no Sementes) must cost
        nothing, or the day drains on clicks that did nothing.

        Args:
            cost: The stamina to spend.

        Returns:
            Whether it was spent.
        """
        if not self.can_afford(cost):
            return False
        self.stamina -= cost
        return True

    def sleep(self) -> None:
        """End the day: the next one begins with a full pool.

        Stamina does not carry over. A day you end early is a day you chose
        to end, not energy you banked.
        """
        self.day += 1
        self.stamina = self.max_stamina

    @property
    def exhausted(self) -> bool:
        """Whether nothing affordable is left -- the prompt to sleep."""
        return self.stamina <= 0

    @property
    def is_final_day(self) -> bool:
        """Whether sleeping tonight ends the session and scores the garden."""
        return self.day >= SESSION_DAYS
