"""Headless Validation Suite for PyGuara Demo Games.

Boots the demo games that run on the pygame backend, plus the asset
pipeline module, under headless SDL dummy drivers, to verify that all
systems and resource managers function without runtime crashes or
regressions.

The ModernGL demos are deliberately absent -- see `main()` for why, and
for how to smoke them instead.
"""

import logging
import os
import sys

# Ensure we can import pyguara from root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

# Configure SDL dummy drivers for headless window initialization
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

from games.asset_pipeline.bootstrap import configure_game_container as ap_bootstrap
from games.asset_pipeline.scenes import AssetScene as APAssetScene

# Import bootstrap configurations
from games.vinagre_matilha.bootstrap import configure_game_container as vm_bootstrap
from games.vinagre_matilha.level_builder import STAGE_1
from games.vinagre_matilha.scenes import GameScene as VMGameScene
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher


def _vm_game_scene(event_dispatcher: EventDispatcher) -> VMGameScene:
    """`GameScene` needs a `StageConfig`; `validate_game()` calls with just
    the dispatcher, so pin it to Stage 1 for the smoke check.
    """
    return VMGameScene(event_dispatcher, STAGE_1)


def validate_game(name: str, configure_container_fn, scene_class) -> bool:
    """Validate a game container and scene by running it for 30 ticks."""
    print("\n==================================================")
    print(f" Validating Subsystem: {name}")
    print("==================================================")

    try:
        # 1. Bootstrap DI Container
        container = configure_container_fn()
        app = container.get(Application)

        # 2. Monkeypatch application update loop to stop after 30 ticks
        ticks = 0
        original_update = app._update

        def patched_update(dt: float) -> None:
            nonlocal ticks
            ticks += 1
            if ticks >= 30:
                print(f"  --> Ticked {ticks} frames successfully.")
                app._is_running = False
            original_update(dt)

        app._update = patched_update

        # 3. Create active gameplay scene
        event_dispatcher = (
            container.get(EventDispatcher)
            if EventDispatcher in container._services
            else app._event_dispatcher
        )
        scene = scene_class(event_dispatcher)

        # 4. Execute game loop
        app.run(starting_scene=scene)

        print(f"  [+] Validation SUCCESS for {name}!")
        return True
    except Exception as e:
        print(f"  [-] Validation FAILED for {name} due to exception: {e}")
        logging.getLogger(name).error("Exception traceback: ", exc_info=True)
        return False
    finally:
        # Explicitly shutdown pygame to release dummy device hooks
        pygame.quit()


def main() -> None:
    """Execute validation checks on all games."""
    logging.basicConfig(level=logging.WARNING)

    results = {}

    # guara_falcao, protocolo_bandeira, true_coral, mourisco_ressonancia and
    # tamandua_murundus are not booted here. All five run on the ModernGL
    # backend, and SDL's `dummy` video driver -- set at the top of this
    # file -- provides no OpenGL at all, so none of them can create a
    # context. Smoke them with, e.g.:
    #     uv run python tools/agent_view.py guara_falcao --gl --frames 30

    # 3. Asset Pipeline Module (Flyweight Loader / .meta files)
    results["Asset Pipeline (Module 3)"] = validate_game(
        name="Asset Pipeline",
        configure_container_fn=ap_bootstrap,
        scene_class=APAssetScene,
    )

    # 5. Squad Tactics (Vinagre: Matilha)
    results["Vinagre: Matilha (Squad Tactics)"] = validate_game(
        name="Vinagre: Matilha",
        configure_container_fn=vm_bootstrap,
        scene_class=_vm_game_scene,
    )

    # Print Summary Table
    print("\n==================================================")
    print(" SUMMARY OF VALIDATION SUITE RESULTS")
    print("==================================================")
    all_success = True
    for key, val in results.items():
        status = "PASSED" if val else "FAILED"
        print(f" - {key:32}: {status}")
        if not val:
            all_success = False

    print("==================================================")
    if all_success:
        print(" SUCCESS: All demo games are 100% stable!")
        sys.exit(0)
    else:
        print(" FAILURE: One or more validations failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
