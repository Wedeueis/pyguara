# Future Backlog & Roadmap

This directory serves as the registry for long-term project vision, technical debt cleanup, and educational content planning for the PyGuara engine.

## 📂 Registry

### 1. Systems & Architecture
**File:** [`systems_improvement.md`](./systems_improvement.md)

Focuses on major architectural evolutions to improve performance, scalability, and data-driven capabilities.

*   **ECS Archetypes:** Transition from inverted indexes to contiguous arrays for CPU cache locality.
*   **Schema Migrations:** Versioned serialization pipeline for save game compatibility.
*   **Data-Driven Prefabs:** JSON/YAML entity definitions to replace hardcoded setup.
*   **Input Persistence:** Export/Import bindings and conflict resolution.
*   **Determinism:** Ordered iteration and input recording for replay systems.
*   **Hot-Reloading:** Dynamic reloading of System logic during runtime.
*   **Audio Instances:** Component-based audio sources tied to entity lifecycle.

### 2. Technical Debt & Polish
**File:** [`technical_debt_cleanup.md`](./technical_debt_cleanup.md)

Addresses specific low/medium priority issues identified during the Beta assessment (PEP-2026.01).

*   **Shape Rendering:** Native shape support in ModernGL backend.
*   **Serialization:** MessagePack implementation for efficient binary saves.
*   **Component Registry:** Dynamic registration to replace hardcoded lists.
*   **Editor:** Command pattern implementation for Undo/Redo.
*   **Concurrency:** Thread-safety verification suite.
*   **Audio Effects:** 3D spatialization features and DSP effects chain.

### 3. Education & Content
**File:** [`tutorial_series_raodmap.md`](./tutorial_series_raodmap.md)

Detailed plan for user onboarding and feature showcase games.

*   **Phase 1 (Foundations):** Boot process, ECS mental model, Asset pipeline.
*   **Phase 2 (Core Systems):** Input events, Physics integration, UI & Scene graph.
*   **Phase 3 (Capstone Demos):**
    *   *True Coral* (Puzzle)
    *   *Guará & Falcão* (Platformer)
    *   *Protocolo Bandeira* (Shooter)

---

## 🏷️ Legend

*   **P1 (High):** Critical for post-beta stability or performance.
*   **P2 (Medium):** Important features for production usage.
*   **P3 (Low):** Nice-to-have enhancements or niche features.
