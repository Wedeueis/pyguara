NavBar is the top chrome for any full screen — the editor menu bar, the docs header, the marketing site header.

```jsx
<NavBar brand={<Image src="assets/art/badge-pyguara-mark.png" height={34} />}>
  <Button text="File" variant="ghost" size="small" />
  <Button text="View" variant="ghost" size="small" />
<\/NavBar>
```

It renders no dropdown behaviour of its own — the engine's version is a layout container plus a background, so compose Buttons inside it.
