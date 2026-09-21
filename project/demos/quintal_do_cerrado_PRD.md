## **Project Name:** _Quintal do Cerrado_ (Working Title)

**Module Path:** `games/quintal_cerrado/`
**Target Duration:** 15-Minute Playable Capstone Demo
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

To validate engine save/load capabilities, the game state must save automatically every 60 seconds or on manual exit:

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

## 6. 15-Minute Playable Loop (Demo Script)

- **0:00 – 2:00 (Onboarding):** Player starts with a barren $12 \times 8$ dirt plot and a few legume seeds (_Guandu_). Learns basic tilling, planting, and watering.
- **2:00 – 5:00 (Stratification):** Unlocks _Baru_ and _Cagaita_. Discovers that planting _Cagaita_ under the shade of _Baru_ with _Guandu_ at the base boosts growth speed by $40\%$.
- **5:00 – 8:00 (The Fork in the Road):** Pest infestation arrives. Player chooses:
    - _Option A:_ Buy expensive NPK & Chemical Pesticide (Instant recovery, but soil turns dusty red; crop sell value drops).
    - _Option B:_ Plant _Pequi_ and add organic compost (Slower recovery, but unlocks premium organic market pricing).

- **8:00 – 12:00 (Automation Expansion):** Credits allow purchasing the Solar Panel and Drip Irrigation. The garden runs partially hands-free.

- **12:00 – 15:00 (Evaluation & Save Test):** System calculates the **Agroecological Score** (Soil Health + Biodiversity Index + Total Revenue). Automatically triggers `PersistenceManager.save("garden_slot_1")` and displays victory metrics.
## 7. Implementation Tasks for Agent Team

1. **Agent 1 (Data & Components):** Define `SoilComponent`, `PlantComponent`, `AutomationComponent`, and the `SAVE_SCHEMA` inside `components.py` and `events.py`.
2. **Agent 2 (Simulation Systems):** Implement `plant_growth_system.py` and `syntropic_system.py` to calculate tile interactions (shade, nitrogen transfer, and water depletion).
3. **Agent 3 (Tilemap & Visuals):** Set up `TilemapLayer` grid rendering, cell selection cursor, and dynamic plant growth sprites in `garden_render_system.py`.
4. **Agent 4 (UI & Persistence):** Build `GardenHUD` using `pyguara.ui.design_system` (`DSPanel`, `DSProgressBar`, `DSSlider`) and wire auto-save logic via `pyguara.persistence`.
