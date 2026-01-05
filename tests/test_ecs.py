from pyguara.ecs import EntityManager
from pyguara.common.components import Transform, Vector2
from pyguara.physics.components.rigid_body import RigidBody
from pyguara.physics.components.collider import Collider
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.events.dispatcher import EventDispatcher

# 1. Setup World
manager = EntityManager()

# 2. Create Entity
player = manager.create_entity("player")
player.add_component(Transform(position=Vector2(100, 100)))
player.add_component(RigidBody(mass=10))
player.add_component(Collider())

# 3. System Query
# The PhysicsSystem logic we wrote previously:
# def update(self, entities: List[Any], dt: float)

event_dispatcher = EventDispatcher()
physics_backend = PymunkEngine()
physics_system = PhysicsSystem(physics_backend, event_dispatcher)
relevant_entities = list(manager.get_entities_with(Transform, RigidBody))
physics_system.update(relevant_entities, dt=0.016)

# 4. Access
# Thanks to __getattr__ magic in Entity:
print(player.transform.position)
print(player.rigid_body.velocity)
