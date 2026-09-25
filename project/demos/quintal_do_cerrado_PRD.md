## **Project Name:** _Quintal do Cerrado_ (Working Title)

**Module Path:** `games/quintal_cerrado/`
**Target Duration:** a twelve-day playable capstone demo, played turn by turn
**Engine:** PyGuara 2D (`pyguara`)
**Theme:** Agroforestry, Syntropic Agriculture, Cozy Incremental Gardening
## 1. Executive Summary & Vision

_Quintal do Cerrado_ is a cozy, incremental gardening game set in the Brazilian Cerrado. Inspired by _Stardew Valley_ and syntropic agroforestry, players restore a grid-based plot of dirt by planting native flora, balancing natural ecosystem dynamics (sunlight, shade, soil nutrients, moisture, and pest pressure), or opting for short-term chemical shortcuts.
### Primary Showcase Goals for PyGuara

1. **Tilemap & Grid System (`pyguara.tilemap` & `pyguara.physics.tilemap`):** Multi-layer grid interaction, dirt tilling, dynamic tile transitions, and spatial query checks per cell.
2. **Persistence & Migration (`pyguara.persistence`):** Saving the garden at the end of every day, along with player inventory, unlocked tech, the day and its stamina, and the sky — plus cross-session restoration. The schema is versioned; the turn-based build is **v2**, and a v1 save is refused cleanly rather than half-loaded.
3. **PyGuara Design System (`pyguara.ui.design_system`):** Clean integration of the **Cerrado Dusk / Day** UI tokens (`DSPanel`, `DSButton`, `DSProgressBar`, `DSSlider`) for HUD, store, and plant inspection overlays.
## 2. Core Gameplay Mechanics & Ecosystem Loop

### A. The Turn: a day, its stamina, and the night

The garden is **turn-based**, and this frames every other mechanic below.

- **A day is the turn.** Nothing in the simulation moves while the player
  is in one. Plants grow, soil dries, pests spread, weeds take ground and
  the sky turns *only* when the player sleeps.
- **Stamina bounds the day.** Twelve points, spent per action: till 2,
  plant 1, water 1, compost 2, spray 3, harvest 1. Placing a bought
  structure is free (the store already charged for it), and so are
  choosing a tool, reading the inspector and shopping — charging for
  looking would make the player stop looking.
- **An action that does nothing costs nothing.** Planting on untilled
  ground or tilling worked soil is refused without taking the day.
- **Sleeping resolves the night**, restores the pool, advances the day and
  opens the **morning report**. Leftover stamina does not carry over, so
  ending a day early is a choice rather than banked energy.

Why turn-based: the real-time build punished thinking. The plot dried out
while the player read the inspector, and there was never a moment to plan
the next move. A cozy game has to let the player stop.

### B. The Agroforestry Grid (Tilemap)

- **Grid Layout:** $12 \times 8$ playable dirt tiles (`TilemapLayer`).
- **Tile Properties:** Each cell tracks `moisture`, `nitrogen`, `organic_matter`, `shade_level`, and `pest_pressure`.
- **Layer Composition:**
    - `Layer 0 (Terrain)`: Base soil, tilled soil, paths, and water pipes.
    - `Layer 1 (Flora)`: Plant sprites, growth stages, and shade/canopy overlays.
    - `Layer 2 (Automation)`: Drip irrigation, solar panels, and automated sensors.
### C. Plant Stratification & Syntropic Consortium

Plants are grouped into canopy layers. Planting complementary species in
adjacent cells provides mutual benefits: an understory plant gains
$40\%$ growth speed once an adjacent canopy tree has matured enough to
cast shade, and a ground-cover plant gains the same beside any plant of a
different layer.

| Species | Layer | Days / stage | Seed | Sells for | Note |
|---|---|---|---|---|---|
| **Guandu** | ground cover | 1.0 | 5 | 10 | the starter legume |
| **Cagaita** | understory | 1.5 | 10 | 20 | wants shade overhead |
| **Pequi** | canopy | 1.7 | 12 | 26 | suppresses pests nearby |
| **Baru** | canopy | 2.0 | 15 | 30 | the slow, valuable one |
| _Weed_ | ground cover | 0.7 | — | — | spreads on its own; pulling it yields a generic seed |

Three stages separate a seedling from a harvest, so a guandu is three
nights and a baru six. Sale prices are before the organic premium (2.0x)
or the chemical discount (0.5x).
### D. The Agroecological Dilemma: Natural vs. Chemical

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

