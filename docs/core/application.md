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

The engine provides a centralized exception hierarchy in `pyguara.error`.

- **EngineException**: Base class for all engine errors.
- **Categories**: Errors are categorized (Graphics, Assets, Physics) for easier debugging.
- **Safe Execution**: Decorators like `@safe_execute` and `@retry` help manage instability in IO operations.
