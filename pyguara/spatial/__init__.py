"""Non-physics spatial queries for PyGuara.

`SpatialHash`, the underlying value type, lives in `pyguara.common.spatial`
and knows nothing of the ECS. `SpatialTracked` and `SpatialIndexSystem` here
wire it to entities: attach `SpatialTracked` to anything a spatial query
needs to find that has no physics body, and run `SpatialIndexSystem` each
tick to keep the hash current.

The physics-backed equivalent -- `point_query`, `region_query`,
`overlap_circle`, etc. on `IPhysicsEngine` -- already covers entities that
do have a pymunk shape; this module exists for the ones that don't.
"""

from pyguara.common.spatial import SpatialHash
from pyguara.spatial.components import SpatialTracked
from pyguara.spatial.system import SpatialIndexSystem

__all__ = ["SpatialHash", "SpatialIndexSystem", "SpatialTracked"]