Each rung is unlocked by *placing* the one before it, and each does its
work **overnight** — which is the point of the tree: it buys back stamina
for everything the player would rather spend a day on.

1. **Solar Micro-Panel** (40): pays 8 Sementes a night and powers three
   devices, handed out in placement order.
2. **Drip Irrigation System** (40, needs power): fills every cell in its
   $3 \times 3$ to the target moisture each night, so they are never dry
   in the morning.
3. **Syntropic Soil Sensor** (30): prints moisture, humus and pest bars on
   the tiles it reaches, out to a $5 \times 5$.
4. **Auto-Harvester Drone** (90, needs power): collects up to two ready
   crops in its $3 \times 3$ each night and sells them through the same
   path the harvest tool uses — a pair of extra hands, not a replacement
   for tending the plot.
## 4. UI / UX Design System Integration

The UI uses the established **Cerrado Design System**
(`pyguara.ui.design_system`) for its colours and its bevelled overlay
furniture, plus two things of its own: soft translucent **cards**
(`hud_widgets.CardPanel`) and an **icon set drawn from primitives**
(`icons.py`, no textures — the same house style as the plot itself).

- **Color Palette:** warm earth tones (`--sand-100` to `--rock-600`),
  **Guará Pelt Orange** (`#e2621f`) for primary actions, and **Colonial
  Green / Sage** (`--colonial-500`) for garden status.
- **Top ribbon**, three cards:
    - **Resources:** a seed pouch and the Sementes count, chips for solar
      power and generic seed stock, the pest status line, and a row of
      **stamina pips** — one per point, spent ones dimmed, because stamina
      is discrete and what the player needs to read is "how many more
      things can I do".
    - **Weather & calendar:** today's condition, **"Dia 3 / 12"**, and the
      next two days as icons. There is no clock: a day does not pass, it
      ends.
    - **Resilience:** the live Agroecological Score as a bar and a grade —
      the same `compute_score` the evaluation runs, so the ribbon cannot
      flatter a garden the score sheet then marks down.
- **Bottom dock**, three groups of icon slots: **ESPÉCIES**,
  **FERRAMENTAS**, **BASE** (Dormir, Loja, Menu). Each slot carries its
  icon, its price or seed stock, and its hotkey in a corner badge. A slot
  the player cannot pay for — in Sementes *or* stamina — dims, and the
  grid cursor turns red over a cell where the active tool would do
  nothing.
- **Right column:** the **cell inspector** — a portrait of the plant
  (drawn by the same function that draws it on the plot), the syntropic
  ladder with its layer lit, and four icon gauges (Umidade, Húmus, Sombra,
  Pragas, the last stepping calm → amber → crimson with severity) — plus a
  message toast.
- **On the plot:** a hover tooltip showing moisture and pests over the
  tile under the cursor, after a short dwell.
- **Overlays**, all pushed over the frozen garden: the **morning report**
  (`morning.py`), the **store**, the **pause menu** and the
  **evaluation**.

## 5. Technical Architecture & Persistence Specification

### A. Directory Structure

```
games/quintal_cerrado/
├── bootstrap.py            # Composition root, DI container, ModernGL render graph
├── main.py                 # Game entry point
├── scenes.py               # TitleScene & GardenScene (the turn loop)
├── turn.py                 # The day, its stamina, and what each action costs
├── clock.py                # The calendar: which day, how many left
├── components.py           # SoilCell, PlantComponent, AutomationComponent, PlayerEconomy
├── garden_grid.py          # The 12x8 plot over pyguara.tilemap
├── species.py              # The species table (layers, days per stage, prices)
├── structures.py           # The automation tech tree
├── economy.py              # Sales, seed stock, the organic premium
├── treatments.py           # Compost and spray
├── scoring.py              # The Agroecological Score
├── plant_states.py         # Per-plant FSM (seedling -> ... -> dying)
├── garden_states.py        # Plot-wide pest FSM, paced in days
├── weather.py              # Conditions and their effects
├── persistence_schema.py   # Save payload v2: parse, then apply
├── events.py               # Garden & save event definitions
├── systems/
│   ├── day_resolver.py     # A night: what the garden does while you sleep
│   ├── soil_system.py      # Moisture: rain in, evaporation out
│   ├── plant_growth_system.py
│   ├── shade_system.py     # Canopy cover
│   ├── syntropic_system.py # The companion bonus, which reads shade
│   ├── pest_system.py      # Spread, decay, and the health it costs
│   ├── weed_spread_system.py
│   ├── automation_system.py# Solar, drip and the drone, once a night
│   └── weather_system.py   # Tomorrow's sky
├── garden_widget.py        # The plot as a clickable Canvas, plus its juice
├── art.py                  # Soil, plants and structures, drawn from primitives
├── icons.py                # The HUD's icon set, likewise
├── layout.py               # Where every region of the screen sits
├── hud.py / hud_widgets.py / ribbon.py   # Cards, dock slots, the top ribbon
├── morning.py              # The morning report overlay
├── store.py / pause.py / evaluation.py / overlay.py
├── juice.py                # Motes and floating labels
├── soil_health_effect.py   # A post-process grade driven by soil health
└── assets/audio/           # Placeholder SFX + the script that generates them
```

