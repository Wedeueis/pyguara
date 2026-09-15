TextInput is the only text entry control — save-file names, entity tags, and editor string fields.

```jsx
<TextInput value={tag} placeholder="entity tag" onChange={setTag} />
```

Use `mono` for resource paths and ids. The engine's 32-character cap is the default; raise `maxLength` deliberately.
