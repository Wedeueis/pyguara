# Editor & Tooling Review - January 9, 2026

## Executive Summary
A deep-dive review of the `pyguara.editor` and `pyguara.tools` packages reveals a robust "Dual-Layer" architecture. However, the coexistence of legacy debug tools and the new ImGui editor creates redundancy. Additionally, the new "Live-Link" features, while powerful, lack safety mechanisms.

## 1. Identified Improvements

### 1.1 Redundancy Consolidation
- **Observation:** Two inspector implementations exist:
    1.  `EntityInspector` (`pyguara.tools.inspector`): Native Pygame implementation.
    2.  `InspectorPanel` (`pyguara.editor.panels.inspector`): ImGui implementation.
- **Risk:** High maintenance burden. Changes to the Component architecture must be patched in two places.
- **Recommendation:**
    - Deprecate `EntityInspector` as an interactive tool.
    - Replace it with a read-only **"Stats Overlay"** that shows high-level metrics (Entity Count, FPS, Memory) rather than per-component details.

### 1.2 Data Safety Mechanisms
- **Observation:** The `InspectorPanel._save_entity_to_source` method writes directly to the source JSON file.
- **Risk:** "Destructive Save." If a designer accidentally saves a broken state or the write fails midway, the asset is lost.
- **Action Items:**
    - **Validation:** Validate the data against a schema (if available) before writing.
    - **Atomic Writes:** Write to a temp file first, then rename.
    - **Versioning:** Create a backup (`.bak`) of the resource file before overwriting.

### 1.3 Visual Editing Tools (Gizmos)
- **Observation:** The editor allows value tweaking but lacks visual manipulation in the viewport.
- **Action Items:**
    - Implement a **Gizmo System** using `UIRenderer` (lines/circles).
    - Support **Transform Handles** (Translation, Rotation, Scale) that intercept mouse input before it reaches the game world.

### 1.4 Serialization Robustness
- **Observation:** `SceneSerializer` is critical for the "Save Scene" workflow.
- **Risk:** Python object references (outside of simple primitives) may break during serialization/deserialization cycles.
- **Action Items:**
    - Audit `SceneSerializer` for handling of complex types (tuples, enums, nested dataclasses).
    - Ensure circular references do not cause recursion errors.
