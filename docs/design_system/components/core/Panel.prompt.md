Panel is the base container surface — use it wherever a region needs a background and a border, including as the backdrop for HUD groups and editor panels.

```jsx
<Panel bevel padding="var(--space-5)">
  <Label text="Inventory" fontSize={24} />
<\/Panel>
```

Variants: `borderWidth` (1 default, 2 for framed game panels, 3 for high-contrast), `bevel` for the stamped pixel look, `color` to override the fill.
