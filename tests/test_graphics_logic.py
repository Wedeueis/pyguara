from pyguara.graphics.components.animation import Animator, AnimationClip
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.components.particles import ParticleSystem
from pyguara.common.types import Vector2


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
    animator.add_clip(clip)

    # Act: Play
    animator.play("run")
    assert sprite.texture == tex1

    # Act: Update (0.5s - No change yet)
    animator.update(0.5)
    assert sprite.texture == tex1

    # Act: Update (0.6s -> Total 1.1s -> Next frame)
    animator.update(0.6)
    assert sprite.texture == tex2

    # Act: Loop (Total 2.2s -> Back to frame 1)
    animator.update(1.1)
    assert sprite.texture == tex1


def test_particle_system_emission():
    """
    Unit Test: Particle Emission & Lifecycle
    Verifies that particles are spawned, moved, and recycled.
    """
    ps = ParticleSystem(capacity=10)
    tex = MockTexture("smoke")

    # 1. Emit
    ps.emit(tex, Vector2(0, 0), count=5, speed=100, life=1.0)

    active = [p for p in ps._pool if p.active]
    assert len(active) == 5
    assert active[0].texture == tex
    assert active[0].life == 1.0
    # Velocity should be non-zero
    assert active[0].velocity.length > 0

    # 2. Update (Move)
    ps.update(0.5)
    # Positions should have changed from 0,0
    assert active[0].position != Vector2(0, 0)
    assert active[0].life == 0.5

    # 3. Kill (Life expires)
    ps.update(0.6)  # Total 1.1s
    active_now = [p for p in ps._pool if p.active]
    assert len(active_now) == 0
