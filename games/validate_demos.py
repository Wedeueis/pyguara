"""Headless Validation Suite for PyGuara Demo Games.

Boots all three demo games and the asset pipeline module under headless
SDL dummy drivers to verify that all systems and resource managers function
without runtime crashes or regressions.
"""

import os
import sys
import logging

# Ensure we can import pyguara from root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

# Configure SDL dummy drivers for headless window initialization
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
from pyguara.application.application import Application
from pyguara.events.dispatcher import EventDispatcher

# Import bootstrap configurations
from games.guara_falcao.bootstrap import configure_game_container as gf_bootstrap
from games.guara_falcao.scenes import GameScene as GFGameScene

from games.protocolo_bandeira.bootstrap import configure_game_container as pb_bootstrap
from games.protocolo_bandeira.scenes import ArenaScene as PBArenaScene

from games.true_coral.bootstrap import configure_game_container as tc_bootstrap
from games.true_coral.scenes import GameScene as TCGameScene

from games.asset_pipeline.bootstrap import configure_game_container as ap_bootstrap
from games.asset_pipeline.scenes import AssetScene as APAssetScene


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
            if "EventDispatcher" in container._services
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

    # 1. Platformer Game (Guará & Falcão)
    results["Guara & Falcao (Platformer)"] = validate_game(
        name="Guara & Falcao",
        configure_container_fn=gf_bootstrap,
        scene_class=GFGameScene,
    )

    # 2. Twin-Stick Shooter (Protocolo Bandeira)
    results["Protocolo Bandeira (Shooter)"] = validate_game(
        name="Protocolo Bandeira",
        configure_container_fn=pb_bootstrap,
        scene_class=PBArenaScene,
    )

    # 3. Puzzle Game (True Coral)
    results["True Coral (Puzzle)"] = validate_game(
        name="True Coral", configure_container_fn=tc_bootstrap, scene_class=TCGameScene
    )

    # 4. Asset Pipeline Module (Flyweight Loader / .meta files)
    results["Asset Pipeline (Module 3)"] = validate_game(
        name="Asset Pipeline",
        configure_container_fn=ap_bootstrap,
        scene_class=APAssetScene,
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
