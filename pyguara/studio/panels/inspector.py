"""The Inspector, routed through Studio's operations.

The base editor's panel does the reflection -- reading a component's
fields, picking a widget per type, deciding what is frozen -- and writes
the accepted value straight onto the component. That is right for an
editor with no session behind it and wrong for Studio, where it opened a
second way to change the world: a field typed here did not reach the
history, did not appear in the journal, and applied even in `plan` mode,
which is supposed to change nothing.

So this subclasses the panel rather than reimplementing it, and overrides
the one method that writes. The same `set_field` an agent calls over MCP
is what a person typing in the Inspector now calls too, which is the whole
premise: one seam, one history, one record.

A refused or failed edit is reported rather than swallowed. The panel that
accepts a value, reports nothing and changes nothing is what "the controls
do not seem to have any effect" looks like from the outside.
"""

from __future__ import annotations

from typing import Any

from pyguara.ecs.component import Component
from pyguara.ecs.manager import EntityManager
from pyguara.editor.panels.inspector import InspectorPanel
from pyguara.log import get_logger
from pyguara.studio.agent.journal import Actor
from pyguara.studio.model.values import encode

logger = get_logger(__name__)


class StudioInspectorPanel(InspectorPanel):
    """An Inspector whose edits are operations."""

    def __init__(self, attachment: Any, *, visible: bool = True) -> None:
        """Initialize the panel.

        Args:
            attachment: The `StudioAttachment` to apply edits through.
                Held rather than unpacked because the session is replaced
                on a scene switch, and a held one would edit a world that
                is no longer on screen.
            visible: Whether it draws from the first frame.
        """
        super().__init__(visible=visible)
        self._attachment = attachment

    def write(
        self,
        manager: EntityManager,
        entity_id: str,
        component: Component,
        field_name: str,
        value: Any,
    ) -> None:
        """Apply the edit as a `set_field` operation.

        Args:
            manager: The world the component belongs to. Unused: the
                operation reaches it through the session, which is the
                point -- a panel that wrote through the manager it was
                handed would be the second seam this exists to close.
            entity_id: The owning entity.
            component: The component being edited.
            field_name: The field that changed.
            value: Its new value.
        """
        session = self._attachment.session
        if session is None:
            logger.debug("No Studio session yet; the edit was dropped.")
            return

        result = self._attachment.operations.invoke(
            session,
            "set_field",
            {
                "entity_id": entity_id,
                "component": type(component).__name__,
                "field": field_name,
                # Through the same encoder the operation surface uses, so a
                # `Vector2` or a `Color` crosses as the object shape an
                # agent would send rather than as a Python instance the
                # schema does not describe.
                "value": encode(value),
            },
            actor=Actor.HUMAN,
        )
        if not result.ok:
            self.report(
                f"{entity_id}.{type(component).__name__}.{field_name}: {result.error}"
            )
