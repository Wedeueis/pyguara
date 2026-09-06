# Application Lifecycle

The `pyguara.application` package manages the main game loop, initialization, and shutdown sequences.

## The Application Class

The `Application` class (`pyguara/application/application.py`) is the runtime coordinator. It is responsible for:

1.  **Dependency Resolution**: Retrieving core systems (Window, Input, SceneManager) from the DI Container.
2.  **Main Loop**:
    - `Time.tick()`
    - `Input.process()`
    - `Update()` (Logic & Physics)
    - `Render()`

## Bootstrapping

The entry point is managed by `create_application()` in `bootstrap.py`. This implementation of the **Composition Root** pattern ensures that all dependencies are wired *before* the game starts.

```python
def create_application() -> Application:
    container = DIContainer()
    # ... register services ...
    return Application(container)
```

## Configuration

Configuration is managed by `ConfigManager` (`pyguara/config`), which handles:
- **Loading/Saving**: JSON serialization.
- **Validation**: Rules checking (e.g., "Screen width must be > 640").
- **Events**: Dispatches `OnConfigurationChanged` when settings are modified.

---

# Error Handling

Subsystems that run user-supplied callbacks share one policy for what happens
when that code raises, defined in `pyguara.errors`:

```python
from pyguara.errors import ErrorHandlingStrategy

EventDispatcher(error_strategy=ErrorHandlingStrategy.LOG)
DIContainer(error_strategy=ErrorHandlingStrategy.LOG)
```

- **`RAISE`** (default): log, then re-raise. Fail fast during development.
- **`LOG`**: log and carry on. Graceful degradation in production.
- **`IGNORE`**: swallow silently. Tests and narrow edge cases only.

`EventDispatcher` applies this to both handlers and their filters;
`DIContainer` applies it to constructor introspection failures.
