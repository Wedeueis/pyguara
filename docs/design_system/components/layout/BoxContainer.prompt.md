BoxContainer stacks children in a row or column with fixed spacing — it is what every menu column and toolbar row in the engine is built from.

```jsx
<BoxContainer direction="VERTICAL" align="CENTER" spacing={12}>
  <Button text="Play" variant="metal" size="large" />
  <Button text="Options" variant="wood" size="large" />
  <Button text="Quit" variant="wood" size="large" />
<\/BoxContainer>
```

There is no grid or flex-grow model in the engine — nest BoxContainers instead.
