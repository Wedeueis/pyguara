# Engine & Editor Comprehensive Audit - January 8, 2026

## 1. Executive Summary

**PyGuara** is structured as an "enterprise-grade" 2D game engine, positioning itself uniquely in the Python ecosystem. It rejects the unstructured nature of raw frameworks (Pygame) in favor of a strict **Entity-Component-System (ECS)** and **Dependency Injection (DI)** architecture.

*   **Architecture Grade:** A- (S-tier Core, B-tier Rendering/Scene wiring).
*   **Editor Grade:** C+ (Functional Debugger, not yet a Level Editor).
*   **Verdict:** The foundation is exceptionally robust for a Python engine, prioritizing maintainability and decoupling. The primary risks are currently in the Rendering Pipeline's abstraction leakage and the Editor's isolation from the Resource system.

---

## 2. Engine Architecture Review

### 2.1 Strengths
*   **Dependency Injection (`pyguara.di`):**
    *   **Verdict:** Excellent and rare in game dev.
    *   **Details:** Full IOC container with scoped lifetimes. Auto-wiring via `inspect` and type hints significantly reduces initialization boilerplate.
*   **ECS Core (`pyguara.ecs`):**
    *   **Verdict:** Pythonic & Optimized.
    *   **Details:** Correctly chooses Inverted Indexes (Sets) over Array-of-Structs, ensuring $O(K)$ query performance which is optimal for Python's memory model.
*   **Event System (`pyguara.events`):**
    *   **Verdict:** Thread-safe and robust.
    *   **Details:** The separation of immediate `dispatch()` and deferred `queue_event()` prevents race conditions and allows safe background loading.
*   **Physics Bridge (`pyguara.physics`):**
    *   **Verdict:** Architecturally correct.
    *   **Details:** Correctly manages the "Ownership of Transform" problem. Kinematic bodies are driven by ECS; Dynamic bodies drive the ECS.

### 2.2 Critical Vulnerabilities
*   **Rendering Pipeline Conflation:**
    *   **Issue:** `Application.py` injects a `UIRenderer` and passes it to Scenes, which use it for *everything*.
    *   **Impact:** There is no distinction between "World Rendering" (Cameras, Layers, Sorting) and "UI Rendering" (Screen Space). This forces Scenes to render game entities via a UI interface.
*   **Loose Component Typing:**
    *   **Issue:** Components are plain Python classes.
    *   **Risk:** Users can accidentally put logic into Components, violating ECS purity. There is no enforcement of "Data-Only" semantics.

---

## 3. Editor Implementation Review

### 3.1 Status: "Debugger" vs "Editor"
The current tool is a **Runtime Inspector**, not a Level Editor. It is excellent for tweaking values in memory but lacks the feedback loop to save those changes to disk.

### 3.2 Strengths
*   **Tool Integration:** The `EditorTool` correctly hooks into the `ToolManager`. It handles input consumption (`io.want_capture_mouse`) properly, preventing clicks from bleeding into the game world.
*   **Resilience:** Gracefully degrades if `imgui` is missing, allowing production builds to run without the editor overhead.

### 3.3 Weaknesses
*   **Reflection Strategy:** The Inspector iterates `component.__dict__`. This is brittle and will break if optimizations like `__slots__` are introduced.
*   **Hierarchy Readability:** Entities are listed by UUID. Without a `Tag` or `Name` component, the list is human-unreadable.
*   **Missing Core Features:**
    *   **No Serialization:** The "Save" button is a placeholder.
    *   **No Gizmos:** No visual handles for moving objects in the scene view.

---

## 4. Integration Gap Analysis

There is a significant disconnect between the **Editor** and the **Resource System**.

*   **The Silo:** `DataResource` (in `resources/data.py`) handles JSON loading, and the Editor handles runtime objects. There is no bridge.
*   **Missing Workflow:**
    *   You cannot drag a `DataResource` (JSON) into the Scene to instantiate it.
    *   Editing an entity in the Inspector does not update the source `DataResource`.
    *   There is no "Prefab" concept exposed to the user.

---

## 5. Detailed Improvement Plan

### Phase 1: Architectural Corrections (Core Stability)
*Goal: Fix the rendering pipeline and enforce ECS strictness.*

- [ ] **Split Rendering Interfaces:**
    *   Update `Application` to maintain both `WorldRenderer` and `UIRenderer`.
    *   Refactor `Scene.render` signature: `def render(self, world: WorldRenderer, ui: UIRenderer) -> None:`
- [ ] **Enforce Data Components:**
    *   Add a meta-check or base class `Component` that validates subclasses are `dataclasses` or `pydantic` models.
    *   (Optional) Use `__slots__` for memory optimization, which necessitates Phase 2 changes.

### Phase 2: Editor Maturation (Usability)
*Goal: Make the editor usable for level design, not just debugging.*

- [ ] **Robust Inspection:**
    *   Refactor `InspectorPanel` to use `dataclasses.fields()` instead of `__dict__`. This supports `__slots__` and provides strict typing info.
    *   Create a `TypeDrawer` registry to handle complex types (Enums, Lists) instead of a hardcoded `if/elif` chain.
- [ ] **Hierarchy UX:**
    *   Implement a `TagComponent` (e.g., `name="Player"`).
    *   Update `HierarchyPanel` to display Name > ID.
- [ ] **Serialization Loop:**
    *   Implement `SceneSerializer` to dump the current ECS state to JSON.
    *   Wire the "Save" button to this serializer.

### Phase 3: Ecosystem Unification (The "Engine" Feel)
*Goal: Bridge Resources and Editor.*

- [ ] **Resource Panel:**
    *   Create a generic UI panel that lists files from `ResourceManager`.
    *   Allow inspection of raw `DataResource` dictionaries.
- [ ] **Source Linking:**
    *   Add a `_source_resource` reference to Entities spawned from data.
    *   Add a "Save to Source" button in the Inspector to push changes back to the JSON file.
- [ ] **Drag-and-Drop Spawning:**
    *   Implement drag logic from Resource Panel -> Scene View to trigger `ResourceManager.spawn(data)`.
