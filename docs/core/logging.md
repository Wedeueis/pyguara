# Logging System

PyGuara provides a centralized logging configuration (`pyguara.log`) wrapping Python's standard `logging` module. This ensures consistent log formatting, levels, and output destinations.

## Setup

Logging is initialized via `setup_logging` in `bootstrap.py`.

```python
from pyguara.log.config import setup_logging
import logging

# Configure console output and optional file output
setup_logging(
    level=logging.INFO,
    log_file="game.log",
    file_level=logging.DEBUG
)
```

## Usage

In any module, retrieve a namespaced logger:

```python
from pyguara.log.config import get_logger

logger = get_logger(__name__)

def my_function():
    logger.info("Function started")
    try:
        # ... logic ...
    except Exception:
        logger.error("Critical failure", exc_info=True)
```

## Best Practices

*   **Avoid `print()`**: Always use the logger.
*   **Levels**:
    *   `DEBUG`: High-frequency data (resource loads, events).
    *   `INFO`: Lifecycle events (startup, scene switch).
    *   `WARNING`: Recoverable issues (missing texture fallback).
    *   `ERROR`: Exceptions and failures.
