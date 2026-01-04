import sys
import pygame
import math

# --- Imports from our new Architecture ---
from pyguara.common.types import Vector2, Color
from pyguara.common.palette import BasicColors
from pyguara.graphics.window import Window, WindowConfig
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.components.geometry import Box, Circle
from pyguara.graphics.components.particles import ParticleSystem
from pyguara.graphics.types import Layer
from pyguara.resources.manager import ResourceManager
from pyguara.graphics.backends.pygame.loaders import PygameImageLoader
from pyguara.resources.types import Texture


# --- Helper: Generate Dummy Assets ---
def create_dummy_texture(manager: ResourceManager, name: str, color: Color) -> Texture:
    # Make it 64x64 so it's huge
    surf = pygame.Surface((32, 32), flags=pygame.SRCALPHA)
    surf.fill(color)

    from pyguara.graphics.backends.pygame.types import PygameTexture

    tex = PygameTexture(name, surf)
    manager._cache[name] = tex
    return tex


def main() -> None:
    pygame.init()

    # 1. Setup Infrastructure
    print("[1/5] Initializing Window & Renderer...")
    pygame_window = PygameWindow()
    win_config = WindowConfig(
        title="pyGuara Render Pipeline Test", width=1280, height=720
    )
    window = Window(win_config, pygame_window)
    window.create()

    backend = PygameBackend(window.native_handle)
    renderer_system = RenderSystem(backend)

    # 2. Setup Resources
    print("[2/5] Setting up Resources...")
    resources = ResourceManager()
    resources.register_loader(PygameImageLoader())

    # Create dummy textures for Sprites & Particles
    player_tex = create_dummy_texture(resources, "player", BasicColors.BLUE)
    particle_tex = create_dummy_texture(resources, "smoke", Color(200, 200, 100, 128))
    font = pygame.font.SysFont("Arial", 18)

    # 3. Create Scene Objects
    print("[3/5] Instantiating Entities...")

    # A. Regular Sprite (The Player)
    player = Sprite(texture=player_tex, layer=Layer.ENTITIES, z_index=Layer.ENTITIES)
    player_pos = Vector2(0, 0)  # World Origin

    # B. Geometry (Placeholder World)
    # Ground: A generic Green box
    ground = Box(width=800, height=50, color=BasicColors.GREEN, layer=Layer.WORLD)
    ground.position = Vector2(-400, 100)  # Below player

    # Coin: A generic Yellow circle
    coin = Circle(
        radius=10,
        color=BasicColors.YELLOW,
        layer=Layer.ENTITIES,
        z_index=Layer.ENTITIES,
    )
    coin.position = Vector2(0, 0)

    # C. Particle System
    particles = ParticleSystem(capacity=2000)

    # 4. Setup Camera
    camera = Camera2D(width=1280, height=720)
    camera.zoom = 1.0

    # 5. Game Loop
    print("[4/5] Starting Game Loop...")
    clock = pygame.time.Clock()
    running = True
    time = 0.0

    while running:
        dt = clock.tick(60) / 1000.0
        time += dt

        # --- Event Handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                # Test Zoom
                if event.key == pygame.K_z:
                    camera.zoom = 2.0 if camera.zoom == 1.0 else 1.0

        # --- Update Logic ---

        # 1. Move Player (Orbit around center)
        new_x = math.sin(time) * 100
        new_y = math.cos(time) * 100
        player_pos = Vector2(new_x, new_y)

        # 2. Camera Follow (Smooth Lerp)
        camera.position = camera.position.lerp(player_pos, 5.0 * dt)

        # 3. Particle Emission (Trail behind player)
        particles.emit(
            texture=particle_tex,
            position=player_pos,  # Emit from player
            count=5,
            speed=50.0,
            spread=360.0,
            life=0.8,
        )
        particles.update(dt)

        # Update Sprite Positions manually (ECS would do this automatically)
        # Note: We create a generic object with .position attr if needed,
        # but here we just modify the renderer submission values or wrap logic.
        # For this test, we construct the submission in the render phase.

        # --- Render Phase ---

        # A. Setup Viewport (Cinematic 21:9 Aspect Ratio test)
        # This will automatically create black bars (Letterboxing)
        viewport = Viewport.create_best_fit(window.width, window.height, 21 / 9)

        # B. Clear Window (Background for letterbox bars)
        backend.clear(BasicColors.BLACK)  # Bars will be black

        # C. Submit "Standard" Objects to Pipeline
        # Note: In a real ECS, you'd iterate `for entity in entities: renderer.submit(entity)`

        # Hack to update player sprite position for submission since Sprite is just data
        # In ECS, 'player' would be an Entity with PositionComponent + SpriteComponent
        # Here we manually simulate that coupling for the test.
        class RenderProxy:
            def __init__(self, spr: Sprite, pos: Vector2) -> None:
                self.texture = spr.texture
                self.layer = spr.layer
                self.z_index = spr.z_index
                self.position = pos
                self.rotation = 0.0
                self.scale = Vector2(1, 1)

        renderer_system.submit(RenderProxy(player, player_pos))
        renderer_system.submit(ground)  # Box implements Renderable directly
        renderer_system.submit(coin)  # Circle implements Renderable directly
        fps_text = f"FPS: {clock.get_fps():.0f}"
        text_surf = font.render(fps_text, True, BasicColors.WHITE)

        # D. Flush Main Pipeline (Sorts & Batches Sprites + Geometry)
        # We pass the specific Viewport here. The renderer will clip to it.
        # Inside the viewport, we clear with a Sky Color (Dark Blue)
        backend.set_viewport(viewport)
        backend.clear(Color(120, 120, 240))

        renderer_system.flush(camera, viewport)

        backend._screen.blit(text_surf, (10, 10))

        # --- DEBUG: Print Particle Count ---
        # Only print every 60 frames to avoid spamming console
        if int(time * 60) % 60 == 0:
            active_count = sum(1 for p in particles._pool if p.active)
            print(f"Active Particles: {active_count}")

        # E. Render Particles (The real system)
        particles.render(backend, camera, viewport)

        # F. Debug UI (Draw Viewport Border)
        # Draw a white line around the active viewport to visualize aspect ratio
        backend.draw_rect(viewport, BasicColors.WHITE, width=5)

        # G. Present
        renderer_system._backend.present()  # Access backend directly or expose present() in System

        # Title Debug Stats
        pygame.display.set_caption(
            f"FPS: {clock.get_fps():.2f} | Particles: {sum(1 for p in particles._pool if p.active)}"
        )

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
