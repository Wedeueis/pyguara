"""Key binding management."""

from typing import Dict, List, Tuple
from pyguara.input.types import InputContext, InputDevice

# Binding Key: (DeviceType, KeyCode/AxisIndex)
BindingKey = Tuple[InputDevice, int]


class KeyBindingManager:
    """Maps physical inputs (Device + Code) to Actions."""

    def __init__(self) -> None:
        """Initialize the binding manager with default contexts."""
        # Map: Context -> BindingKey -> List[ActionName]
        self._bindings: Dict[str, Dict[BindingKey, List[str]]] = {}
        for ctx in InputContext:
            self._bindings[ctx.value] = {}

    def bind(
        self,
        device: InputDevice,
        code: int,
        action: str,
        context: InputContext = InputContext.GAMEPLAY,
    ) -> None:
        """Bind a physical input to an action."""
        ctx_map = self._bindings.setdefault(context.value, {})
        key = (device, code)

        if key not in ctx_map:
            ctx_map[key] = []

        if action not in ctx_map[key]:
            ctx_map[key].append(action)

    def get_actions(
        self, device: InputDevice, code: int, context: InputContext
    ) -> List[str]:
        """Lookup actions for a specific device input."""
        key = (device, code)
        return self._bindings.get(context.value, {}).get(key, [])
