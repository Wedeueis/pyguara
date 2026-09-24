## **Project Name:** _Quintal do Cerrado_ (Working Title)

**Module Path:** `games/quintal_cerrado/`
**Target Duration:** a twelve-day playable capstone demo, played turn by turn
**Engine:** PyGuara 2D (`pyguara`)
**Theme:** Agroforestry, Syntropic Agriculture, Cozy Incremental Gardening
## 1. Executive Summary & Vision

_Quintal do Cerrado_ is a cozy, incremental gardening game set in the Brazilian Cerrado. Inspired by _Stardew Valley_ and syntropic agroforestry, players restore a grid-based plot of dirt by planting native flora, balancing natural ecosystem dynamics (sunlight, shade, soil nutrients, moisture, and pest pressure), or opting for short-term chemical shortcuts.
### Primary Showcase Goals for PyGuara

1. **Tilemap & Grid System (`pyguara.tilemap` & `pyguara.physics.tilemap`):** Multi-layer grid interaction, dirt tilling, dynamic tile transitions, and spatial query checks per cell.
2. **Persistence & Migration (`pyguara.persistence`):** Autosaving garden state, player inventory, unlocked tech, and cross-session state restoration.
3. **PyGuara Design System (`pyguara.ui.design_system`):** Clean integration of the **Cerrado Dusk / Day** UI tokens (`DSPanel`, `DSButton`, `DSProgressBar`, `DSSlider`) for HUD, store, and plant inspection overlays.
## 2. Core Gameplay Mechanics & Ecosystem Loop

### A. The Agroforestry Grid (Tilemap)

- **Grid Layout:** $12 \times 8$ playable dirt tiles (`TilemapLayer`).
- **Tile Properties:** Each cell tracks `moisture`, `nitrogen`, `organic_matter`, `shade_level`, and `pest_pressure`.
- **Layer Composition:**
    - `Layer 0 (Terrain)`: Base soil, tilled soil, paths, and water pipes.
    - `Layer 1 (Flora)`: Plant sprites, growth stages, and shade/canopy overlays.
    - `Layer 2 (Automation)`: Drip irrigation, solar panels, and automated sensors.
### B. Plant Stratification & Syntropic Consortium

Plants are grouped into canopy layers. Planting complementary species in adjacent cells provides mutual benefits:
### C. The Agroecological Dilemma: Natural vs. Chemical

Players choose between two strategies (or a hybrid approach):

```
                   ┌─────────────────────────────────────────┐
                   │               START PLOT                │
                   └────────────────────┬────────────────────┘
                                        │
           ┌────────────────────────────┴────────────────────────────┐
           ▼                                                         ▼
┌─────────────────────────────┐                           ┌─────────────────────────────┐
│    Chemical Shortcut Path   │                           │  Natural Consortium Path    │
├─────────────────────────────┤                           ├─────────────────────────────┤
│ • High upfront cost         │                           │ • Slower initial growth     │
│ • Fast yield boost          │                           │ • Self-sustaining soil      │
│ • Depletes soil organic BOM │                           │ • High-value organic yield  │
│ • Degrades neighboring tiles│                           │ • Pest resistance via flora │
│ • Sells at 0.5x Market Price│                           │ • Sells at 2.0x Premium     │
└─────────────────────────────┘                           └─────────────────────────────┘
```

## 3. Technology & Automation Tree (Incremental Systems)

Earned credits (_Sementes_) can be reinvested into tech structures to automate chores:

1. **Solar Micro-Panel:** Generates passive credits and powers irrigation pumps without burning fuel.
2. **Drip Irrigation System:** Automatically maintains tile moisture at optimal levels ($>60\%$) across connected cells.
3. **Syntropic Soil Sensor:** Renders real-time HUD overlays showing tile nutrients, shade percentages, and moisture heatmaps.
4. **Auto-Harvester Drone:** Harvests mature crops within a $3 \times 3$ radius and deposits them directly into the auto-sell bin.
## 4. UI / UX Design System Integration

