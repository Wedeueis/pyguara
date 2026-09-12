# Game Design Document: *Vinagre: Matilha*

**Version:** 1.0
**Engine:** PyGuara v0.5
**Genre:** 90s Real-Time Squad Tactics (Pikmin-meets-Cannon Fodder, Top-down)
**Theme:** Distributed Pack Intelligence & Emergent Coordination

---

## 1. Executive Summary

### 1.1 Logline

A pack of 6-12 bush dogs (*cachorros-vinagre* — vinegar dogs, named for their
scent gland), hyper-social semi-aquatic hunters, must flush a jaguar out of
the Cerrado's riverbeds by out-flanking it as one coordinated organism —
never by brute force.

### 1.2 The "Meta" Pitch

*Vinagre: Matilha* is the engine's proof that intelligence can be
distributed across many cheap agents instead of one expensive one.

* **The Pack Blackboard** represents **Shared Mutable State**: many
  concurrent readers and writers agreeing on one source of truth
  (threat location, flanker assignments, retreat thresholds) without
  stepping on each other.
* **The Flow Field** represents **Coordinated Pathing at Scale**: one
  scalar field solve standing in for twelve individual pathfinding
  requests, recomputed only when the target moves.
* **The Alpha's Signal** represents the **Command Pattern**: a single
  player intent (Scatter, Pincer, Distract) that many independent
  behavior trees subscribe to and reinterpret locally.

---

## 2. Gameplay Mechanics

### 2.1 Core Loop: "Flush and Encircle"

1. **Scout:** The pack spreads across riverbeds and shoals, separation
   keeping members from clumping while cohesion keeps them a pack, not a
   scatter.
2. **Signal:** The alpha issues **Scatter**, **Pincer Attack**, or
   **Distract**, writing intent to the Pack Blackboard.
3. **Encircle:** Flanker dogs read the flow field toward the assigned
   approach vector; `CirclePrey` and `IsFlankingTarget` behavior tree
   nodes bias their steering into an orbit around the target instead of
   a straight chase.
4. **Corner:** Group steering cuts the jaguar's escape routes. Cornering
   it against a pack-weighted obstacle (a log, a narrows) ends the
   encounter.

### 2.2 Pack Roles & Controls

* **Vanguard** (Player 1 in co-op, or the alpha in solo): direct pursuit
  line, the dog(s) the player steers by hand.
* **Flankers** (Player 2 in co-op, autonomous in solo): never
  directly steered — the player issues group commands and the
  behavior trees resolve individual movement off the shared blackboard.
* **Solo mode:** the player drives the alpha; flankers run entirely off
  blackboard threat data and last-issued command.
* **Co-op mode:** dual-stick local co-op via `pyguara.input.coop` —
  Player 1 owns the Vanguard's `InputManager` context, Player 2 owns the
  Flankers' command context, resolved concurrently each frame.

### 2.3 Threats & Obstacles

* **Onça-pintada (jaguar):** a larger predator with its own behavior
  tree, reading the same blackboard shape (threat/retreat thresholds)
  from the opposite side — it disengages once its own health/exposure
  crosses a threshold, same as the pack would.
* **Water current zones:** slow standard movement; bush dogs carry a
  `WebbedFeet` component that negates the penalty, so currents become a
  routing decision, not a hazard, once the player understands it.
* **Pack-weighted pressure plates:** require **N** dogs standing
  simultaneously to lower a log or open a passage — a coordination
  puzzle layered on top of the combat loop.
* **Isolation risk:** a dog cut off from the pack loses cohesion buffs
  and becomes vulnerable alone, reinforcing the "hyper-social" premise
  mechanically, not just thematically.

---

## 3. Visual & Audio Aesthetic

### 3.1 Art Style: "Riverbed Silhouette"

Following the cover key art: warm Cerrado browns and jungle greens for
the pack and terrain, teal-blue for water and shoals, with the jaguar
rendered against a faint bioluminescent green haze — a visual stand-in
for the blackboard's threat marker made diegetic.

* **Pack:** earthy browns/oranges; the Vanguard wears a **Guará Orange**
  collar marker, Flankers tint slightly cooler so formation reads at a
  glance mid-encirclement.
* **Water:** teal-blue current zones with visible flow-direction ripple
  particles — the same vector field driving AI movement, exposed to the
  player as a readable current.
