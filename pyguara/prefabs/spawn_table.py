"""Spawn tables: weighted picks among prefabs, from a seeded stream.

A table names prefabs and how likely each is, so a wave, a room's
contents or a scatter of scenery can be authored as data and rolled the
same way every run with the same seed. `PrefabFactory.spawn` instantiates
what a table picks.

Example:
    table = load_spawn_table("data/cave_enemies.spawn.json")
    goblins = factory.spawn(table, rng, count=5, positions=points)
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyguara import assets
from pyguara.common.random import RandomStream, weighted_choice

__all__ = ["SpawnChoice", "SpawnTable", "load_spawn_table"]


@dataclass(frozen=True)
class SpawnChoice:
    """One prefab a table can pick, and how likely it is.

    Attributes:
        prefab: The prefab's path, as `PrefabFactory.create_from_path` takes it.
        weight: Its odds against the table's other choices; need not sum
            to 1. 0 keeps it in the table without ever picking it.
        overrides: Component data applied on top of the prefab's, as
            `PrefabFactory.create`'s `overrides`.
    """

    prefab: str
    weight: float = 1.0
    overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject a choice that cannot be rolled.

        Raises:
            ValueError: If `prefab` is empty, or `weight` is negative or
                not finite.
        """
        if not self.prefab:
            raise ValueError("a spawn choice needs a prefab path")
        if not (math.isfinite(self.weight) and self.weight >= 0.0):
            raise ValueError(
                f"spawn choice {self.prefab!r} has weight {self.weight}; "
                f"weights must be finite and not negative"
            )


@dataclass(frozen=True)
class SpawnTable:
    """Weighted choices among prefabs.

    Attributes:
        choices: What the table can pick. Their order does not change the
            odds, but does change which choice a given seed picks.
    """

    choices: tuple[SpawnChoice, ...]

    def __post_init__(self) -> None:
        """Reject a table nothing can be picked from.

        Raises:
            ValueError: If there are no choices, or every weight is 0.
        """
        if not self.choices:
            raise ValueError("a spawn table needs at least one choice")
        if sum(choice.weight for choice in self.choices) <= 0.0:
            raise ValueError("a spawn table needs a choice with a positive weight")

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> SpawnTable:
        """Build a table from `{"choices": [{"prefab": ..., "weight": ...}]}`.

        Each choice may also carry `"overrides"`. `"weight"` defaults to 1.

        Raises:
            ValueError: If the data is not shaped like that, or a choice
                or the table is invalid.
        """
        raw = data.get("choices")
        if not isinstance(raw, list):
            raise ValueError('a spawn table needs a "choices" list')
        choices = []
        for index, entry in enumerate(raw):
            if not isinstance(entry, Mapping) or not isinstance(
                entry.get("prefab"), str
            ):
                raise ValueError(f'spawn table choice {index} needs a "prefab" path')
            unknown = set(entry) - {"prefab", "weight", "overrides"}
            if unknown:
                raise ValueError(
                    f"spawn table choice {index} has unknown keys {sorted(unknown)}; "
                    f'a choice takes "prefab", "weight" and "overrides"'
                )
            weight = entry.get("weight", 1.0)
            if isinstance(weight, bool) or not isinstance(weight, int | float):
                raise ValueError(
                    f"spawn table choice {index} has a weight of {weight!r}"
                )
            choices.append(
                SpawnChoice(
                    prefab=entry["prefab"],
                    weight=float(weight),
                    overrides=entry.get("overrides", {}),
                )
            )
        return cls(tuple(choices))

    def pick(self, rng: RandomStream) -> SpawnChoice:
        """Pick one choice, weighted."""
        return weighted_choice(
            rng, [(choice, choice.weight) for choice in self.choices]
        )

    def pick_many(
        self, rng: RandomStream, count: int, *, unique: bool = False
    ) -> list[SpawnChoice]:
        """Pick `count` choices, weighted, each independently or all different.

        Args:
            rng: The seeded stream to roll on.
            count: How many to pick.
            unique: Pick each choice at most once, re-weighting the rest
                after each pick.

        Raises:
            ValueError: If `count` is negative, or `unique` asks for more
                choices than have a positive weight.
        """
        if count < 0:
            raise ValueError(f"cannot pick {count} choices")
        if not unique:
            return [self.pick(rng) for _ in range(count)]
        left = [choice for choice in self.choices if choice.weight > 0.0]
        if count > len(left):
            raise ValueError(
                f"cannot pick {count} different choices from {len(left)} with a "
                f"positive weight"
            )
        picked = []
        for _ in range(count):
            choice = weighted_choice(rng, [(c, c.weight) for c in left])
            left.remove(choice)
            picked.append(choice)
        return picked


def load_spawn_table(path: str | Path) -> SpawnTable:
    """Read a spawn table from a JSON file, loose or in a mounted pack.

    Raises:
        FileNotFoundError: If there is no such file.
        ValueError: If it is not valid JSON or not a valid table. The
            message names the file.
    """
    if not assets.is_file(Path(path)):
        raise FileNotFoundError(f"spawn table not found: {path}")
    try:
        data = json.loads(assets.read_text(Path(path)))
        if not isinstance(data, Mapping):
            raise ValueError("the file is not a JSON object")
        return SpawnTable.from_data(data)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from error
