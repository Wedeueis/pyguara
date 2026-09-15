# UI kit — Guará & Falcão (game surfaces)

Title screen, in-game HUD, pause menu and options screen, over the parallax Cerrado plate.

## What it is built from
| Screen region | Source |
| --- | --- |
| Title lockup, engine badge | `uploads/pyguara_platformer_spritesheet.jpg` (cropped into `assets/sprites/`) |
| Wood / painted menu plates | same sheet — reproduced as `Button` `variant="wood"` and `"sage"` |
| Keycap prompts (arrows, A, +) | same sheet, `assets/sprites/keycaps.png` |
| Health / stamina meters | `ProgressBar` at engine defaults, `pyguara/ui/components/progress_bar.py` |
| Options controls | `Slider` and `Checkbox`, engine geometry unchanged |
| Menu column stacking | `BoxContainer` VERTICAL / CENTER, `pyguara/ui/layout.py` |

## Interactions
Play → HUD (click the lime fruit to raise the counter) → Pause → Options → Back.
All four screens use the `[data-theme="game"]` scope, which is dark regardless of the editor theme
because the HUD always sits over a bright sky.

## Note
The source repository contains no game-specific menu code — the engine is generic and ships no
game. These screens compose engine primitives with the provided art; the button plates and the
title lockup are the only literal recreations.
