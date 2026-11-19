# Game Design Document: *O Protocolo Bandeira*

**Version:** 1.0
**Engine:** PyGuara v0.2 (Beta Buriti)
**Genre:** Horde Survivor / Bullet Heaven (Reverse Bullet Hell)
**Theme:** Garbage Collection & Insect Control

---

## 1. Executive Summary

### 1.1 Logline

You are nature's ultimate Garbage Collector: a Giant Anteater (Tamanduá-Bandeira) standing alone against an infinite stack overflow of termites. "Sweep the Heap" before the system crashes.

### 1.2 The "Meta" Pitch

*O Protocolo Bandeira* is the **Stress Test** for the PyGuara Engine.

* **The Anteater** represents the **Garbage Collector (GC)**: An automated process that sweeps memory to free up resources.
* **The Termites** represent **Memory Leaks**: Small, unreferenced objects that multiply rapidly and clog the system.
* **The Frame Rate** is the Health Bar. If there are too many enemies (too much lag), the system "Crashes" (Game Over).

---

## 2. Gameplay Mechanics

### 2.1 Core Loop: "Sweep the Heap"

Unlike the Platformer (precision) or Snake (logic), this is about **Flow**.

1. **Survive:** Enemies spawn in waves at the edges of the screen and rush the player.
2. **Consume:** The player's primary weapon (The Tongue) automatically targets and "collects" enemies within range.
3. **Optimize:** collected enemies drop **"Data Shards"** (XP). Collecting enough triggers a "System Upgrade," allowing the player to clear the screen faster.

### 2.2 Controls & Abilities

#### **The Hero: Agent Bandeira**

* **Movement:** WASD / Left Stick.
* **Primary Weapon: The Tongue (Auto-Fire)**
* *Behavior:* A rapid-fire raycast that targets the nearest enemy.
* *Visual:* A pink line renderer that lashes out and retracts.
* *Upgrade Path:*
* *Multithreading:* Tongue splits into 3 concurrent lashes.
* *Long Polling:* Increases range by 50%.
* *Sticky Session:* Enemies hit are slowed by 40%.





#### **Ultimate: The Bandeira Swipe**

* **Trigger:** Space Bar / Face Button South.
* **Cooldown:** Based on "Cache Fill" (kills).
* **Behavior:** The Anteater spins, using its massive bushy tail as a bludgeon.
* **Effect:** Massive 360-degree Knockback + Stun. Clears the immediate area.

### 2.3 Enemies (The Leaks)

1. **Termite Worker (The Byte):**
* *Behavior:* Spawns in clusters of 50. Weak, fast, linear movement.
* *Threat:* Collides to deal small damage.


2. **Flying Ant / Tanajura (The Stack Overflow):**
* *Behavior:* Ignores terrain collision. Flies directly at the player.
* *Threat:* Harder to hit; requires "Anti-Air" upgrade logic.


3. **Armored Beetle (The Memory Dump):**
* *Behavior:* Slow, massive HP. Acts as a moving wall.
* *Threat:* pushes other enemies forward. Requires "Armor Breaking" claws.



---

## 3. Visual & Audio Aesthetic

### 3.1 Art Style: "Murundus Matrix"

* **Biome:** **Campo de Murundus** (Mound Field). A flat red-earth plain dotted with hundreds of termite mounds.
* **Palette:**
* **Player:** Grey/Black fur with a high-visibility **Guará Orange** vest.
* **Enemies:** **Neon Green** (`#39FF14`). They should look like "Code" or "Glitches" invading the natural world.
* **Terrain:** Deep Red Earth (`#6d2a0e`) to contrast with the neon enemies.



### 3.2 Audio Direction

* **Music:** **"Percussion Protocol."**
* Starts with a solitary drum beat.
* As enemy count rises (), layers of heavy **Surdo** and **Taiko** drums are added, matching the intensity of the CPU load.


* **SFX:**
* *Tongue Lash:* Synthesized "Laser Slurp" sounds.
* *Enemy Death:* A satisfying 8-bit "Crunch" or "Delete" sound.



---

## 4. Technical Implementation Specifications

This demo exists to validate the engine's Performance & Optimization systems.

### 4.1 Collision Optimization (Spatial Partitioning)

* **The Challenge:** Checking collision for 1 Player vs. 2,000 Enemies is .
* **Validation:**
* Implement a **QuadTree** or **Spatial Hash Grid** in the `CollisionSystem`.
* The game acts as a benchmark tool; include a debug toggle to visualize the QuadTree subdivisions in real-time.



### 4.2 Memory Management (Object Pooling)

* **The Challenge:** Python's garbage collection overhead will cause stutters if we `init` and `del` 100 enemies per second.
* **Validation:**
* Implement `EntityPool` for Termites and Projectiles.
* Entities are "Deactivated" (hidden/removed from update list) rather than destroyed, then "Recycled" for the next spawn.



### 4.3 Rendering Pipeline (Batching)

* **The Challenge:** 2,000 individual draw calls will kill the frame rate.
* **Validation:**
* The `RenderSystem` must support **Instanced Rendering**.
* All Termites share 1 Texture Atlas. The engine should issue a single draw call for all active termites.



---

## 5. Level Design: "The Infinite Heap"

**Level Name:** `protocol_survival.py`

* **Map Structure:** Infinite scrolling plane (Torus topology—going off the right edge wraps to the left).
* **Obstacles:**
* **Termite Mounds:** Indestructible static bodies. Used to kite enemies.
* **Doce de Leite Puddles:** (See Easter Egg).



**Wave Progression:**

* **0:00 - 1:00:** "Warm Up." Small clusters of Termites. Tests basic movement.
* **1:00 - 3:00:** "The Leak." Continuous stream of enemies. Tests Object Pooling.
* **3:00+:** "Garbage Collection." Maximum density (2000+ entities). Tests Spatial Partitioning and Rendering.

---

## 6. Cultural Easter Egg: "O Doce de Leite"

**Type:** Power-Up / Cultural Reference
**Context:** In Brazil, it is common knowledge (and folklore) that Anteaters love sweet things, specifically *Doce de Leite* (Milk Jam).

* **The Item:** A glowing jar of golden jam.
* **Effect:** **"Sugar Rush."**
* Global Time Scale slows to 0.5 (Enemies move slow).
* Player Time Scale remains 1.0 (Player moves fast relative to world).
* Visuals: Screen edges vignette with a golden/caramel glow.
* *Meta-Meaning:* Gives the "Garbage Collector" more CPU cycles to process the queue.



---

## 7. Asset Requirements Checklist

**Sprites:**

* [ ] `spr_anteater_run`: 4-frame top-down run cycle.
* [ ] `spr_anteater_swipe`: 360-degree tail spin blur.
* [ ] `spr_tongue_tip`: The end of the tongue.
* [ ] `spr_termite_walk`: 2-frame wiggle.
* [ ] `spr_flying_ant`: 2-frame wing flap.
* [ ] `tex_ground_red`: Tiling earth texture.
* [ ] `spr_mound_01`, `spr_mound_02`: Obstacles.

**Audio:**

* [ ] `bgm_drums_layer1.ogg` (Slow)
* [ ] `bgm_drums_layer2.ogg` (Fast)
* [ ] `sfx_tongue_fire.wav`
* [ ] `sfx_enemy_pop.wav`
* [ ] `sfx_sugar_rush_loop.wav`
