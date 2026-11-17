from pyguara.common.types import Vector2
from pyguara.graphics.components.animation import (
    AnimationClip,
    Animator,
    add_clip,
    advance_animator,
    play_clip,
)
from pyguara.graphics.components.particles import ParticleSystem
from pyguara.graphics.components.sprite import Sprite


# --- Mocks ---
class MockTexture:
    def __init__(self, name):
        self.name = name


def test_animator_playback():
    """
    Unit Test: Animator State Machine
    Verifies that the animator updates the sprite's texture over time based on frame rate.
    """
    # Setup
    tex1 = MockTexture("f1")
    tex2 = MockTexture("f2")
    sprite = Sprite(texture=tex1)
    animator = Animator(sprite)

    clip = AnimationClip(name="run", frames=[tex1, tex2], frame_rate=1.0, loop=True)
    add_clip(animator, clip)

    # Act: Play
    play_clip(animator, "run")
    assert sprite.texture == tex1

    # Act: Update (0.5s - No change yet)
    advance_animator(animator, 0.5)
    assert sprite.texture == tex1

    # Act: Update (0.6s -> Total 1.1s -> Next frame)
    advance_animator(animator, 0.6)
    assert sprite.texture == tex2

    # Act: Loop (Total 2.2s -> Back to frame 1)
    advance_animator(animator, 1.1)
    assert sprite.texture == tex1


def test_particle_system_emission():
    """Particles are spawned, moved and recycled."""
    ps = ParticleSystem(capacity=10)
    tex = MockTexture("smoke")

    # 1. Emit
    ps.emit(tex, Vector2(0, 0), count=5, speed=100, life=1.0)

    assert ps.live_count == 5

    # 2. Update (Move)
    ps.update(0.5)
    assert ps.live_count == 5

    # 3. Kill (Life expires)
    ps.update(0.6)  # Total 1.1s
    assert ps.live_count == 0


def test_particle_state_is_readable_slot_by_slot():
    """The pool has no particle objects; a slot's columns are the state."""
    ps = ParticleSystem(capacity=10)

    ps.emit(MockTexture("smoke"), Vector2(0, 0), count=5, speed=100, life=1.0)

    slots = [ps._native.slot(index) for index in range(10)]
    active = [slot for slot in slots if slot[6]]
    assert len(active) == 5
    _x, _y, velocity_x, velocity_y, life, _rotation, _active = active[0]
    assert life == 1.0
    assert (velocity_x, velocity_y) != (0.0, 0.0)

    ps.update(0.5)
    assert ps._native.slot(slots.index(active[0]))[:2] != (0.0, 0.0)
    assert ps._native.slot(slots.index(active[0]))[4] == 0.5
