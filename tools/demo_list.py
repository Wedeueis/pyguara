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
        "examples.asset_pipeline.bootstrap",
        "examples.asset_pipeline.scenes",
        "AssetScene",
    ),
    "boot_process": (
        "examples.boot_process.bootstrap",
        "examples.boot_process.scenes",
        "BootScene",
    ),
    "ecs_mental_model": (
        "examples.ecs_mental_model.bootstrap",
        "examples.ecs_mental_model.scenes",
        "ECSScene",
    ),
    "net_horde": (
        "examples.net_horde.bootstrap",
        "examples.net_horde.scenes",
        "SideBySideScene",
    ),
    "guara_falcao": (
        "examples.guara_falcao.bootstrap",
        "examples.guara_falcao.scenes",
        "TitleScene",
    ),
    "input_events": (
        "examples.input_events.bootstrap",
        "examples.input_events.scenes",
        "InputScene",
    ),
    "physics_integration": (
        "examples.physics_integration.bootstrap",
        "examples.physics_integration.scenes",
        "PhysicsScene",
    ),
    "protocolo_bandeira": (
        "examples.protocolo_bandeira.bootstrap",
        "examples.protocolo_bandeira.scenes",
        "MenuScene",
    ),
    "quintal_cerrado": (
        "examples.quintal_cerrado.bootstrap",
        "examples.quintal_cerrado.scenes",
        "TitleScene",
    ),
    "tilemap_authoring": (
        "examples.tilemap_authoring.bootstrap",
        "examples.tilemap_authoring.scenes",
        "TilemapScene",
    ),
    "tamandua_murundus": (
        "examples.tamandua_murundus.bootstrap",
        "examples.tamandua_murundus.scenes",
        "ClearingScene",
    ),
    "true_coral": (
        "examples.true_coral.bootstrap",
        "examples.true_coral.scenes",
        "MenuScene",
    ),
    "ui_scene_graph": (
        "examples.ui_scene_graph.bootstrap",
        "examples.ui_scene_graph.scenes",
        "MenuScene",
    ),
    "mourisco_ressonancia": (
        "examples.mourisco_ressonancia.bootstrap",
        "examples.mourisco_ressonancia.scenes",
        "CaveScene",
    ),
    "vinagre_matilha": (
        "examples.vinagre_matilha.bootstrap",
        "examples.vinagre_matilha.scenes",
        "MenuScene",
    ),
}
