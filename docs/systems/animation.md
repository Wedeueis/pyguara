# Animation System

The Animation system (`pyguara.animation`) provides powerful tweening capabilities for smooth state transitions.

## Tweening

The `Tween` class allows you to animate any numeric property (float or tuple of floats) over time using easing functions.

### Features

*   **Flexible Targets**: Animate `Vector2`, `Color`, or simple `float` values.
*   **Easing Functions**: Includes standard easings (Linear, EaseInQuad, EaseOutBounce, etc.).
*   **Lifecycle Control**: Start, Pause, Resume, Stop, and Loop animations.
*   **Yoyo Mode**: Automatically reverse animation on loop.
*   **Callbacks**: `on_update` and `on_complete` hooks.

### Usage

```python
from pyguara.animation.tween import Tween, TweenManager
from pyguara.animation.easing import EasingType

# Create a tween
tween = Tween(
    start_value=Vector2(0, 0),
    end_value=Vector2(100, 100),
    duration=1.0,
    easing=EasingType.EASE_OUT_QUAD,
    loops=-1,  # Infinite
    yoyo=True  # Ping-pong
)

# Register with manager (usually injected)
tween_manager.add(tween)
tween.start()
```

## Integration

The `TweenManager` should be updated every frame. In a standard setup, this is handled automatically by the `AnimationSystem`.
