# Game Design Document: *Guará & Falcão: Veredas*

**Version:** 1.0
**Engine:** PyGuara v0.2 (Beta Buriti)
**Genre:** 2D Puzzle-Platformer / Metroidvania-lite
**Theme:** Brazilian Cerrado / Symbiotic Tech

---

## 1. Executive Summary

### 1.1 Logline

In the twilight of the Cerrado, a heavy-stepping Maned Wolf and a swift Aplomado Falcon must work together to purge "Bugs" from the Veredas.

### 1.2 The "Meta" Pitch

*Guará & Falcão* is not just a game; it is an allegorical tour of the **PyGuara Engine**.

* **The Wolf** represents the **Physics Engine**: heavy, grounded, and colliding with the world.
* **The Falcon** represents the **Event System**: agile, observing from above, and triggering actions that physics cannot reach.
* **The Bugs** represent **Software Bugs**: glitchy entities that must be "caught" (resolved) to clear the memory.

---

## 2. Gameplay Mechanics

### 2.1 Core Loop: "The Flush & The Dive"

The game is built on a verified biological behavior (commensalism):

1. **Traverse:** The Player controls **Guará** (Wolf) to navigate complex terrain. The tall grass obscures vision and hides enemies.
2. **Flush:** As Guará walks, his physical collider pushes the grass aside (`GrassDisplacement` Component). This "flushes" out hidden **Bugs**.
3. **Strike:** The Player triggers **Falcão** (Falcon) to perform a "Precision Dive." The Falcon leaves its hover state, tweens to the target, captures the bug, and returns.

### 2.2 Character Controls

#### **Guará (The Physics Object)**

* **Input:** Left Stick / WASD.
* **Movement:** Heavy, momentum-based.
* **Abilities:**
* **Stilt Walk:** Can step over high obstacles (high step-height in physics config).
* **Bash:** Can push heavy physics crates to clear paths.
* **Bark:** A localized physics impulse that shakes trees to drop fruit.



#### **Falcão (The Event Trigger)**

* **Input:** Right Stick (Aim) + Right Trigger (Dive) / Mouse Aim + Click.
* **Movement:** Automatically hovers above Guará (parented entity with offset).
* **Abilities:**
* **The Dive:** Instantly moves to the cursor position to interact with switches or enemies.
* **Scan:** Highlighting interactive objects (rendering debug wireframes) in the world.



### 2.3 The "Bug" Enemies

Bugs are glitchy, pixelated insects that corrupt the world.

* **Null Pointer Beetle:** Walks blindly off ledges. Must be caught before it falls.
* **Infinite Loop Locust:** Spins rapidly in place, creating a wind barrier. Must be interrupted by a Dive.
* **Memory Leak Moth:** Duplicates itself constantly. Must be caught to free up "RAM" (Score).

---

## 3. Visual & Audio Aesthetic

### 3.1 Art Style: "Cerrado Silhouette"

To save assets while reinforcing the brand, the game uses a high-contrast style.

* **Foreground:** Pure **Black** silhouettes (Terrain).
* **Midground:** **Guará Orange** (Wolf) and **Aplomado Slate** (Falcon) stand out vividly against the dark.
* **Background:** Layers of **Charcoal** and **Deep Grey** (Parallax Ipê trees).
* **The Glitch:** Enemies (Bugs) are rendered in bright **Neon Cyan** or **Magenta** (Cyberpunk colors) to look "foreign" to the natural environment.

### 3.2 Audio Direction

* **Music:** Acoustic guitar (Viola Caipira) mixed with subtle 8-bit arpeggios.
* **Sound Effects:**
* *Wolf Steps:* Heavy bass thuds.
* *Falcon Dive:* A sharp "Swoosh" combined with a synthesizer "Ping."
* *Bug Capture:* The satisfying "Crunch" of a bug combined with a "Coin Pickup" sound.



---

## 4. Technical Implementation Specifications

This section defines exactly which Engine Systems are validated by this game.

### 4.1 ECS Architecture Verification

* **Entities:**
* `GuaraEntity`: Uses `RigidBody`, `BoxCollider`, `Sprite`, `PlatformerController`.
* `FalconEntity`: Uses `Transform` (No Physics), `Sprite`, `TweenAnimator`.


* **Systems:**
* `PhysicsSystem`: Handles the Wolf.
* `ScriptingSystem`: Handles the Falcon's AI follow logic.
* `ParticleSystem`: Renders the "Grass" being pushed aside (validating high entity count performance).



### 4.2 Physics & Collision (The Wolf)

* **Requirements:**
* One-way platforms (for the Wolf's long legs jumping up).
* Dynamic rigidbodies (Crates) that the Wolf can push.
* `TriggerVolume` on the Wolf's feet to detect "Grass" entities.



### 4.3 Events & Messaging (The Falcon)

* **Requirements:**
* **Input Event Routing:** The `InputManager` must intelligently route "Movement" events to the Wolf and "Action" events to the Falcon simultaneously.
* **Animation Events:** The Falcon's "Dive" is a `Tween`. When the Tween finishes (`on_complete`), it must fire a `BugCaughtEvent`.



### 4.4 Brand Integration (UI)

* **HUD:** Minimalist.
* **Health Bar:** Represented by the Wolf's stamina.
* **"RAM" Meter:** Fills up as you collect bugs.


* **Font:** Uses **JetBrains Mono** for all in-game text, reinforcing the "Code" theme.

---

## 5. Level Design: "The Vertical Slice"

**Level Name:** `veredas_tutorial.py`

1. **Screen 1: The Wake Up.**
* Wolf wakes up. Simple movement tutorial (Left/Right).
* *Engine Test:* Sprite Animation State Machine (Idle -> Walk).


2. **Screen 2: The Obstacle.**
* A high wall. Wolf cannot jump it.
* *Mechanic:* Push a heavy crate to make a step.
* *Engine Test:* Physics Mass & Friction.


3. **Screen 3: The Symbiosis.**
* Wolf enters tall grass. Screen shakes.
* A **Null Pointer Beetle** flushes out.
* Time slows down (Engine `time_scale` test).
* Tutorial prompt: "Press [Action] to Debug."
* Falcon dives, catches bug. Gate opens.


4. **Screen 4: The Loop.**
* Open platforming section combining jumps, crate pushing, and bug catching.



---

## 6. Asset Requirements Checklist

**Sprites (Pixel Art / Vector):**

* [ ] `spr_guara_walk`: 8 frames walk cycle.
* [ ] `spr_guara_idle`: Breathing animation.
* [ ] `spr_falcon_hover`: Wings flapping.
* [ ] `spr_falcon_dive`: Single frame "Arrow" shape.
* [ ] `spr_bug_glitch`: 3 frames of noise/static.
* [ ] `env_grass_blade`: Simple vertical line (will be instanced 1000x).

**Audio:**

* [ ] `bgm_veredas_twilight.ogg` (Loopable).
* [ ] `sfx_step_heavy.wav`.
* [ ] `sfx_falcon_cry.wav`.
* [ ] `sfx_glitch_noise.wav`.
