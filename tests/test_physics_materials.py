"""Tests for physics material presets."""

import pytest

from pyguara.physics.materials import Materials, MaterialConstants
from pyguara.physics.types import PhysicsMaterial


class TestMaterialPresets:
    """Test material preset definitions and properties."""

    def test_materials_singleton_exists(self):
        """Materials singleton should be accessible."""
        assert Materials is not None
        assert isinstance(Materials, MaterialConstants)

    def test_default_material(self):
        """DEFAULT material should have balanced properties."""
        mat = Materials.DEFAULT
        assert isinstance(mat, PhysicsMaterial)
        assert mat.friction == 0.5
        assert mat.restitution == 0.0
        assert mat.density == 1.0

    def test_wood_material(self):
        """WOOD material should have moderate friction and slight bounce."""
        mat = Materials.WOOD
        assert mat.friction == 0.6
        assert mat.restitution == 0.3
        assert mat.density == 0.7

    def test_metal_material(self):
        """METAL material should have lower friction, high density."""
        mat = Materials.METAL
        assert mat.friction == 0.4
        assert mat.restitution == 0.2
        assert mat.density == 8.0

    def test_stone_material(self):
        """STONE material should have high friction, low bounce."""
        mat = Materials.STONE
        assert mat.friction == 0.8
        assert mat.restitution == 0.1
        assert mat.density == 2.5

    def test_rubber_material(self):
        """RUBBER material should have high friction and bounce."""
        mat = Materials.RUBBER
        assert mat.friction == 0.9
        assert mat.restitution == 0.8
        assert mat.density == 1.1

    def test_ice_material(self):
        """ICE material should be very slippery (low friction)."""
        mat = Materials.ICE
        assert mat.friction == 0.05
        assert mat.restitution == 0.1
        assert mat.density == 0.9

    def test_glass_material(self):
        """GLASS material should have low friction, high bounce."""
        mat = Materials.GLASS
        assert mat.friction == 0.1
        assert mat.restitution == 0.7
        assert mat.density == 2.4

    def test_super_ball_material(self):
        """SUPER_BALL material should be extremely bouncy."""
        mat = Materials.SUPER_BALL
        assert mat.friction == 0.6
        assert mat.restitution == 0.95
        assert mat.density == 1.0

    def test_player_material(self):
        """PLAYER material should have good traction, no bounce."""
        mat = Materials.PLAYER
        assert mat.friction == 0.7
        assert mat.restitution == 0.0
        assert mat.density == 1.0

    def test_ground_material(self):
        """GROUND material should have good traction, no bounce, zero density."""
        mat = Materials.GROUND
        assert mat.friction == 0.7
        assert mat.restitution == 0.0
        assert mat.density == 0.0

    def test_material_instances_are_independent(self):
        """Material preset instances should be independent objects."""
        # Each material should be a separate instance
        assert Materials.DEFAULT is not Materials.WOOD
        assert Materials.PLAYER is not Materials.GROUND

        # Modifying one shouldn't affect others (they're independent instances)
        # Note: While materials themselves are mutable, the presets are
        # independent instances, so users can safely use them

    def test_materials_have_unique_properties(self):
        """Each material should have distinct properties."""
        materials = [
            Materials.DEFAULT,
            Materials.WOOD,
            Materials.METAL,
            Materials.STONE,
            Materials.RUBBER,
            Materials.ICE,
            Materials.GLASS,
            Materials.SUPER_BALL,
            Materials.PLAYER,
            Materials.GROUND,
        ]

        # Check that at least some materials differ
        frictions = {mat.friction for mat in materials}
        restitutions = {mat.restitution for mat in materials}
        densities = {mat.density for mat in materials}

        assert len(frictions) > 5, "Materials should have varied friction values"
        assert len(restitutions) > 3, "Materials should have varied restitution values"
        assert len(densities) > 5, "Materials should have varied density values"

    def test_material_instances_are_physics_materials(self):
        """All preset materials should be PhysicsMaterial instances."""
        materials = [
            Materials.DEFAULT,
            Materials.WOOD,
            Materials.METAL,
            Materials.STONE,
            Materials.RUBBER,
            Materials.ICE,
            Materials.GLASS,
            Materials.SUPER_BALL,
            Materials.PLAYER,
            Materials.GROUND,
        ]

        for mat in materials:
            assert isinstance(mat, PhysicsMaterial)


