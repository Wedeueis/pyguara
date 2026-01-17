# Scripting System

PyGuara utilizes Python **Coroutines** (`pyguara.scripting`) to enable sequential, time-based game logic without the complexity of state machines or callback hell. This is similar to Unity's Coroutines.

## Concepts

*   **Coroutine**: A Python generator function that `yields` control back to the engine.
*   **WaitInstruction**: Objects yielded to control timing (`WaitForSeconds`, `WaitUntil`).
*   **CoroutineManager**: Manages the execution and lifecycle of active coroutines.

## Wait Instructions

*   `WaitForSeconds(duration)`: Pause execution for `duration` seconds.
*   `WaitUntil(predicate)`: Pause until `predicate()` returns True.
*   `WaitWhile(predicate)`: Pause while `predicate()` returns True.

## Usage

```python
from pyguara.scripting.coroutines import wait_for_seconds

def scripted_sequence():
    print("Sequence started")

    # Wait for 2 seconds
    yield wait_for_seconds(2.0)

    print("2 seconds passed, spawning enemies...")
    spawn_enemies()

    # Wait until all enemies are defeated
    yield wait_until(lambda: get_enemy_count() == 0)

    print("Wave cleared!")

# Start the coroutine
coroutine_manager.start_coroutine(scripted_sequence())
```
