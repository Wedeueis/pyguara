"""The demos the capture tools and tests can boot, by name.

Its own module, with no imports, so a check that runs a demo with pygame
made unimportable (`tests/integration/_without_pygame.py`) can read it
without `agent_view` loading pygame first.
"""

from __future__ import annotations

# name -> (bootstrap module, scene module, scene class). Explicit rather than
# derived, so a broken demo names itself instead of failing during discovery.
DEMOS: dict[str, tuple[str, str, str]] = {
    "asset_pipeline": (
        "games.asset_pipeline.bootstrap",
        "games.asset_pipeline.scenes",
        "AssetScene",
    ),
    "boot_process": (
        "games.boot_process.bootstrap",
        "games.boot_process.scenes",
        "BootScene",
    ),
    "ecs_mental_model": (
        "games.ecs_mental_model.bootstrap",
        "games.ecs_mental_model.scenes",
        "ECSScene",
    ),
    "net_horde": (
        "games.net_horde.bootstrap",
        "games.net_horde.scenes",
        "SideBySideScene",
    ),
    "guara_falcao": (
        "games.guara_falcao.bootstrap",
        "games.guara_falcao.scenes",
        "TitleScene",
    ),
    "input_events": (
        "games.input_events.bootstrap",
        "games.input_events.scenes",
        "InputScene",
    ),
    "physics_integration": (
        "games.physics_integration.bootstrap",
        "games.physics_integration.scenes",
        "PhysicsScene",
    ),
    "protocolo_bandeira": (
        "games.protocolo_bandeira.bootstrap",
        "games.protocolo_bandeira.scenes",
        "MenuScene",
    ),
    "quintal_cerrado": (
        "games.quintal_cerrado.bootstrap",
        "games.quintal_cerrado.scenes",
        "TitleScene",
    ),
    "tilemap_authoring": (
        "games.tilemap_authoring.bootstrap",
        "games.tilemap_authoring.scenes",
        "TilemapScene",
    ),
    "tamandua_murundus": (
        "games.tamandua_murundus.bootstrap",
        "games.tamandua_murundus.scenes",
        "ClearingScene",
    ),
    "true_coral": (
        "games.true_coral.bootstrap",
        "games.true_coral.scenes",
        "MenuScene",
    ),
    "ui_scene_graph": (
        "games.ui_scene_graph.bootstrap",
        "games.ui_scene_graph.scenes",
        "MenuScene",
    ),
    "mourisco_ressonancia": (
        "games.mourisco_ressonancia.bootstrap",
        "games.mourisco_ressonancia.scenes",
        "CaveScene",
    ),
    "vinagre_matilha": (
        "games.vinagre_matilha.bootstrap",
        "games.vinagre_matilha.scenes",
        "MenuScene",
    ),
}