The UI uses the established **Cerrado Design System** (`pyguara.ui.design_system`):
- **Color Palette:** Warm earth tones (`--sand-100` to `--rock-600`), **Guará Pelt Orange** (`#e2621f`) for primary actions, and **Colonial Green / Sage** (`--colonial-500`) for garden status cards.
- **HUD Layout:**
    - **Top-Left (`DSPanel`):** Day/Night cycle clock, solar power reserves, and current credits.
    - **Top-Right (`DSPanel`):** Active tool selector (Seed Bag, Water Can, Pruner, Chemical Sprayer, Sensor).
    - **Bottom-Center (`DSPanel`):** Contextual Cell Inspector (displays selected tile's Nitrogen, Moisture, Shade, and Plant Stage).
    - **Floating Store Overlay (`DSPanel` with `bevel=True`):** Buy seeds, equipment, or chemical/organic inputs.
## 5. Technical Architecture & Persistence Specification

### A. Directory Structure

Plaintext

```
games/quintal_cerrado/
├── __init__.py
├── bootstrap.py            # Composition root & DI container setup
├── main.py                 # Game entry point
├── components.py           # Tile, Plant, Automation & Soil Components
├── events.py               # Garden & Save/Load Event Definitions
├── scenes.py               # GardenScene & StoreOverlayScene
├── systems/
│   ├── plant_growth_system.py # Nutrient, shade & moisture simulation
│   ├── syntropic_system.py    # Companion planting & pest calculation
│   ├── automation_system.py   # Drip irrigation & solar power ticks
│   └── garden_render_system.py# Tilemap & overlay renderer
└── assets/
    └── textures/           # Plant sprites, soil tiles, automation structures
```

### B. Persistence & Serialization Specification (`pyguara.persistence`)

To validate engine save/load capabilities, the game state must save automatically at the end of every day (when the player sleeps) or on manual exit. Between two mornings nothing changes that a save could miss, so there is no periodic autosave:

Python

```
# State schema stored via pyguara.persistence.manager
SAVE_SCHEMA = {
    "version": "1.0.0",
    "player": {
        "credits": 150.0,
        "solar_power": 45.0,
        "unlocked_tech": ["drip_irrigation_v1", "soil_sensor"]
    },
    "grid_state": [
        {
            "x": 0,
            "y": 0,
            "soil_type": "tilled",
            "moisture": 0.75,
            "nitrogen": 0.80,
            "organic_matter": 0.90,
            "plant": {
                "species_id": "baru_tree",
                "growth_stage": 3,
                "health": 1.0,
                "is_chemical_boosted": False
            },
            "automation": "drip_nozzle"
        }
        # ... 96 tiles total
    ]
}
```

## 6. Twelve-Day Playable Loop (Demo Script)

The garden is **turn-based**. A day is the turn, and nothing in the
simulation moves while the player is in one: plants grow, soil dries, pests
spread and the sky turns only when they sleep. **Stamina** is what makes a
day finite — twelve points, spent per action (till 2, plant 1, water 1,
compost 2, spray 3, harvest 1); choosing a tool, reading the inspector and
shopping are free. Sleeping restores the pool, advances the day, resolves
the night and opens a **morning report** of what happened while the player
slept.

The twelve days are also a **calendar**. The Cerrado has two seasons, not
four, so a run is three four-day spells — **seca, águas, seca** — and the
season is two levers and no more:

- **the sky**: each season re-weights the same six weather conditions. It
  does not rain in the *seca* at all, and the cold fronts (*friagem*)
  belong to it alone; the *águas* rain three times as often and never
  bring a front. Every forecast entry is rolled for the day it will land
  on, so the two-day forecast shows the rains arriving before they do.
- **the market**: a crop harvested in its own season sells 25% above the
  market rate. Baru and Cagaita belong to the dry months, Pequi and
  Guandu to the rains — roughly when each actually fruits — so what goes
  in the ground is planned around what is coming, not around what is
  cheapest today. It is a premium, not a lockout: an out-of-season crop
  is still worth growing.

Growth rates are untouched by the season: the weather already moves those,
and a second multiplier saying the same thing would be one system too many.

- **Days 1–2 (Onboarding):** A barren $12 \times 8$ dirt plot and a few
  legume seeds (_Guandu_). The player learns tilling, planting and
  watering, and finds that a day runs out.
- **Days 2–4 (Stratification):** _Baru_ and _Cagaita_ unlock. Planting
  _Cagaita_ under the shade of _Baru_ with _Guandu_ at the base boosts
  growth speed by $40\%$ — which now reads as "a stage a night sooner".
  These are the driest days of the run: nothing falls from the sky, and
  the watering can is the whole answer.
- **Day 3 onward (The Fork in the Road):** A pest infestation arrives once
  the plot has enough established plants. The player chooses:
    - _Option A:_ chemical spray (clears it at once and grows the crop
      faster, but the soil turns dusty red and the crop sells at 0.5x).
    - _Option B:_ plant _Pequi_ and add organic compost (slower recovery,
      keeps the 2.0x organic premium).

- **Day 5 (The rains):** the *águas* arrive. The plot waters itself, the
  cold fronts stop, and the pests like the wet as much as the plants do.
  _Pequi_ and _Guandu_ are worth a quarter more while it lasts.

- **Days 4–10 (Automation Expansion):** Revenue allows the Solar Panel and
  Drip Irrigation. Each night the panel pays, the drip keeps its cells off
  the dry line, and the drone collects a couple of ready plants — the
  garden does part of the work while the player sleeps, which is what buys
  back stamina for everything else.

- **Day 9 (The dry harvest):** the *seca* returns for the last four days,
  and with it the premium on _Baru_ and _Cagaita_ — the crops a player
  who read the calendar on day 1 put in the ground to ripen now.

- **Day 12 (Evaluation & Save Test):** Sleeping on the last day calculates
  the **Agroecological Score** (Soil Health + Biodiversity Index + Total
  Revenue + the organic share), saves through `PersistenceManager`, and
  displays victory metrics.

## 7. Implementation Tasks for Agent Team

1. **Agent 1 (Data & Components):** Define `SoilComponent`, `PlantComponent`, `AutomationComponent`, and the `SAVE_SCHEMA` inside `components.py` and `events.py`.
2. **Agent 2 (Simulation Systems):** Implement `plant_growth_system.py` and `syntropic_system.py` to calculate tile interactions (shade, nitrogen transfer, and water depletion).
3. **Agent 3 (Tilemap & Visuals):** Set up `TilemapLayer` grid rendering, cell selection cursor, and dynamic plant growth sprites in `garden_render_system.py`.
4. **Agent 4 (UI & Persistence):** Build `GardenHUD` using `pyguara.ui.design_system` (`DSPanel`, `DSProgressBar`, `DSSlider`) and wire auto-save logic via `pyguara.persistence`.