* **Predator:** the jaguar carries a subtle green scent-glow while
  "marked" by the pack's shared threat state, fading once it breaks
  line of sight.

### 3.2 Audio Direction

* **Music:** layered percussion — a new layer joins per pack member
  actively engaged in the pursuit, so the mix itself communicates pack
  commitment.
* **SFX:** a distinct bark per issued command (Scatter / Pincer /
  Distract), a rising snarl chorus on `CallReinforcements`, and a
  splash/current audio cue at water crossings.

---

## 4. Technical Implementation Specifications

This is the reason the demo exists: each subsystem below is exercised by
a real gameplay mechanic above, not bolted on for coverage.

### 4.1 AI Steering & Flow Fields (`pyguara.ai.steering`, `pyguara.ai.pathfinding.flow_field`)

* Cohesion, alignment, and separation are summed per dog against its
  5-11 packmates, tuned so separation dominates at close range —
  the failure mode this demo has to avoid is visible jitter when the
  flow field's pull and neighbor separation disagree.
* The flow field is recomputed on target change (new prey position, new
  pincer point) rather than per-agent, so a 12-agent pack costs one
  field solve per retarget, not twelve pathfinding queries.
* Land/water cost differences are baked into the field so dogs
  naturally route around currents unless `WebbedFeet` removes the
  penalty for that agent.

### 4.2 Shared Behavior Trees & Blackboard (`pyguara.ai.behavior_tree`, `pyguara.ai.blackboard`)

* **Pack Blackboard** fields: `threat_position`,
  `flanker_assignments` (dog id → approach vector), `retreat_threshold`,
  `reinforcement_requested`.
* **Tree nodes:** `IsFlankingTarget` (compares assigned vector against
  current heading), `CirclePrey` (wraps the flow field with an orbit
  bias), `CallReinforcements` (writes `reinforcement_requested`, which
  other dogs' selectors react to on their next tick).
* **Validates:** up to twelve independent behavior tree instances
  safely reading and writing one shared blackboard within a single
  synchronous tick, with no read/write ordering bugs.

### 4.3 Local Co-op & Input Manager (`pyguara.input.coop`, `pyguara.input.manager`)

* Two `InputManager` binding contexts resolved in the same frame:
  Player 1 bound to direct Vanguard movement, Player 2 bound to
  Flanker group commands.
* Validates that `pyguara.input.coop` can route two independent local
  players into the same scene without one context starving the other.

### 4.4 Physics Trigger Volumes & Solid System (`pyguara.physics.trigger_volume`, `pyguara.physics.solid_system`)

* Water currents are `TriggerVolume`s applying a velocity modifier,
  gated per-entity on `WebbedFeet` presence.
* Pack-weighted pressure plates are `TriggerVolume`s that count
  simultaneous occupants and, above N, release a `Solid` (the log)
  through `pyguara.physics.solid_system` rather than teleporting or
  disabling collision outright.

---

## 5. Level Design: "The Riverbed Chain"

**Level Name:** `matilha_riverbed.py`

1. **Stage 1: Sandbar Drill (Tutorial)** — a small pack of 4 on flat
   riverbank. Teaches Scatter/Pincer commands and following the flow
   field with no water hazards yet.
2. **Stage 2: The Braided Channel** — multiple water crossings force the
   pack to split and rejoin; `WebbedFeet` routing becomes load-bearing,
   not optional.
3. **Stage 3: The Jaguar's Bend** — full 12-dog pack, a pressure-plate
   log gate requiring 4 simultaneous dogs, cornering the jaguar at a
   dead-end oxbow.

---

## 6. Asset Requirements Checklist

**Sprites:**

* [ ] `spr_dog_run`, `spr_dog_idle`: shared cycle, role-tinted
      (Vanguard / Flanker) at render time.
* [ ] `spr_jaguar_stalk`, `spr_jaguar_retreat`, `spr_jaguar_lunge`.
* [ ] `spr_log_gate`: closed/open states for the pressure-plate puzzle.
* [ ] `fx_current_ripple`: directional particle matching the flow
      field's local vector.

**Audio:**

* [ ] `bark_scatter.wav`, `bark_pincer.wav`, `bark_distract.wav`.
* [ ] `snarl_reinforcements.wav`.
* [ ] `ambient_river_loop.ogg`.
* [ ] `bgm_pursuit_layer_{1..4}.ogg` (one per engaged pack member).
