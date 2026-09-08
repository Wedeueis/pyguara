"""Tests for input rebinding functionality."""

import pytest

from pyguara.input.binding import KeyBindingManager
from pyguara.input.types import (
    ConflictResolution,
    InputContext,
    InputDevice,
    RebindResult,
)


@pytest.fixture
def binding_manager():
    """Create a fresh binding manager."""
    return KeyBindingManager()


class TestKeyBindingManagerBasics:
    """Tests for basic binding operations."""

    def test_bind_action(self, binding_manager):
        """Test binding an action to a key."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        actions = binding_manager.get_actions(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        )
        assert "jump" in actions

    def test_get_bindings_for_action(self, binding_manager):
        """Test getting bindings for a specific action."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(
            InputDevice.KEYBOARD,
            87,
            "jump",
            InputContext.GAMEPLAY,  # W key
        )

        bindings = binding_manager.get_bindings_for_action(
            "jump", InputContext.GAMEPLAY
        )
        assert len(bindings) == 2
        assert (InputDevice.KEYBOARD, 32) in bindings
        assert (InputDevice.KEYBOARD, 87) in bindings

    def test_unbind_action(self, binding_manager):
        """Test unbinding an action."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.unbind("jump", InputContext.GAMEPLAY)

        actions = binding_manager.get_actions(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        )
        assert "jump" not in actions

    def test_unbind_key(self, binding_manager):
        """Test unbinding all actions from a key."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(
            InputDevice.KEYBOARD, 32, "interact", InputContext.GAMEPLAY
        )

        unbound = binding_manager.unbind_key(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        )

        assert "jump" in unbound
        assert "interact" in unbound
        assert (
            binding_manager.get_actions(InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY)
            == []
        )


