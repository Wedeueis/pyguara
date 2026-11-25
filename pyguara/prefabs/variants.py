"""Named variants: a prefab plus changes, looked up by name.

A variant such as "elite_goblin" is the goblin prefab with some fields
replaced and some numbers scaled, authored once in a library rather than
as an `extends` file per variant or overrides repeated at every spawn
site. `VariantLibrary.resolver` wraps a prefab resolver so that a variant
name works wherever a prefab path does: `create_from_path`, a spawn
table's choice, a child, or another variant's base.

Example:
    variants = load_variants("data/enemies.variants.json")
    factory = PrefabFactory(manager, registry, variants.resolver(cache.load))
    elite = factory.create_from_path("elite_goblin")
"""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyguara import assets
from pyguara.prefabs.types import PrefabData

__all__ = ["PrefabVariant", "VariantLibrary", "load_variants"]

PrefabResolver = Callable[[str], PrefabData | None]

_KEYS = {"base", "overrides", "multiply", "tags"}


@dataclass(frozen=True)
class PrefabVariant:
    """A prefab with some of its component data changed.

    Attributes:
        name: What the variant is looked up by. Not a path: it may not
            contain a slash, a backslash or a dot, so it cannot shadow a path.
        base: The prefab path, or another variant's name, it starts from.
        overrides: Component data merged over the base's, as
            `PrefabFactory.create`'s `overrides`.
        multiply: Factors for numeric fields the base already has, nested
            the same way as component data. An int field stays an int,
            rounded to the nearest. A field may not be both multiplied and
            overridden.
        tags: Added to the base's tags.
    """

    name: str
    base: str
    overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    multiply: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject a variant that names itself like a path or has no base.

        Raises:
            ValueError: If `name` is empty or path-like, `base` is empty, a
                factor is not a finite non-negative number, or a field is
                both multiplied and overridden.
        """
        if not self.name or any(mark in self.name for mark in "/\\."):
            raise ValueError(
                f"variant name {self.name!r} must be non-empty and contain no "
                f"'/', '\\\\' or '.', so it cannot be mistaken for a path"
            )
        if not self.base:
            raise ValueError(f"variant {self.name!r} needs a base")
        _check_factors(self.name, self.multiply, [])
        _check_disjoint(self.name, self.multiply, self.overrides, [])


class VariantLibrary:
    """Variants by name, and a resolver that knows them."""

    def __init__(self, variants: Mapping[str, PrefabVariant] | None = None) -> None:
        """Hold `variants`, keyed by their names.

        Raises:
            ValueError: If a key differs from its variant's name.
        """
        self._variants: dict[str, PrefabVariant] = {}
        for key, variant in (variants or {}).items():
            if key != variant.name:
                raise ValueError(f"variant {variant.name!r} is filed as {key!r}")
            self._variants[key] = variant

    def add(self, variant: PrefabVariant) -> None:
        """Add a variant, replacing any of the same name."""
        self._variants[variant.name] = variant

    def __contains__(self, name: object) -> bool:
        """Return whether a variant of this name exists."""
        return name in self._variants

    def __len__(self) -> int:
        """Return how many variants the library holds."""
        return len(self._variants)

    def names(self) -> list[str]:
        """Return every variant's name, sorted."""
        return sorted(self._variants)

    def resolver(self, base: PrefabResolver) -> PrefabResolver:
        """Return a resolver that builds variants and passes paths to `base`.

        A variant comes back as prefab data with its base's `extends` chain
        already applied, its multipliers and overrides on top, its base's
        children, and the tags of both. A variant whose base does not
        resolve comes back as None, as a missing prefab does.

        Raises:
            ValueError: When resolving a variant whose bases form a cycle,
                or that multiplies a field its base lacks or holds as
                something other than a number.
        """
        return lambda name: self._resolve(name, base, [])

    def _resolve(
        self, name: str, base: PrefabResolver, chain: list[str]
    ) -> PrefabData | None:
        variant = self._variants.get(name)
        if variant is None:
            return base(name)
        if name in chain:
            raise ValueError(f"variant cycle: {' -> '.join([*chain, name])}")
        parent = self._resolve(variant.base, base, [*chain, name])
        if parent is None:
            return None
        components = _resolve_components(parent, base)
        _multiply(variant.name, components, variant.multiply, [])
        components = _merge(components, variant.overrides)
        return PrefabData(
            name=variant.name,
            version=parent.version,
            components=components,
            children=copy.deepcopy(parent.children),
            tags=[*parent.tags, *(t for t in variant.tags if t not in parent.tags)],
        )


