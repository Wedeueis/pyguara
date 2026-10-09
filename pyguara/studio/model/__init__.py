"""The read model: what Studio and an agent see when they look at a scene.

Three layers, sharing one value vocabulary:

- `values` -- encoding component field values to JSON and back, shape-
  compatible with what `SceneSerializer` writes.
- `schema` -- what a component's fields are, their types and whether they
  can be set. Drives the Inspector, the schema browser, and the JSON
  Schema an agent reads.
- `snapshot` -- a scene at one instant, and the diff between two.
- `projectmap` -- the budgeted inventory an agent reads first.
"""

from pyguara.studio.model.projectmap import ProjectMap, build_project_map
from pyguara.studio.model.schema import (
    ComponentSchema,
    FieldSchema,
    describe_component,
    describe_registry,
)
from pyguara.studio.model.snapshot import (
    EntityView,
    FieldChange,
    SceneDiff,
    SceneSnapshot,
    diff_snapshots,
    read_component,
    snapshot_scene,
)
from pyguara.studio.model.values import (
    UNENCODABLE_KEY,
    decode,
    encode,
    is_encodable,
    type_name,
)

__all__ = [
    "UNENCODABLE_KEY",
    "ComponentSchema",
    "EntityView",
    "FieldChange",
    "FieldSchema",
    "ProjectMap",
    "SceneDiff",
    "SceneSnapshot",
    "build_project_map",
    "decode",
    "describe_component",
    "describe_registry",
    "diff_snapshots",
    "encode",
    "is_encodable",
    "read_component",
    "snapshot_scene",
    "type_name",
]
