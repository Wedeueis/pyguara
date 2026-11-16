"""The edit command for one configuration setting.

A setting is not part of a world, so this command ignores the world it
is handed and writes through the `ConfigManager` it was built with. It
sits on the same `CommandStack` as the scene edits, which is what makes
a config change undoable, journaled and subject to the approval mode.
"""

from __future__ import annotations

import copy
from typing import Any

from pyguara.config.manager import ConfigManager
from pyguara.ecs.manager import EntityManager
from pyguara.studio.commands.base import EditCommand, EditError
from pyguara.studio.model.values import encode


class SetConfigSetting(EditCommand):
    """Write one setting of one config section.

    The write goes through `ConfigManager.update_setting()`, so it is
    type-checked, validated and announced with `OnConfigurationChanged`
    exactly as a game's own options menu would be. Reverting announces
    it again, which also happens to an edit that is only planned.
    """

    def __init__(
        self, manager: ConfigManager, section: str, setting: str, value: Any
    ) -> None:
        """Describe the write.

        Args:
            manager: The configuration to write to.
            section: The section's name, e.g. `"physics"`.
            setting: The field within it.
            value: The new value, already decoded to the field's type.
        """
        super().__init__()
        self._manager = manager
        self._section = section
        self._setting = setting
        self._value = value
        self._previous: Any = None

    @property
    def label(self) -> str:
        """What the history shows."""
        return f"Set config {self._section}.{self._setting}"

    @property
    def target(self) -> tuple[str, str]:
        """What this command writes to, for coalescing comparisons."""
        return (self._section, self._setting)

    def _apply(self, world: EntityManager) -> None:
        """Write the setting, keeping the value it replaces.

        Args:
            world: Unused; a setting belongs to no world.

        Raises:
            EditError: If the manager refuses the value, with its reason.
        """
        reason = self._manager.check_setting(self._section, self._setting, self._value)
        if reason is not None:
            raise EditError(reason)

        section = self._manager.config.get_section(self._section)
        # Copied: a `Color` is mutable, and one shared with the live
        # section would follow a later in-place change.
        self._previous = copy.deepcopy(getattr(section, self._setting))
        self._write(self._value)

    def _revert(self, world: EntityManager) -> None:
        """Put the previous value back.

        Args:
            world: Unused.

        Raises:
            EditError: If the manager now refuses the old value, which
                happens when a profile took the setting over in between.
        """
        self._write(self._previous)

    def _write(self, value: Any) -> None:
        """Send one value through the manager.

        Args:
            value: The value to write.

        Raises:
            EditError: If it is refused.
        """
        if self._manager.update_setting(self._section, self._setting, value):
            return
        reason = self._manager.check_setting(self._section, self._setting, value)
        raise EditError(
            reason
            or f"'{self._section}.{self._setting}' could not be set to {value!r}."
        )

    def coalesce_with(self, previous: EditCommand) -> EditCommand | None:
        """Fold into `previous` when both write the same setting.

        The merged command keeps `previous`'s captured old value and this
        command's new one, so a dragged slider undoes to where the drag
        began.

        Args:
            previous: The command on top of the stack.

        Returns:
            A command spanning both writes, or None when they are unrelated.
        """
        if not isinstance(previous, SetConfigSetting):
            return None
        if previous.target != self.target or previous._manager is not self._manager:
            return None

        merged = SetConfigSetting(
            self._manager, self._section, self._setting, self._value
        )
        merged._previous = previous._previous
        merged._applied = True
        return merged

    def describe(self) -> dict[str, Any]:
        """Describe the write, old value included.

        Returns:
            A JSON-serializable description.
        """
        description = super().describe()
        description.update(
            {
                "section": self._section,
                "setting": self._setting,
                "from": encode(self._previous),
                "to": encode(self._value),
            }
        )
        return description
