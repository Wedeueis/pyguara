"""Main Script Orchestrate application setup and execution."""

import os

import pygame

from pyguara.resources.manager import ResourceManager
from pyguara.resources.types import Texture

# Imports da infraestrutura (feitos apenas na configuração inicial)
from pyguara.graphics.backends.pygame.loaders import PygameImageLoader


def main() -> None:
    """Orchestrates application execution."""
    print("--- 1. Initializing Low-Level Dependencies ---")
    pygame.init()

    # CRITICAL: Initialize a hidden 1x1 window.
    # This satisfies the requirement for .convert() and .convert_alpha()
    pygame.display.set_mode((1, 1), flags=pygame.HIDDEN)
    print("[Test] Pygame Display Initialized.")

    try:
        print("\n--- 2. Setting up pyGuara Resource System ---")
        # Instantiate the Manager
        resources = ResourceManager()

        # Register the loader (The Strategy Pattern)
        # This will populate the dictionary: {'.png': PygameImageLoader, ...}
        loader = PygameImageLoader()
        resources.register_loader(loader)
        print(f"[Test] Registered loader for: {loader.supported_extensions}")

        print("\n--- 3. Running the Load Test ---")
        asset_name = "assets/textures/sentinel.jpg"

        # A. Happy Path: Loading a Texture
        print(f"[Test] Attempting to load {asset_name} as Texture...")
        hero_sprite = resources.load(asset_name, Texture)  # type: ignore[type-abstract]

        print(f"    SUCCESS! Object Type: {type(hero_sprite)}")
        print(f"    Width: {hero_sprite.width}")
        print(f"    Height: {hero_sprite.height}")
        print(f"    Native Handle: {hero_sprite.native_handle}")

        # B. Error Handling: Requesting wrong type
        print("\n[Test] Attempting to load .jpg as AudioClip (Expected Failure)...")
        try:
            # Assuming you have an AudioClip type imported, or just use int to fail
            resources.load(asset_name, int)  # type: ignore[type-var]
        except TypeError as e:
            print(f"    SUCCESS! Caught expected error: {e}")

        # C. Cache Test
        print("\n[Test] Checking Cache...")
        hero_sprite_2 = resources.load(asset_name, Texture)  # type: ignore[type-abstract]
        if hero_sprite is hero_sprite_2:
            print(
                "    SUCCESS! Manager returned the exact same instance (Flyweight pattern)."
            )
        else:
            print("    FAILURE! Manager created a duplicate object.")

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Cleanup
        if os.path.exists("test_sprite.png"):
            os.remove("test_sprite.png")
            print("\n[Test] Cleaned up dummy file.")

        pygame.quit()
        print("[Test] Pygame quit. Done.")


if __name__ == "__main__":
    main()
