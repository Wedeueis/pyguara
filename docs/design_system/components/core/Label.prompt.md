Label renders static text at one of the engine's four font sizes — use it for every non-interactive string in a HUD, menu, or editor panel.

```jsx
<Label text="GUARÁ & FALCÃO" font="display" fontSize={32} color="var(--action-secondary)" />
```

Use `font="display"` for short titles only (Press Start 2P is unreadable in runs), `font="pixel"` for UI strings, `font="body"` for prose, `font="mono"` for code and numeric readouts.
