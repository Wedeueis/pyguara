# Game Design Document: *Coral: A Tríade*

**Version:** 1.0
**Engine:** PyGuara v0.2 (Beta Buriti)
**Genre:** Logic / Arcade Snake
**Theme:** Brazilian Mimicry & Biological Rules

---

## 1. Executive Summary

### 1.1 Logline

A twist on the classic Snake genre where a "True Coral" snake must consume prey in a specific color sequence (Red-White-Black) to maintain its potency. Fail the pattern, and degenerate into a harmless "False Coral."

### 1.2 The "Meta" Pitch

*Coral: A Tríade* demonstrates the **PyGuara Engine's** ability to handle complex logical state and memory management.

* **The Snake Body** represents **Dynamic Memory Allocation**: A growing array of entities that must be managed without leaks.
* **The Pattern** represents **State Validation**: proving the ECS can handle non-physics logic rules.
* **The Mimicry** represents **Data Inheritance**: How entities can share behavior but swap properties (Components) on the fly.

---

## 2. Gameplay Mechanics

### 2.1 Core Loop: "The Triad Pattern"

Unlike standard Snake, the challenge is not just length, but **Order**.

1. **Hunt:** The map contains Red Beetles, White Grubs, and Black Spiders.
2. **Match:** The HUD displays the active "DNA Requirement" (e.g., currently needs **WHITE**).
3. **Grow:**
* **Success:** Eating the correct color advances the triad (R -> W -> B -> R). The snake grows, and the score multiplier increases.
* **Failure:** Eating the wrong color triggers **"Mimicry Degeneration."**



### 2.2 Snake States

#### **State A: Coral Verdadeira (True Form)**

* **Visuals:** Bright Neon Red, White, and Black bands. Emits a glow.
* **Buff:** Score Multiplier x2. Predators (Owls) avoid you.
* **Goal:** Complete 3 full Triads to trigger "Venom Mode."

#### **State B: Falsa Coral (False Form)**

* **Visuals:** Dull, desaturated bands. No glow. Glitchy particle effects.
* **Debuff:** Score Multiplier x1. Predators actively hunt you.
* **Recovery:** Must complete 1 full Triad perfectly to evolve back to True Form.

#### **State C: Venom Mode (Power-Up)**

* **Trigger:** 3 Perfect Triads.
* **Effect:** The screen tints Orange. The snake moves 20% faster and becomes invincible. It can smash through Termite Mounds (obstacles) and eat Predators for massive points.

---

## 3. Visual & Audio Aesthetic

### 3.1 Art Style: "Luminous Leaf Litter"

A high-contrast aesthetic designed to pop on OLED screens and stress-test the renderer's batching capabilities.

* **Background:** Dark Charcoal (`#2C2C2C`) soil with scattered dry leaves (browns/greys).
* **The Snake:**
* **Red:** PyGuara Brand Orange (`#D95204`).
* **White:** Brand Cream (`#F0EAD6`).
* **Black:** Deep Void Black (`#000000`).


* **UI:** Minimalist. The "Next Color" indicator floats near the snake's head (World Space UI).

### 3.2 Audio Direction

* **Music:** "Rhythmic Hiss."
* *Base Layer:* A slow, heartbeat-like drum.
* *Layer 2 (True Form):* Shakers representing the rattle of dry leaves.
* *Layer 3 (Venom Mode):* A high-tempo Flute melody inspired by northeastern Brazilian *Pífano* bands.


* **SFX:**
* *Correct Eat:* A crisp "Chime."
* *Wrong Eat:* A digital "Glitch/Static" noise.
* *Venom Mode Start:* A loud hiss followed by a bass drop.



---

## 4. Technical Implementation Specifications

This demo validates engine features that the Platformer ignored.

### 4.1 ECS & Memory Management

* **Entities:**
* `SnakeHead`: The "Driver." Contains `GridMovement` and `PatternState`.
* `BodySegment`: A growing list of entities.


* **The Challenge:**
* **Dynamic Arrays:** Validates that the `EntityManager` can handle spawning/despawning entities rapidly (eating food, growing body) without garbage collection stutters.
* **Parent-Child Lag:** The body segments must follow the head's "History" of positions. This validates the `Update` loop stability.



### 4.2 Logic vs. Rendering Separation

* **Logic Tick:** The game logic runs on a Grid (e.g., 10 steps per second).
* **Render Tick:** The display runs at 60 FPS+.
* **Validation:** The `RenderSystem` must interpolate the snake's position between grid cells so movement looks fluid, not jerky. This tests **Alpha Interpolation** in the Game Loop.

