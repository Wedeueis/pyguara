# Refactoring Plan: Logging Standardization (P2-012)

## 1. Context & Motivation
The codebase currently relies on `print()` statements for diagnostic output. This is a bad practice for a game engine because:
- It cannot be disabled/filtered in production.
- It lacks metadata (timestamps, log levels, module names).
- It clutters standard output (stdout).

We need to implement a structured **Logging System** using Python's `logging` module.

## 2. Implementation Strategy

### Phase A: Infrastructure (pyguara.log)
1.  **Create `pyguara/log/config.py`**:
    -   Define a `setup_logging(level: int = logging.INFO)` function.
    -   Configure a `StreamHandler` with a clean formatter: `[%(levelname)s] [%(name)s] %(message)s`.
    -   (Optional) Configure a `FileHandler` for `game.log`.

### Phase B: Domain Refactoring
Iterate through each domain and replace `print()` with `logger.level()`.

#### 1. Audio Domain (`pyguara/audio/manager.py`)
-   **Current**: `print(f"[AudioManager] Failed to load...")`
-   **Change**:
    ```python
    import logging
    logger = logging.getLogger(__name__)
    ...
    logger.error("Failed to load audio clip '%s'", path, exc_info=True)
    logger.warning("No resource manager available...")
    ```

#### 2. Input Domain (`pyguara/input/manager.py`)
-   **Current**: `print(f"Controller detected: ...")`
-   **Change**: `logger.info("Controller detected: %s", joy.get_name())`

#### 3. Resource Domain (`pyguara/resources/manager.py`)
-   **Current**: `print(f"[ResourceManager] Loading {actual_path}...")`
-   **Change**:
    -   `Loading...` -> `logger.debug("Loading resource: %s", actual_path)` (Level: DEBUG)
    -   `Unloaded...` -> `logger.debug("Unloaded resource: %s", actual_path)` (Level: DEBUG)
    -   `Warning...` -> `logger.warning("Directory %s does not exist", root_path)`

### Phase C: Missing Logs (New Instrumentation)
Identify critical silent failure points and add logs.

#### 1. Graphics (`pyguara/graphics/pipeline/render_system.py`)
-   **Add**: `logger.info("Initializing RenderSystem with backend: %s", type(backend).__name__)` in `__init__`.

#### 2. Scene (`pyguara/scene/manager.py`)
-   **Add**: `logger.info("Switching to scene: %s", scene_name)` in `switch_to`.
-   **Add**: `logger.debug("Scene transition complete")` in transition callback.

#### 3. AI (`pyguara/ai/ai_system.py`)
-   **Add**: `logger.warning("AI Component enabled but missing FSM/Tree for entity %s", entity.id)`

## 3. Log Levels Guide

| Level | Usage |
| :--- | :--- |
| **ERROR** | Function failed, game may be unstable (Exception caught). |
| **WARNING** | Function completed but something was wrong (Missing file, fallback used). |
| **INFO** | Major lifecycle events (Scene switch, Controller connected, System init). |
| **DEBUG** | High-frequency detail (Resource load/unload, Event dispatch). |
| **TRACE** | (Not used in stdlib, map to DEBUG 5) Per-frame data (Physics step). |

## 4. Acceptance Criteria
- [x] No `print()` calls in the library code (`pyguara/`).
  - Remaining print statements are only in:
    - CLI tools (atlas_generator.py) - appropriate for user-facing output
    - Docstring examples - documentation only
- [x] Running `make play` shows clean INFO logs (Scene switch, Controller detect).
- [x] Running `make play --debug` shows resource loading details.
- [x] Errors (missing files) include tracebacks in the log.
