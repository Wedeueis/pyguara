# Rendering Pipeline

PyGuara employs a modern, backend-agnostic rendering architecture located in `pyguara.graphics`.

## Core Pipeline

The rendering process is split into distinct stages to maximize performance and flexibility:

1.  **Submission**: Entities submit `Renderable` items to the `RenderSystem`.
2.  **Queueing**: Items are stored in a `RenderQueue`.
3.  **Sorting**: The queue is sorted by Layer and Z-Index (Painter's Algorithm).
4.  **Batching**: The `Batcher` groups compatible draw calls (same texture) into `RenderBatch` objects.
5.  **Execution**: The backend (e.g., `PygameBackend`) executes the batches.

## Components

### Camera2D
Handles Coordinate Transformation (World Space <-> Screen Space). Supports Zoom, Rotation, and Panning.

### Viewport
Defines the drawable region on the screen. Used for:
- Split-screen multiplayer.
- Minimaps.
- Aspect ratio enforcement (Letterboxing).

### Geometry
Procedural shapes (`Box`, `Circle`) that lazy-generate their textures. This allows them to be batched alongside standard sprites.

## Backends

The engine uses the `IRenderer` protocol, allowing for different implementations:
- **PygameBackend**: Uses `pygame-ce` for rendering. Optimized with `blits` for batching.
- **HeadlessBackend**: Discards draw calls. Useful for CI/CD and server-side simulation.

---

# UI System

The UI system (`pyguara.ui`) is immediate-mode friendly but retains state via an Object-Oriented widget tree.

## Architecture
- **UIManager**: Routes input events (`OnMouseEvent`) to widgets.
- **UIElement**: Base class for all widgets (`Button`, `Panel`, `Label`).
- **Layouts**: `BoxContainer` handles automatic positioning (Vertical/Horizontal).
- **Theme**: A centralized `UITheme` controls colors and spacing.

## Integration
The UI is rendered via the `UIRenderer` protocol, allowing it to sit on top of the main game render pass.
