# UI kit — Pyguara Engine Editor

A recreation of the engine's own ImGui editor, read from source rather than from screenshots.

## What it is built from
| Screen region | Source file |
| --- | --- |
| Menu bar (File / View, Ctrl+S, Ctrl+L) | `pyguara/editor/layer.py` |
| Hierarchy panel (tag + id[:8] labels, selection) | `pyguara/editor/panels/hierarchy.py` |
| Inspector (entity id, ResourceLink source, Save to Source Asset, per-component collapsing headers) | `pyguara/editor/panels/inspector.py`, `pyguara/editor/drawers.py` |
| Assets panel (Registry + Cache (Loaded)) and Resource Inspector window (Save to Disk / Spawn into Scene) | `pyguara/editor/panels/assets.py` |
| Performance monitor (150×60, green border, red under 30 fps) | `pyguara/tools/performance.py` |
| Shortcuts panel (F1–F12 map, yellow heading, green keys) | `pyguara/tools/shortcuts_panel.py` |
| Physics debug colours | `pyguara/common/palette.py` |
| Field widget mapping (bool→checkbox, float→drag, str→input) | `pyguara/editor/panels/assets.py` `_draw_dict_editor` |

## Interactions
- Click any entity in **Hierarchy** — Inspector rebuilds from that entity's components.
- Collapse/expand component headers; filter the entity list.
- Click a cached resource in **Assets** — the Resource Inspector window opens bottom-right.
- **Tools** menu, or the real F-keys: F1 performance, F3 event monitor, F4 physics debugger, F8 shortcuts, F12 toggles all.
- **Day / Dusk** in the top right switches the earthy light and dark themes.

## Deliberate difference from source
The engine's editor renders through ImGui's default dark style with two colour overrides
(`COLOR_WINDOW_BACKGROUND` 0.1/0.1/0.1/0.95 and `COLOR_TITLE_BACKGROUND_ACTIVE` 0.2/0.3/0.4).
This kit restyles that chrome into the Cerrado palette because the brief asked for an earthy
editor in both light and dark. Layout, panel names, field order and copy are unchanged.