There are no texture assets: soil tiles, plants, structures and every HUD
icon are renderer primitives.

### B. Persistence & Serialization Specification (`pyguara.persistence`)

The game saves at the end of every day (when the player sleeps) and on
exit — which includes closing the window. There is no periodic autosave:
between two mornings nothing changes that a save could miss.

The payload is hand-built plain data, because the engine's serializer does
not round-trip dataclasses, and loading is **parse, then apply**, so a
corrupt or hand-edited save is refused without ever half-loading the plot.

```python
# State schema stored via pyguara.persistence.manager (SCHEMA_VERSION = 2)
SAVE_SCHEMA = {
    "version": 2,
    "day": 4,                 # which turn, 1-based
    "stamina": 7,             # what is left of it
    "weather": {              # saved: a condition lasts a whole day, and
        "condition_id": "rainy",   # the forecast is two days of planning
        "forecast": ["clear", "windy"],
    },
    "player": {
        "credits": 150.0,
        "revenue": 88.0,
        "organic_sales": 4,
        "chemical_sales": 2,
        "inventory": {"solar_panel": 1},
        "unlocked_tech": ["solar_panel", "drip_irrigation"],
    },
    "conditions": {           # the plot-wide pest FSM
        "phase": "outbreak",
        "last_treatment": "",
        "organic_resolutions": 3,
        "chemical_resolutions": 1,
        "days_in_phase": 2.0,
    },
    "grid": [
        {
            "x": 0, "y": 0,
            "soil_type": "tilled_dirt",
            "moisture": 0.75, "nitrogen": 0.80, "organic_matter": 0.90,
            "shade_level": 0.4, "pest_pressure": 0.0,
            "is_chemically_degraded": False,
            "plant": {
                "species_id": "baru",
                "growth_stage": "mature",
                "growth_progress": 0.42,
                "health": 1.0,
                "is_chemical_boosted": False,
                "growth_multiplier": 1.4,
                "pest_pressure": 0.0,
                "resume_stage": None,      # where an infested plant returns to
                "resume_progress": None,
            },
            "automation": {"kind": "drip_irrigation", "powered": True},
        }
        # ... 96 tiles total
    ],
}
```

**v1 saves are not migrated.** A real-time save has no day, no stamina and
no sky, and its elapsed seconds mean nothing here; the version check
refuses it and the title screen starts a fresh garden.

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

## 7. Implementation Status

The demo is **complete**, and the modules that deliver each part of this
spec are named in §5A rather than assigned as tasks. Where the shipped
game departs from the original plan, it is recorded here so the spec and
the code cannot quietly disagree:

- **Turn-based, not real-time.** The original §6 was a fifteen-minute
  wall-clock script. The simulation now runs only when the player sleeps
  (`systems/day_resolver.py`), and a session is twelve days. See §2A.
- **`SoilComponent` is not a component.** Soil is a plain
  `list[list[SoilCell]]` on `GardenGrid`, parallel to the tilemap: it is
  per-*tile* data, not per-entity, and an ECS component per cell would
  have bought nothing.
- **No `garden_render_system.py`.** The plot draws itself through
  `garden_widget.GardenGridCanvas`, a clickable `Canvas` that renders into
  the world pass so the post-process shaders can see it.
- **Nitrogen is tracked but not yet simulated.** `SoilCell.nitrogen`
  round-trips through the save and is read by no system; the nutrient loop
  §2B's tile properties imply is the obvious next mechanic.
- **The sensor draws bars on tiles, not a heatmap overlay.**

### Known gaps

- The store cannot be opened from the morning report, so a player who
  learns they can afford the next rung has to close it first.
- The evaluation is offered once, after the last night. There is no way to
  keep playing past day twelve and be re-scored.
- `FileStorageBackend.base_path` is CWD-relative, not an OS user-data
  directory (engine issue #43), so saves land beside the repo.
