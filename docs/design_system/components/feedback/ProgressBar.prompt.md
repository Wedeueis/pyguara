ProgressBar is the system's only meter — HUD health and stamina, asset-import progress, level load.

```jsx
<ProgressBar value={0.68} fillColor="var(--state-danger)" label="68%" />
```

Colour the fill semantically: `--state-danger` for health, `--state-warn` for stamina, `--action-secondary` (the engine default) for neutral progress.