### 4.3 Algorithms (AI)

* **Predator AI (The Owl):**
* Uses **A* Pathfinding** (`pyguara.ai.pathfinding`) to hunt the snake when in "False Form."
* Validates the integration of AI Systems with the Grid.



---

## 5. Level Design: "The Biomes"

**Level Name:** `coral_biomes.py`

1. **Stage 1: The Buried Pipe (Tutorial)**
* Small enclosed space.
* Only Red and White food appears initially.
* **Goal:** Teach the color switching mechanic.


2. **Stage 2: The Termite Field**
* Open map filled with destructible Termite Mounds.
* **Mechanic:** Player must use "Venom Mode" to smash mounds and open shortcuts.


3. **Stage 3: The Canopy Shadow**
* **Mechanic:** "Fog of War."
* The player can only see a radius around the snake's head (simulating being under heavy leaf litter). Requires memory of where the food spawned.



---

## 6. Asset Requirements Checklist

**Sprites (Vector / Pixel):**

* [ ] `spr_snake_head`: Distinctive rounded nose.
* [ ] `spr_segment_red`: Neon Orange square/circle.
* [ ] `spr_segment_white`: Cream square/circle.
* [ ] `spr_segment_black`: Black square/circle.
* [ ] `spr_food_beetle`: Red insect.
* [ ] `spr_food_grub`: White insect.
* [ ] `spr_food_spider`: Black insect.
* [ ] `spr_predator_owl`: Shadowy silhouette with glowing yellow eyes.

**Audio:**

* [ ] `bgm_leaf_litter_base.ogg`
* [ ] `bgm_leaf_litter_venom.ogg`
* [ ] `sfx_eat_correct.wav`
* [ ] `sfx_eat_wrong.wav`
* [ ] `sfx_crash.wav`

# Appendix: Expanded Mechanics & Cultural References

## Appendix A: "O Contrato do Cacique" (The Chief's Contract)

**Type:** Cultural Easter Egg / Secret Mechanic
**Reference:** The *Fundação Cacique Cobra Coral*, a Brazilian esoteric foundation famous for allegedly controlling the weather (stopping rain) for major events.

### A.1 The Trigger

* **Location:** *Stage 3: The Canopy Shadow* (The only level with active Rain particles).
* **Condition:** Rare Spawn (1% chance replacing a food item) OR spawns automatically if the player maintains "True Form" (Multiplier x2) for 60 seconds without taking damage.
* **Item:** A **White Feather** (Pena Branca).

### A.2 The Effect

Upon eating the feather, the game state changes dramatically:

1. **Visuals:**
* Rain particle emitter sets `active = False`.
* Global lighting tint transitions from **Gloomy Grey** to **Clear Sky Blue** (Tween duration: 2.0s).
* The Snake's Head sprite swaps to `spr_snake_cocar` (wearing a small indigenous headdress) or `spr_snake_glasses` (dark glasses).


2. **Audio:**
* SFX: A thunderclap playing in reverse (`sfx_thunder_implode.wav`) followed by a "Choir" chord.


3. **UI Feedback:**
* A Toast Notification appears at the top of the screen: **"CONTRATO ASSINADO: TEMPO LIMPO"** (Contract Signed: Clear Weather).



### A.3 Technical Purpose

* **Event Decoupling:** Validates that the `SnakeSystem` can trigger global environment changes without holding a reference to the `WeatherSystem` or `ParticleSystem`, purely via the `EventBus`.

---

## Appendix B: The "Ophiophagus" Mechanic (Cut Content / Future Mode)

**Type:** Advanced AI / Alternative Game Mode
**Concept:** Originally planned for Level 1, this mechanic changes the game from "Puzzle" to "Combat."

### B.1 The Rival Snakes

* **Entity:** `FalseCoralAI`.
* **Behavior:**
* These are autonomous snakes controlled by `AStarPathfinding`.
* They compete for the same food as the player.
* They do **not** follow the Color Triad rule (chaos agents).


* **Interaction:**
* **Collision:** If the Player's head hits their body -> Player takes damage/Game Over.
* **Predation:** If the Player is in **Venom Mode**, colliding with a Rival Snake's head "eats" them, converting their entire length into Score Points instantly.



### B.2 Implementation Note

This feature remains in the design as a "Stretch Goal" to stress-test the **Navigation Mesh** capabilities of the engine in a dynamic environment (since the "walls" i.e., snake bodies, are constantly moving).
