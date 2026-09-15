Slider sets a continuous value — audio volume in options screens, and float fields in the editor inspector.

```jsx
<Slider value={vol} min={0} max={1} showValue onChange={setVol} />
```

The knob is round even though everything else in the system has square corners — that is the engine's own `draw_circle` call, so keep it.
