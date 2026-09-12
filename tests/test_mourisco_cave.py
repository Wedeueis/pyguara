"""Tests for Mourisco's cave geometry and its DDA ray march.

The march is what makes rock cast an acoustic shadow, so its occlusion
rule is the single most load-bearing piece of the demo: if a ray ran past
a solid tile, a pulse would light straight through walls and the game
would have no shape at all.
"""

from __future__ import annotations

from games.mourisco_ressonancia.cave import (
    TILE,
    CaveLayout,
    exposed_faces,
    generate_cave,
    march,
    parse_cave,
)
from pyguara.common.types import Vector2


def _open_room(width: int = 10, height: int = 10) -> CaveLayout:
    """A hollow box: solid border, open interior."""
    rows = []
    for y in range(height):
        if y in (0, height - 1):
            rows.append("#" * width)
        else:
            rows.append("#" + "." * (width - 2) + "#")
    return parse_cave(rows)


# ========== parsing ==========


class TestParseCave:
    def test_it_reads_solids_and_spawns(self) -> None:
        layout = parse_cave(["####", "#P.#", "#.E#", "####"])
        assert layout.width == 4
        assert layout.height == 4
        assert layout.is_solid((0, 0))
        assert not layout.is_solid((1, 1))
        assert layout.player_spawn == Vector2(TILE * 1.5, TILE * 1.5)
        assert layout.exit_position == Vector2(TILE * 2.5, TILE * 2.5)

    def test_creature_markers_become_spawn_points(self) -> None:
        layout = parse_cave(["#####", "#s.b#", "#####"])
        assert len(layout.spider_perches) == 1
        assert len(layout.bat_roosts) == 1

    def test_out_of_bounds_counts_as_solid(self) -> None:
        """So a ray leaving the map stops rather than running forever."""
        layout = _open_room()
        assert layout.is_solid((-1, 5))
        assert layout.is_solid((999, 5))


class TestExposedFaces:
    def test_only_tiles_touching_open_air_are_returned(self) -> None:
        # A 5x5 block of rock inside a larger solid field: the very centre
        # touches no open air and must be excluded.
        rows = ["#" * 7 for _ in range(7)]
        rows[3] = "###.###"
        layout = parse_cave(rows)
        faces = {cell for cell, _rect in exposed_faces(layout)}
        assert (3, 2) in faces  # directly above the opening
        assert (0, 0) not in faces  # buried corner, can never be seen


# ========== the march ==========


class TestMarch:
    def test_a_ray_stops_at_the_first_solid_tile(self) -> None:
        layout = _open_room(width=10, height=6)
        origin = Vector2(TILE * 1.5, TILE * 2.5)
        crossed = march(layout, origin, Vector2(1, 0), TILE * 20)

        cells = [cell for _distance, cell in crossed]
        # The wall at x=9 is included (it is the lit surface); nothing past.
        assert cells[-1] == (9, 2)
        assert all(cell[0] <= 9 for cell in cells)

    def test_the_surface_it_stops_on_is_included(self) -> None:
        """The wall is what the pulse illuminates, so it must be revealed."""
        layout = _open_room()
        crossed = march(
            layout, Vector2(TILE * 1.5, TILE * 1.5), Vector2(-1, 0), TILE * 5
        )
        assert crossed[-1][1] == (0, 1)

    def test_distances_increase_monotonically(self) -> None:
        layout = _open_room(width=12, height=12)
        crossed = march(
            layout, Vector2(TILE * 1.5, TILE * 1.5), Vector2(1, 1), TILE * 12
        )
        distances = [distance for distance, _cell in crossed]
        assert distances == sorted(distances)

    def test_each_crossed_cell_appears_once(self) -> None:
        layout = _open_room(width=12, height=12)
        crossed = march(
            layout, Vector2(TILE * 1.5, TILE * 1.5), Vector2(1, 0.37), TILE * 12
        )
        cells = [cell for _distance, cell in crossed]
        assert len(cells) == len(set(cells))

    def test_a_diagonal_ray_walks_a_connected_path(self) -> None:
        """No gaps at grazing angles -- consecutive cells always touch."""
        layout = _open_room(width=14, height=14)
        crossed = march(
            layout, Vector2(TILE * 1.5, TILE * 1.5), Vector2(1, 0.6), TILE * 14
        )
        cells = [cell for _distance, cell in crossed]
        for before, after in zip(cells, cells[1:], strict=False):
            assert abs(after[0] - before[0]) + abs(after[1] - before[1]) == 1

    def test_an_axis_parallel_ray_does_not_divide_by_zero(self) -> None:
        layout = _open_room()
        for direction in (Vector2(0, 1), Vector2(0, -1), Vector2(1, 0), Vector2(-1, 0)):
            assert march(layout, Vector2(TILE * 1.5, TILE * 1.5), direction, TILE * 5)

    def test_a_zero_length_direction_yields_nothing(self) -> None:
        layout = _open_room()
        assert march(layout, Vector2(50, 50), Vector2(0, 0), 100.0) == []

    def test_zero_distance_yields_nothing(self) -> None:
        layout = _open_room()
        assert march(layout, Vector2(50, 50), Vector2(1, 0), 0.0) == []


# ========== the generated cave ==========


class TestGeneratedCave:
    def test_it_is_deterministic_for_a_seed(self) -> None:
        assert generate_cave(7) == generate_cave(7)

    def test_it_is_sealed_by_a_solid_border(self) -> None:
        """Nothing may walk or see out of the map."""
        rows = generate_cave()
        assert set(rows[0]) == {"#"}
        assert set(rows[-1]) == {"#"}
        assert all(row[0] == "#" and row[-1] == "#" for row in rows)

    def test_it_is_mostly_rock(self) -> None:
        """Solid-first is what makes a pulse light a nearby wall at all."""
        rows = generate_cave()
        open_cells = sum(row.count(".") for row in rows)
        total = len(rows) * len(rows[0])
        assert 0.1 < open_cells / total < 0.6

    def test_the_spawn_and_exit_are_both_in_open_air(self) -> None:
        layout = parse_cave(generate_cave())
        spawn_cell = (
            int(layout.player_spawn.x // TILE),
            int(layout.player_spawn.y // TILE),
        )
        exit_cell = (
            int(layout.exit_position.x // TILE),
            int(layout.exit_position.y // TILE),
        )
        assert not layout.is_solid(spawn_cell)
        assert not layout.is_solid(exit_cell)

    def test_the_exit_is_reachable_from_the_spawn(self) -> None:
        """A cave you cannot finish is not a level."""
        layout = parse_cave(generate_cave())
        start = (
            int(layout.player_spawn.x // TILE),
            int(layout.player_spawn.y // TILE),
        )
        goal = (
            int(layout.exit_position.x // TILE),
            int(layout.exit_position.y // TILE),
        )

        seen = {start}
        frontier = [start]
        while frontier:
            x, y = frontier.pop()
            if (x, y) == goal:
                break
            for neighbour in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbour in seen or layout.is_solid(neighbour):
                    continue
                seen.add(neighbour)
                frontier.append(neighbour)

        assert goal in seen