def load_variants(path: str | Path) -> VariantLibrary:
    """Read a library from `{"variants": {name: {"base": ..., ...}}}` JSON.

    A variant takes `"base"`, and optionally `"overrides"`, `"multiply"`
    and `"tags"`. The file may be loose or in a mounted pack.

    Raises:
        FileNotFoundError: If there is no such file.
        ValueError: If it is not valid JSON or a variant is invalid. The
            message names the file.
    """
    if not assets.is_file(Path(path)):
        raise FileNotFoundError(f"variant library not found: {path}")
    try:
        data = json.loads(assets.read_text(Path(path)))
        if not isinstance(data, Mapping) or not isinstance(
            data.get("variants"), Mapping
        ):
            raise ValueError('a variant library needs a "variants" object')
        library = VariantLibrary()
        for name, entry in data["variants"].items():
            library.add(_variant_from_data(name, entry))
        return library
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from error


def _resolve_components(
    prefab: PrefabData, resolver: PrefabResolver
) -> dict[str, dict[str, Any]]:
    """Return a copy of a prefab's component data with `extends` applied.

    Raises:
        ValueError: If the `extends` chain has a cycle or names a prefab
            that does not resolve.
    """
    chain: list[str] = []
    layers = [prefab.components]
    current = prefab
    while current.extends:
        if current.extends in chain:
            raise ValueError(
                f"Prefab inheritance cycle detected: "
                f"{' -> '.join([*chain, current.extends])}"
            )
        chain.append(current.extends)
        parent = resolver(current.extends)
        if parent is None:
            raise ValueError(
                f"prefab {current.name!r} extends {current.extends!r}, "
                f"which did not load"
            )
        layers.append(parent.components)
        current = parent
    merged: dict[str, Any] = {}
    for layer in reversed(layers):
        merged = _merge(merged, layer)
    return merged


def _variant_from_data(name: str, entry: Any) -> PrefabVariant:
    if not isinstance(entry, Mapping) or not isinstance(entry.get("base"), str):
        raise ValueError(f'variant {name!r} needs a "base"')
    unknown = set(entry) - _KEYS
    if unknown:
        raise ValueError(
            f"variant {name!r} has unknown keys {sorted(unknown)}; a variant "
            f'takes "base", "overrides", "multiply" and "tags"'
        )
    for key in ("overrides", "multiply"):
        if not isinstance(entry.get(key, {}), Mapping):
            raise ValueError(f'variant {name!r}: "{key}" must be an object')
    tags = entry.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError(f'variant {name!r}: "tags" must be a list of strings')
    return PrefabVariant(
        name=name,
        base=entry["base"],
        overrides=entry.get("overrides", {}),
        multiply=entry.get("multiply", {}),
        tags=tuple(tags),
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _check_factors(name: str, factors: Mapping[str, Any], at: list[str]) -> None:
    for key, factor in factors.items():
        here = [*at, key]
        if isinstance(factor, Mapping):
            _check_factors(name, factor, here)
        elif not (_is_number(factor) and math.isfinite(factor) and factor >= 0):
            raise ValueError(
                f"variant {name!r} multiplies {'.'.join(here)} by {factor!r}; "
                f"a factor must be a finite number, not negative"
            )


def _check_disjoint(
    name: str, factors: Mapping[str, Any], overrides: Mapping[str, Any], at: list[str]
) -> None:
    for key, factor in factors.items():
        if key not in overrides:
            continue
        here = [*at, key]
        if isinstance(factor, Mapping) and isinstance(overrides[key], Mapping):
            _check_disjoint(name, factor, overrides[key], here)
        else:
            raise ValueError(
                f"variant {name!r} both multiplies and overrides {'.'.join(here)}"
            )


def _multiply(
    name: str, data: dict[str, Any], factors: Mapping[str, Any], at: list[str]
) -> None:
    for key, factor in factors.items():
        here = [*at, key]
        if key not in data:
            raise ValueError(
                f"variant {name!r} multiplies {'.'.join(here)}, which its base "
                f"does not set"
            )
        value = data[key]
        if isinstance(factor, Mapping):
            if not isinstance(value, dict):
                raise ValueError(
                    f"variant {name!r} multiplies fields of {'.'.join(here)}, "
                    f"which is {value!r}"
                )
            _multiply(name, value, factor, here)
        elif not _is_number(value):
            raise ValueError(
                f"variant {name!r} multiplies {'.'.join(here)}, which is "
                f"{value!r}, not a number"
            )
        elif isinstance(value, int):
            data[key] = round(value * factor)
        else:
            data[key] = value * factor


def _merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, Mapping):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