class TestMaterialUsage:
    """Test practical usage of material presets."""

    def test_material_can_be_used_in_collider(self):
        """Materials should be compatible with Collider component."""
        from pyguara.physics.components import Collider
        from pyguara.physics.types import ShapeType

        collider = Collider(
            shape_type=ShapeType.BOX,
            dimensions=[32, 64],
            material=Materials.PLAYER,
        )

        assert collider.material == Materials.PLAYER
        assert collider.material.friction == 0.7

    def test_multiple_materials_in_scene(self):
        """Multiple colliders can use different materials."""
        from pyguara.physics.components import Collider
        from pyguara.physics.types import ShapeType

        player_collider = Collider(
            shape_type=ShapeType.BOX,
            dimensions=[32, 64],
            material=Materials.PLAYER,
        )

        ground_collider = Collider(
            shape_type=ShapeType.BOX,
            dimensions=[800, 32],
            material=Materials.GROUND,
        )

        ice_collider = Collider(
            shape_type=ShapeType.BOX,
            dimensions=[100, 100],
            material=Materials.ICE,
        )

        assert player_collider.material.friction == 0.7
        assert ground_collider.material.friction == 0.7
        assert ice_collider.material.friction == 0.05

    def test_material_constants_class_is_frozen(self):
        """MaterialConstants class itself should be frozen."""
        with pytest.raises(AttributeError):
            Materials.NEW_MATERIAL = PhysicsMaterial(1.0, 1.0, 1.0)  # type: ignore


class TestMaterialPhysicsRealism:
    """Test that material properties follow physical realism."""

    def test_friction_values_in_valid_range(self):
        """All friction values should be in valid range [0, 1+]."""
        materials = [
            Materials.DEFAULT,
            Materials.WOOD,
            Materials.METAL,
            Materials.STONE,
            Materials.RUBBER,
            Materials.ICE,
            Materials.GLASS,
            Materials.SUPER_BALL,
            Materials.PLAYER,
            Materials.GROUND,
        ]

        for mat in materials:
            assert 0.0 <= mat.friction <= 1.0, f"Invalid friction: {mat.friction}"

    def test_restitution_values_in_valid_range(self):
        """All restitution values should be in valid range [0, 1]."""
        materials = [
            Materials.DEFAULT,
            Materials.WOOD,
            Materials.METAL,
            Materials.STONE,
            Materials.RUBBER,
            Materials.ICE,
            Materials.GLASS,
            Materials.SUPER_BALL,
            Materials.PLAYER,
            Materials.GROUND,
        ]

        for mat in materials:
            assert 0.0 <= mat.restitution <= 1.0, (
                f"Invalid restitution: {mat.restitution}"
            )

    def test_density_values_are_non_negative(self):
        """All density values should be non-negative."""
        materials = [
            Materials.DEFAULT,
            Materials.WOOD,
            Materials.METAL,
            Materials.STONE,
            Materials.RUBBER,
            Materials.ICE,
            Materials.GLASS,
            Materials.SUPER_BALL,
            Materials.PLAYER,
            Materials.GROUND,
        ]

        for mat in materials:
            assert mat.density >= 0.0, f"Invalid density: {mat.density}"

    def test_ice_is_slipperiest(self):
        """ICE should have the lowest friction among all materials."""
        materials = [
            Materials.DEFAULT,
            Materials.WOOD,
            Materials.METAL,
            Materials.STONE,
            Materials.RUBBER,
            Materials.GLASS,
            Materials.SUPER_BALL,
            Materials.PLAYER,
            Materials.GROUND,
        ]

        for mat in materials:
            assert Materials.ICE.friction <= mat.friction

    def test_super_ball_is_bounciest(self):
        """SUPER_BALL should have the highest restitution."""
        materials = [
            Materials.DEFAULT,
            Materials.WOOD,
            Materials.METAL,
            Materials.STONE,
            Materials.RUBBER,
            Materials.ICE,
            Materials.GLASS,
            Materials.PLAYER,
            Materials.GROUND,
        ]

        for mat in materials:
            assert Materials.SUPER_BALL.restitution >= mat.restitution

    def test_metal_has_highest_density(self):
        """METAL should have the highest density among all materials."""
        materials = [
            Materials.DEFAULT,
            Materials.WOOD,
            Materials.STONE,
            Materials.RUBBER,
            Materials.ICE,
            Materials.GLASS,
            Materials.SUPER_BALL,
            Materials.PLAYER,
            Materials.GROUND,
        ]

        for mat in materials:
            assert Materials.METAL.density >= mat.density