class TestConflictDetection:
    """Tests for conflict detection."""

    def test_get_conflicts(self, binding_manager):
        """Test detecting binding conflicts."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)

        conflicts = binding_manager.get_conflicts(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        )
        assert "jump" in conflicts

    def test_get_conflicts_empty(self, binding_manager):
        """Test no conflicts on unused key."""
        conflicts = binding_manager.get_conflicts(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        )
        assert conflicts == []


class TestRebinding:
    """Tests for rebinding operations."""

    def test_rebind_no_conflict(self, binding_manager):
        """Test rebinding when there's no conflict."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)

        result, conflict = binding_manager.rebind(
            "jump",
            InputDevice.KEYBOARD,
            87,  # W key
            InputContext.GAMEPLAY,
        )

        assert result == RebindResult.SUCCESS
        assert conflict is None
        assert binding_manager.get_actions(
            InputDevice.KEYBOARD, 87, InputContext.GAMEPLAY
        ) == ["jump"]
        assert (
            binding_manager.get_actions(InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY)
            == []
        )

    def test_rebind_conflict_error(self, binding_manager):
        """Test rebind raises error on conflict with ERROR strategy."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(
            InputDevice.KEYBOARD,
            69,
            "attack",
            InputContext.GAMEPLAY,  # E key
        )

        with pytest.raises(ValueError, match="Binding conflict"):
            binding_manager.rebind(
                "jump",
                InputDevice.KEYBOARD,
                69,
                InputContext.GAMEPLAY,
                resolution=ConflictResolution.ERROR,
            )

    def test_rebind_conflict_swap(self, binding_manager):
        """Test rebind swaps bindings with SWAP strategy."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.KEYBOARD, 69, "attack", InputContext.GAMEPLAY)

        result, conflict = binding_manager.rebind(
            "jump",
            InputDevice.KEYBOARD,
            69,
            InputContext.GAMEPLAY,
            resolution=ConflictResolution.SWAP,
        )

        assert result == RebindResult.SWAPPED
        assert conflict is not None
        assert "attack" in conflict.existing_actions

        # Jump should now be on E
        assert binding_manager.get_actions(
            InputDevice.KEYBOARD, 69, InputContext.GAMEPLAY
        ) == ["jump"]
        # Attack should now be on Space
        assert binding_manager.get_actions(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        ) == ["attack"]

    def test_rebind_swap_without_prior_binding_reports_unbound(self, binding_manager):
        """SWAP needs one of the action's own keys to trade back to. When the
        action being rebound has never been bound, the conflicting action is
        simply unbound -- the result must say UNBOUND, not SWAPPED."""
        binding_manager.bind(InputDevice.KEYBOARD, 97, "attack", InputContext.GAMEPLAY)

        result, conflict = binding_manager.rebind(
            "block",  # never bound
            InputDevice.KEYBOARD,
            97,
            InputContext.GAMEPLAY,
            resolution=ConflictResolution.SWAP,
        )

        assert result == RebindResult.UNBOUND
        assert conflict is not None and "attack" in conflict.existing_actions
        assert binding_manager.get_actions(
            InputDevice.KEYBOARD, 97, InputContext.GAMEPLAY
        ) == ["block"]
        assert (
            binding_manager.get_bindings_for_action("attack", InputContext.GAMEPLAY)
            == []
        )

    def test_rebind_conflict_unbind(self, binding_manager):
        """Test rebind removes conflicting binding with UNBIND strategy."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.KEYBOARD, 69, "attack", InputContext.GAMEPLAY)

        result, conflict = binding_manager.rebind(
            "jump",
            InputDevice.KEYBOARD,
            69,
            InputContext.GAMEPLAY,
            resolution=ConflictResolution.UNBIND,
        )

        assert result == RebindResult.UNBOUND
        # Jump should now be on E
        assert binding_manager.get_actions(
            InputDevice.KEYBOARD, 69, InputContext.GAMEPLAY
        ) == ["jump"]
        # Attack should be unbound
        assert (
            binding_manager.get_bindings_for_action("attack", InputContext.GAMEPLAY)
            == []
        )

    def test_rebind_conflict_allow(self, binding_manager):
        """Test rebind allows multiple actions with ALLOW strategy."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.KEYBOARD, 69, "attack", InputContext.GAMEPLAY)

        result, conflict = binding_manager.rebind(
            "jump",
            InputDevice.KEYBOARD,
            69,
            InputContext.GAMEPLAY,
            resolution=ConflictResolution.ALLOW,
        )

        assert result == RebindResult.SUCCESS
        # Both actions should be on E
        actions = binding_manager.get_actions(
            InputDevice.KEYBOARD, 69, InputContext.GAMEPLAY
        )
        assert "jump" in actions
        assert "attack" in actions

    def test_rebind_unbound_action_onto_free_key(self, binding_manager):
        """Every other rebind test starts from an already-bound action. An
        action with no current binding must still bind cleanly to a free key."""
        result, conflict = binding_manager.rebind(
            "block", InputDevice.KEYBOARD, 66, InputContext.GAMEPLAY
        )

        assert result == RebindResult.SUCCESS
        assert conflict is None
        assert binding_manager.get_actions(
            InputDevice.KEYBOARD, 66, InputContext.GAMEPLAY
        ) == ["block"]

    def test_rebind_swap_across_devices_and_contexts(self, binding_manager):
        """A SWAP must move every one of the action's existing keys, and only
        within the given context. Prior coverage only swapped a single
        same-device key."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.GAMEPAD, 0, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.MOUSE, 1, "fire", InputContext.GAMEPLAY)
        # Same key in another context must be left untouched.
        binding_manager.bind(InputDevice.MOUSE, 1, "confirm", InputContext.MENU)

        result, _ = binding_manager.rebind(
            "jump",
            InputDevice.MOUSE,
            1,
            InputContext.GAMEPLAY,
            resolution=ConflictResolution.SWAP,
        )

        assert result == RebindResult.SWAPPED
        assert binding_manager.get_actions(
            InputDevice.MOUSE, 1, InputContext.GAMEPLAY
        ) == ["jump"]
        # "fire" landed on both keys "jump" vacated.
        fire_keys = binding_manager.get_bindings_for_action(
            "fire", InputContext.GAMEPLAY
        )
        assert (InputDevice.KEYBOARD, 32) in fire_keys
        assert (InputDevice.GAMEPAD, 0) in fire_keys
        # The MENU binding on the same physical key is unchanged.
        assert binding_manager.get_actions(InputDevice.MOUSE, 1, InputContext.MENU) == [
            "confirm"
        ]


class TestSerialization:
    """Tests for binding import/export."""

    def test_export_bindings(self, binding_manager):
        """Test exporting bindings to dictionary."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.MOUSE, 1, "attack", InputContext.GAMEPLAY)

        data = binding_manager.export_bindings()

        assert data["version"] == 1
        assert "gameplay" in data["bindings"]
        assert "jump" in data["bindings"]["gameplay"]
        assert "attack" in data["bindings"]["gameplay"]

    def test_import_bindings(self, binding_manager):
        """Test importing bindings from dictionary."""
        data = {
            "version": 1,
            "bindings": {
                "gameplay": {
                    "jump": [{"device": "KEYBOARD", "code": 32}],
                    "attack": [{"device": "MOUSE", "code": 1}],
                }
            },
        }

        binding_manager.import_bindings(data)

        assert binding_manager.get_actions(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        ) == ["jump"]
        assert binding_manager.get_actions(
            InputDevice.MOUSE, 1, InputContext.GAMEPLAY
        ) == ["attack"]

    def test_export_import_roundtrip(self, binding_manager):
        """Test that export/import is lossless."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.KEYBOARD, 87, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.MOUSE, 1, "attack", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.GAMEPAD, 0, "confirm", InputContext.UI)

        data = binding_manager.export_bindings()

        # Create new manager and import
        new_manager = KeyBindingManager()
        new_manager.import_bindings(data)

        # Verify all bindings preserved
        assert "jump" in new_manager.get_actions(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        )
        assert "jump" in new_manager.get_actions(
            InputDevice.KEYBOARD, 87, InputContext.GAMEPLAY
        )
        assert "attack" in new_manager.get_actions(
            InputDevice.MOUSE, 1, InputContext.GAMEPLAY
        )
        assert "confirm" in new_manager.get_actions(
            InputDevice.GAMEPAD, 0, InputContext.UI
        )

    def test_import_clears_existing(self, binding_manager):
        """Test that import replaces existing bindings."""
        binding_manager.bind(
            InputDevice.KEYBOARD, 32, "old_action", InputContext.GAMEPLAY
        )

        data = {
            "version": 1,
            "bindings": {
                "gameplay": {"new_action": [{"device": "KEYBOARD", "code": 65}]}
            },
        }

        binding_manager.import_bindings(data)

        # Old binding should be gone
        assert (
            binding_manager.get_actions(InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY)
            == []
        )
        # New binding should exist
        assert "new_action" in binding_manager.get_actions(
            InputDevice.KEYBOARD, 65, InputContext.GAMEPLAY
        )

    def test_import_unsupported_version(self, binding_manager):
        """Test that unsupported version raises error."""
        data = {"version": 999, "bindings": {}}

        with pytest.raises(ValueError, match="Unsupported"):
            binding_manager.import_bindings(data)

    def test_import_current_version_is_accepted(self, binding_manager):
        """The boundary the version guard actually tests -- `> FORMAT_VERSION`
        -- was only ever exercised with 999. The current version must pass."""
        data = {
            "version": KeyBindingManager.BINDING_FORMAT_VERSION,
            "bindings": {"gameplay": {"jump": [{"device": "KEYBOARD", "code": 32}]}},
        }

        binding_manager.import_bindings(data)

        assert binding_manager.get_actions(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        ) == ["jump"]

    def test_import_skips_malformed_entries_without_raising(self, binding_manager):
        """`import_bindings` has warn-and-skip branches for an unknown device,
        an unknown context and a missing key -- none were covered. A user's
        hand-edited or version-drifted file must load what it can."""
        data = {
            "version": 1,
            "bindings": {
                "gameplay": {
                    "jump": [
                        {"device": "KEYBOARD", "code": 32},  # good
                        {"device": "HOLOGRAM", "code": 5},  # unknown device
                        {"code": 9},  # missing "device"
                    ]
                },
                "nonsense_context": {"x": [{"device": "KEYBOARD", "code": 1}]},
            },
        }

        binding_manager.import_bindings(data)  # must not raise

        assert binding_manager.get_actions(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        ) == ["jump"]
        assert binding_manager.get_bindings_for_action(
            "jump", InputContext.GAMEPLAY
        ) == [(InputDevice.KEYBOARD, 32)]

    def test_export_import_roundtrip_survives_real_json(self, binding_manager):
        """The existing roundtrip test keeps the dict in memory. Persistence
        goes through a file, where dict keys become strings and an int `code`
        must come back an int -- `test_config.py`'s exact blind spot."""
        import json

        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.GAMEPAD, 0, "confirm", InputContext.UI)

        data = json.loads(json.dumps(binding_manager.export_bindings()))

        restored = KeyBindingManager()
        restored.import_bindings(data)

        assert restored.get_actions(
            InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY
        ) == ["jump"]
        assert restored.get_actions(InputDevice.GAMEPAD, 0, InputContext.UI) == [
            "confirm"
        ]


class TestResetToDefaults:
    """Tests for reset functionality."""

    def test_reset_to_defaults(self, binding_manager):
        """Test resetting all bindings."""
        binding_manager.bind(InputDevice.KEYBOARD, 32, "jump", InputContext.GAMEPLAY)
        binding_manager.bind(InputDevice.MOUSE, 1, "attack", InputContext.UI)

        binding_manager.reset_to_defaults()

        # All bindings should be cleared
        assert (
            binding_manager.get_actions(InputDevice.KEYBOARD, 32, InputContext.GAMEPLAY)
            == []
        )
        assert binding_manager.get_actions(InputDevice.MOUSE, 1, InputContext.UI) == []
