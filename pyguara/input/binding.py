"""Key binding management."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from pyguara.input.types import (
    BindingConflict,
    ConflictResolution,
    InputContext,
    InputDevice,
    RebindResult,
)

logger = logging.getLogger(__name__)

# Binding Key: (DeviceType, KeyCode/AxisIndex)
BindingKey = Tuple[InputDevice, int]


class KeyBindingManager:
    """Maps physical inputs (Device + Code) to Actions.

    Supports runtime rebinding, conflict detection, and serialization
    for persistence of user preferences.
    """

    # Current serialization format version
    BINDING_FORMAT_VERSION = 1

    def __init__(self) -> None:
        """Initialize the binding manager with default contexts."""
        # Map: Context -> BindingKey -> List[ActionName]
        self._bindings: Dict[str, Dict[BindingKey, List[str]]] = {}
        # Reverse map for quick action lookup: Context -> ActionName -> List[BindingKey]
        self._action_bindings: Dict[str, Dict[str, List[BindingKey]]] = {}

        for ctx in InputContext:
            self._bindings[ctx.value] = {}
            self._action_bindings[ctx.value] = {}

    def bind(
        self,
        device: InputDevice,
        code: int,
        action: str,
        context: InputContext = InputContext.GAMEPLAY,
    ) -> None:
        """Bind a physical input to an action.

        Args:
            device: Input device type.
            code: Key/button code.
            action: Action name to bind.
            context: Input context for this binding.
        """
        ctx_name = context.value
        ctx_map = self._bindings.setdefault(ctx_name, {})
        key: BindingKey = (device, code)

        if key not in ctx_map:
            ctx_map[key] = []

        if action not in ctx_map[key]:
            ctx_map[key].append(action)

        # Update reverse mapping
        action_map = self._action_bindings.setdefault(ctx_name, {})
        if action not in action_map:
            action_map[action] = []
        if key not in action_map[action]:
            action_map[action].append(key)

    def get_actions(
        self, device: InputDevice, code: int, context: InputContext
    ) -> List[str]:
        """Lookup actions for a specific device input.

        Args:
            device: Input device type.
            code: Key/button code.
            context: Input context to check.

        Returns:
            List of action names bound to this input.
        """
        key: BindingKey = (device, code)
        return self._bindings.get(context.value, {}).get(key, [])

    def get_bindings_for_action(
        self, action: str, context: InputContext
    ) -> List[BindingKey]:
        """Get all bindings for a specific action.

        Args:
            action: Action name to look up.
            context: Input context to check.

        Returns:
            List of binding keys for this action.
        """
        return self._action_bindings.get(context.value, {}).get(action, [])

    def unbind(self, action: str, context: InputContext) -> None:
        """Remove all bindings for an action.

        Args:
            action: Action name to unbind.
            context: Input context to modify.
        """
        ctx_name = context.value

        # Get bindings for this action
        bindings = self._action_bindings.get(ctx_name, {}).get(action, [])

        # Remove from primary bindings map
        ctx_bindings = self._bindings.get(ctx_name, {})
        for key in bindings:
            if key in ctx_bindings and action in ctx_bindings[key]:
                ctx_bindings[key].remove(action)
                if not ctx_bindings[key]:
                    del ctx_bindings[key]

        # Remove from reverse mapping
        if ctx_name in self._action_bindings:
            self._action_bindings[ctx_name].pop(action, None)

        logger.debug(f"Unbound action '{action}' from context '{ctx_name}'")

    def unbind_key(
        self, device: InputDevice, code: int, context: InputContext
    ) -> List[str]:
        """Remove all action bindings from a specific key.

        Args:
            device: Input device type.
            code: Key/button code.
            context: Input context to modify.

        Returns:
            List of actions that were unbound.
        """
        key: BindingKey = (device, code)
        ctx_name = context.value

        # Get actions bound to this key
        actions = self._bindings.get(ctx_name, {}).get(key, []).copy()

        # Remove from primary bindings
        if ctx_name in self._bindings and key in self._bindings[ctx_name]:
            del self._bindings[ctx_name][key]

        # Remove from reverse mapping
        for action in actions:
            if (
                ctx_name in self._action_bindings
                and action in self._action_bindings[ctx_name]
            ):
                if key in self._action_bindings[ctx_name][action]:
                    self._action_bindings[ctx_name][action].remove(key)

        return actions

    def get_conflicts(
        self, device: InputDevice, code: int, context: InputContext
    ) -> List[str]:
        """Get actions already bound to a key.

        Args:
            device: Input device type.
            code: Key/button code.
            context: Input context to check.

        Returns:
            List of action names already bound to this key.
        """
        key: BindingKey = (device, code)
        return self._bindings.get(context.value, {}).get(key, []).copy()

    def rebind(
        self,
        action: str,
        new_device: InputDevice,
        new_code: int,
        context: InputContext,
        resolution: ConflictResolution = ConflictResolution.ERROR,
    ) -> Tuple[RebindResult, Optional[BindingConflict]]:
        """Rebind an action to a new key with conflict handling.

        Args:
            action: Action name to rebind.
            new_device: New input device type.
            new_code: New key/button code.
            context: Input context to modify.
            resolution: Strategy for handling conflicts.

        Returns:
            Tuple of (result, conflict_info). Conflict is None on success.

        Raises:
            ValueError: If resolution is ERROR and a conflict exists.
        """
        new_key: BindingKey = (new_device, new_code)
        ctx_name = context.value

        # Check for conflicts
        conflicting_actions = self.get_conflicts(new_device, new_code, context)
        # Remove self from conflict list
        conflicting_actions = [a for a in conflicting_actions if a != action]

        conflict_info: Optional[BindingConflict] = None
        if conflicting_actions:
            conflict_info = BindingConflict(
                key=new_key,
                existing_actions=conflicting_actions,
                context=context,
            )

        result = RebindResult.SUCCESS

        if conflicting_actions:
            if resolution == ConflictResolution.ERROR:
                raise ValueError(
                    f"Binding conflict: key {new_key} is already bound to "
                    f"{conflicting_actions} in context {ctx_name}"
                )
            elif resolution == ConflictResolution.SWAP:
                # Get current bindings for this action
                old_bindings = self.get_bindings_for_action(action, context)

                # Unbind conflicting actions from new key
                self.unbind_key(new_device, new_code, context)

                # Unbind this action from old keys
                self.unbind(action, context)

                # Bind this action to new key
                self.bind(new_device, new_code, action, context)

                # Bind conflicting actions to old keys
                for conf_action in conflicting_actions:
                    for old_key in old_bindings:
                        self.bind(old_key[0], old_key[1], conf_action, context)

                result = RebindResult.SWAPPED
            elif resolution == ConflictResolution.UNBIND:
                # Unbind conflicting actions
                self.unbind_key(new_device, new_code, context)

                # Unbind this action from old keys
                self.unbind(action, context)

                # Bind to new key
                self.bind(new_device, new_code, action, context)

                result = RebindResult.UNBOUND
            elif resolution == ConflictResolution.ALLOW:
                # Unbind this action from old keys
                self.unbind(action, context)

                # Allow multiple actions on same key
                self.bind(new_device, new_code, action, context)

                result = RebindResult.SUCCESS
        else:
            # No conflict, simple rebind
            self.unbind(action, context)
            self.bind(new_device, new_code, action, context)

        logger.debug(
            f"Rebound action '{action}' to {new_key} in context '{ctx_name}': {result}"
        )
        return result, conflict_info

    def export_bindings(self) -> Dict[str, Any]:
        """Export all bindings to a serializable dictionary.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        data: Dict[str, Any] = {
            "version": self.BINDING_FORMAT_VERSION,
            "bindings": {},
        }

        for ctx_name, ctx_bindings in self._bindings.items():
            ctx_data: Dict[str, List[Dict[str, Any]]] = {}

            for (device, code), actions in ctx_bindings.items():
                for action in actions:
                    if action not in ctx_data:
                        ctx_data[action] = []
                    ctx_data[action].append({"device": device.name, "code": code})

            if ctx_data:
                data["bindings"][ctx_name] = ctx_data

        return data

    def import_bindings(self, data: Dict[str, Any]) -> None:
        """Import bindings from a dictionary, replacing current bindings.

        Args:
            data: Dictionary from export_bindings() or equivalent.

        Raises:
            ValueError: If data format is invalid or version unsupported.
        """
        version = data.get("version", 1)
        if version > self.BINDING_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported binding format version: {version} "
                f"(max supported: {self.BINDING_FORMAT_VERSION})"
            )

        bindings_data = data.get("bindings", {})

        # Clear existing bindings
        for ctx in InputContext:
            self._bindings[ctx.value] = {}
            self._action_bindings[ctx.value] = {}

        # Import new bindings
        for ctx_name, ctx_data in bindings_data.items():
            try:
                context = InputContext(ctx_name)
            except ValueError:
                logger.warning(f"Unknown context '{ctx_name}' in imported bindings")
                continue

            for action, binding_list in ctx_data.items():
                for binding in binding_list:
                    try:
                        device = InputDevice[binding["device"]]
                        code = binding["code"]
                        self.bind(device, code, action, context)
                    except (KeyError, TypeError) as e:
                        logger.warning(
                            f"Invalid binding data for action '{action}': {e}"
                        )

        logger.info("Imported key bindings")

    def reset_to_defaults(self) -> None:
        """Reset all bindings to empty state."""
        for ctx in InputContext:
            self._bindings[ctx.value] = {}
            self._action_bindings[ctx.value] = {}

        logger.info("Reset all key bindings")
