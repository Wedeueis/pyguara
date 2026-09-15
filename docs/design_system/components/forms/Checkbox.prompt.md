Checkbox is the toggle for options screens and editor inspectors — there is no separate Switch component in this system.

```jsx
<Checkbox label="Fullscreen" checked={full} onChange={setFull} />
```

The box size (20px) and inner mark (10px) are fixed by the engine; don't scale them.
