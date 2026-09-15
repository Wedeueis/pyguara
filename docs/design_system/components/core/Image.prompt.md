Image draws a sprite or texture; it defaults to `image-rendering: pixelated` so pixel art stays crisp at any scale.

```jsx
<Image src="assets/art/hero-guara.png" width={128} alt="Guará idle" />
```

Pass `tint` for the engine's multiply tint (damage flashes, disabled icons). Set `pixelated={false}` only for photographic imagery.
