Button is the only clickable primitive in the system — use it for menu entries, editor toolbar actions and dialog confirmations alike.

```jsx
<Button text="Play" variant="sage" size="large" onClick={start} />
```

Skins: `primary` (Guará red) for the single main action per screen, `secondary` (ochre) for supporting actions, `ghost` for toolbars, and `wood`/`sage` for in-world menu plates. States: `disabled`, `focused` (gamepad/keyboard selection).
