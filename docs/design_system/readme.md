# Pyguara Design System

A design system for **Pyguara** — an open-source, data-driven 2D game engine written in Python on
top of pygame and pymunk — and for **Guará & Falcão: A Platformer Adventure**, the pixel-art
platformer built with it.

Two products, one visual language:

| Product | What it is | Surface |
| --- | --- | --- |
| **Pyguara Engine** | ECS, data-driven, event-driven 2D engine. Ships a DI container, physics, scene serialization, hot reload, an ImGui editor and an F-key developer tool suite. | `ui_kits/editor/`, `ui_kits/docs/` |
| **Guará & Falcão** | A platformer set in the Brazilian Cerrado. A maned wolf (*lobo-guará*) runs; a falcon rides on his back. Beneath the tableland, old machinery is still turning — greened over, repaired, kept alive. | `ui_kits/game/`, `ui_kits/site/`, `ui_kits/store/` |

The engine is generic and knows nothing about the game. The game supplies the warmth; the engine
supplies the structure. Both halves show up in the palette — Cerrado ochres and Guará red against
sage and colonial green.

---

## Sources this system was built from

Read these directly if you have access — they are the ground truth, and this document is a
lossy summary of them.

- **Codebase** — the `pyguara` Python package, attached as a local folder. Everything in
  `tokens/` and `components/` was lifted from it, chiefly:
  - `pyguara/ui/types.py` — `ColorScheme`, `SpacingScheme`, `FontScheme`, `BorderScheme`,
    `ShadowScheme`, `UIElementState`, `UIAnchor`, `LayoutDirection`, `LayoutAlignment`, `UIEventType`
  - `pyguara/ui/theme.py`, `pyguara/ui/theme_presets.py` — the theme model and its six presets
  - `pyguara/ui/components/*.py` — the component inventory and every fixed pixel dimension
  - `pyguara/ui/layout.py` — `BoxContainer`
  - `pyguara/editor/layer.py`, `pyguara/editor/panels/*.py` — the editor
  - `pyguara/tools/*.py` — the developer tool overlays
  - `pyguara/common/palette.py` — `BasicColors`, `DebugColors`
  - `pyguara/graphics/ninepatch.py` — scalable UI frame metrics
- **GitHub repository** — <https://github.com/Wedeueis/pyguara>. The user named this repo as the
  source. It was **not** read over the network (GitHub was not connected in this session); the
  attached local folder was read instead. Explore the repository yourself to do a better job of
  building designs against this product — the Python source is far richer than this summary.
- **Art (current)** — `uploads/Gemini_Generated_Image_5sk5055sk5055sk5.png`, the solarpunk key art:
  amber sky, carved Art Nouveau sign lockup, Guará with pack and Falcão riding, solar leaf panels,
  water spouts and basins, plank platforms, fruit, floating soil. **This is the ground truth for
  colour and style** and it supersedes the earlier sheet. Cropped into `assets/art/`.
- **Art (superseded)** — `uploads/pyguara_platformer_spritesheet.jpg`, the earlier pixel sheet with
  oxidised-metal menu plates and gears. Only `keycaps.png` is still used from it; the rest of
  `assets/sprites/` is legacy and should not be used in new work.
- `uploads/pyguara_mascot.png` (the flat mascot mark).

No Figma file, no slide deck and no marketing material were provided.

---

## Content fundamentals

The engine's own voice is the only written voice the sources contain, and it is unusually
consistent — every module has a docstring and every docstring follows the same shape.

**Voice: a précis, then the mechanism.** One declarative sentence saying what the thing is, then
how it behaves. No preamble, no benefit claims.

> `"""Visualizes progress 0.0 to 1.0."""`
> `"""Clickable button with state styling."""`
> `"""Horizontal bar typically at the top of a screen. Combines a Panel background with a horizontal layout."""`
> `"""A generic container for custom drawing. Useful for mini-maps, model previews, or custom graphs."""`

**Rules observed in the source:**

- **Sentence case throughout.** Headings, labels, docstrings. The only uppercase is in constants
  (`DARK`, `COLLIDER_ACTIVE`) and in pixel-art UI, where Silkscreen and Press Start 2P read better
  in caps — so buttons render `PLAY`, `OPTIONS`, `QUIT` while their source text is `"Play"`.
- **Second person for instructions, none for descriptions.** `"Retrieve the current active theme."`
  describes; `"To customize, clone and modify"` instructs. First person never appears.
- **Imperative mood for actions.** `Save to Source Asset`, `Spawn into Scene`, `Save to Disk`,
  `Press F8 to Close`. Never *"Click here to…"*.
- **No emoji anywhere.** Not in code, comments, panel titles or labels. Do not introduce them.
- **No exclamation marks.** The engine never raises its voice; neither should product copy.
- **Numbers are exact and typed.** `0.0 to 1.0`, `12 / 16 / 24 / 32`, `mass: 12.0`. Floats keep
  their decimal. Never *"about"*, never rounded for tidiness.
- **Uncertainty is stated, not hidden.** The source says
  `"This tool is not complete"`, `"Manual editing not supported for this type."`,
  `"# In a real engine, you might blend colors here."` Copy the honesty: an empty or unfinished
  state says so plainly.
- **Names are Portuguese, prose is English.** `guará`, `falcão`, `roça`, `cerrado`, `coletáveis`
  keep their diacritics and are never translated or italicised. Surrounding sentences are English
  (the user chose English for this system). Entity ids and tags are `snake_case` ASCII:
  `guara_player`, `roca_platform_03`, `fruit_pickup_07`.
- **Game copy is terse and physical.** Describe what the player's body does, not how they will
  feel. *"Guará cannot double-jump. Momentum is the whole puzzle."* — not *"an exhilarating
  journey of discovery"*.
- **Developer-facing copy stays un-branded.** The F-key panel says `Developer Tools`,
  `Performance Monitor`, `Physics Debugger`. Tools are named for what they do.

**Vibe:** late light on the tableland, and something still working in it. Warm, dry, worn-in,
tended. The register is **sober optimism** — closer to the *Dear Alice* world (labour, growth,
craft, no irony) than to either apocalyptic grey or slogan-bright activism. Ornament, where it
appears, is **Art Nouveau in its logic**: the curve follows the structure it grows on, and never
decorates for its own sake. Nothing here is a ruin, and nothing here is a utopia poster. Precise
without being cold. It should read like something made by one person who cares about frame timing.

---

## Visual foundations

### Colour

Warm-dominant, and deliberately **grey-free** — the light ramp is the art's amber sky and cream
haze (`--sand-100` … `--rock-600`), so even "neutral" surfaces are warm. Two cool families
exist and are rationed: Falcão slate blues for informational states, and sage / colonial green
(`--sage-100` … `--colonial-700`) for structure, chrome and menu plates. Green here reads as
cultivation and upkeep, never as corrosion — there is no rust or metal family in the system. Sky blue is the only bright cool colour and appears almost exclusively as
world background, never as UI chrome.

- **Primary** is Guará pelt orange `#e2621f` — one primary action per screen.
- **Roxo is the dark theme's ground.** Cerrado Dusk is tinted with ipê-roxo purple
  (`--roxo-300` … `--roxo-900`), not neutral brown — dusk here is the hour after the amber one.
  `--accent-roxo` and `--selected-tint` carry it into UI; `--state-info` is roxo, not slate.
- **The sky is amber, not blue.** `--sky-300/400/500` are late light. The only cool-bright family
  is water and leaf-glass (`--water-300` … `--glass-500`) — spouts, basins, solar panels, numerics.
- **Secondary** is ochre `#c98a3c` — supporting actions, fills, focus.
- **Outlines are never pure black.** Pixel art uses `--ink-900` `#181818` through `--ink-600`.
- **Debug colours are the exception and stay garish** — pure green, magenta, cyan, straight from
  `pyguara/common/palette.py`. They are meant to be unmistakable, not pretty. Never re-tint them.

Two themes: **Cerrado Dusk** (`:root`, default — the editor opens here; roxo-tinted ground) and
**Cerrado Day** (`[data-theme="light"]` — docs and light editor; the amber hour). A third scope,
`[data-theme="game"]`, is the in-world HUD and is always dark because it sits over a bright sky.
Separately, `[data-engine-theme="dark|light|high-contrast|cyberpunk|forest|retro"]` reproduces the
six themes that ship inside the engine, transcribed exactly.

### Type

Four families, each with one job. **All four are substitutions** — see the caveat at the end.

| Token | Family | Use |
| --- | --- | --- |
| `--font-display` | Press Start 2P | Short titles only. Never a run of text. |
| `--font-pixel` | Silkscreen | Every button, label, HUD string, panel title. |
| `--font-body` | Pixelify Sans | Prose on docs, site and store. |
| `--font-mono` | JetBrains Mono | Code, resource paths, ids, numeric readouts. |

The engine ships exactly four sizes — 12 / 16 / 24 / 32 — and they are load-bearing: the runtime
draws at those sizes, so HUD and editor text must match. A wider scale
(`--fs-100` … `--fs-900`) exists only for the web surfaces, where the engine's four-step ladder is
too coarse for prose. Body prose runs 18px / 1.6 at a 60–68ch measure with `text-wrap: pretty`.

### Spacing and layout

The engine's `SpacingScheme` defaults — padding 8, margin 4, gap 8 — are the origin of the 4px
scale in `tokens/spacing.css`. This is **not** an 8pt grid; 12 and 20 are real steps.

Component geometry is fixed by the Python source and must be copied exactly, never snapped:
Button 120×40, Checkbox box 20 with a 10px mark, Slider 150×20 with an r8 knob, TextInput 200×30
with 5px text padding, ProgressBar 200×20, NavBar height 50 with gap 10, `BoxContainer` spacing 5,
world tile 32×32.

The engine has **no grid and no flex-grow model** — `BoxContainer` stacks children linearly and
unconditionally centres them on the cross axis. Nest containers instead of reaching for a grid.
Editor panels are fixed-width rails around a fluid viewport; HUD elements are absolutely
positioned to screen corners.

### Backgrounds and imagery

Full-bleed raster pixel art, always. The parallax Cerrado plate — sky gradient, blue distance
mesas, tableland, foreground trees — is the backdrop for every game screen and the site hero.
No gradients as decoration, no generated textures, no illustration drawn in CSS or SVG. Where a
screen needs depth, a dark scrim (`--surface-scrim`) or a vertical
`rgba(27,21,18,.55) → rgba(27,21,18,.9)` protection gradient sits between the art and the text —
never a blurred capsule, and never alpha-reduced type.

Imagery is **warm, high-chroma, heavy-outlined, no grain**. The current art in `assets/art/` is
smooth cartoon-vector work with thick ink outlines — it renders with `image-rendering: auto` and
scales freely. `image-rendering: pixelated` and whole-multiple scaling now apply **only** to the
legacy `assets/sprites/` crops (in practice: `keycaps.png`).

### Borders, corners, depth

- **Radius is 0 almost everywhere in UI**, even though the art is full of Art Nouveau curves. The
  curve lives in the illustration and in carved wood — the chrome stays square, which is what keeps
  the ornament from turning decorative. The engine's dark preset
  is radius 0; only its light preset uses 4, and `--radius-2` exists for that light-theme case.
  The single round thing in the system is the Slider knob, because the engine calls `draw_circle`.
- Border widths are 1 (hairline, inside panels), 2 (framed panels and all buttons — the Python
  Button always draws a 2px border) and 3 (chunky, dialogs and high-contrast).
- **Depth is bevel, not blur.** `--shadow-bevel` puts a light inset on the top edge and a dark
  inset on the bottom — the pressed-plate look from the sprite sheet. Drop shadows are hard
  offsets with **zero blur** (`--shadow-stamp` 2px, `--shadow-stamp-lg` 4px), matching the engine's
  retro preset (offset 4/4, blur 0). Blur appears only in `--surface-overlay` backdrop filters on
  web surfaces.

### Cards and panels

A card is a `Panel`: flat ochre-dark fill, 1px or 2px `--edge-strong` border, square corners, no
outer shadow unless it floats above content (then `--shadow-stamp`). Optional `bevel` for the
in-world look. Panel headers are a 26px bar in `--surface-raised` with a 12px pixel-font title and
a bottom hairline — lifted straight from the editor's ImGui windows.

### States

Taken from `UIElementState` and the Python `Button.render`:

- **Hover** — the fill *changes colour*, it does not lighten or fade. The engine swaps
  `primary` → `secondary`. Overlays exist (`--theme-hover-overlay`, white at 12% dark / black at
  8% light) for ghost surfaces only. 120ms.
- **Press** — a darker fill, a 1px downward translate, and the bevel collapses to a bottom inset.
  No scale transform. 60ms.
- **Focused** — the *border* switches to secondary; a `--shadow-glow-focus` ring for keyboard and
  gamepad navigation. This is a distinct engine state, not a synonym for hover.
- **Disabled** — fill drops to `--action-disabled`, text to `--text-on-disabled`, bevel off.
  The engine's `Widget.get_state_color` halves each channel; the tokens encode the result.
- **Selected** (hierarchy rows, gallery thumbs) — a secondary-coloured border plus the hover
  overlay, never a filled highlight bar.

### Motion

Short, stepped and few. Sprite animation runs at 12 fps (`--anim-sprite-fps`) — every frame is
hand-drawn, nothing is tweened. UI transitions: 60ms press, 120ms hover, 200ms panels, 320ms
overlays, 500ms scene fades. Default curve is `--ease-out-quad`; `--ease-out-back` overshoots for
pickups and rewards; `--ease-steps` (`steps(4,end)`) is for anything that should read as a sprite
tick rather than a slide. The engine ships a real easing library
(`pyguara/animation/easing.py`) and a tween system — prefer naming a curve over inventing one.
Nothing bounces. Nothing loops in UI chrome.

### Transparency and blur

Used sparingly and for one of three reasons: **legibility** (HUD panels at
`rgba(27,21,18,.82)` so the world stays visible), **modality** (`--surface-scrim` behind pause and
options), or **sticky chrome** (`--surface-overlay` + a 6px backdrop blur on web headers only).
Never on text, never on borders, never decoratively. Debug overlays are semi-transparent by
design so you can see the game behind them.

---

## Iconography

**There is no icon font, no icon component and no SVG icon set in the source — and none has been
invented here.** The sprite sheet *is* the icon library. Icons are game sprites, copied into
`assets/sprites/` and rendered through `Image`:

- **Collectibles** — `items-collectibles.png` (green and gold Cerrado fruit) stand in for currency,
  score and reward.
- **Mechanism** — `prop-solar-leaf-panel.png` (and `prop-water-basin.png`) mark systems, settings
  and power. Solar and water, tended — no gears, no rust.
- **Input prompts** — `keycaps.png` (arrow keys, `A`, `+`) is the only "UI glyph" set that exists.
  Use it for control hints instead of drawing key icons.
- **Characters** — `hero-guara.png` and `sprite-falcao.png` act as avatars in HUD and cards.
- **Menu plates** — there is no plate art in the current key art; the CSS `wood` and `sage` Button
  variants stand in for it, carrying the art's oiled-wood and colonial-green fills.

Where a small affordance is genuinely needed and no sprite exists, the source's own solution is a
**unicode geometric character** in the pixel font, and that is what the components use:
`▸ ▾` for collapsing headers (matching ImGui's tree nodes), `▪ ▫` for tagged vs untagged entities,
`×` to close, `✓` for enabled tools, `←` `→` for pager links. No emoji. No line-icon library.

**If you need an icon that does not exist:** ask for the sprite. Do not link Lucide, Heroicons or
any line-icon set — a 1.5px-stroke vector icon is visually incompatible with 12fps pixel art and
would be the most obvious wrong note in the whole system.

---

## Index

**Root**

| File | What it is |
| --- | --- |
| `readme.md` | This document — the design guide and manifest. |
| `SKILL.md` | Agent Skill front matter, for use in Claude Code. |
| `styles.css` | The only stylesheet consumers link. `@import` lines only. |
| `thumbnail.html` | Homepage tile for this design system. |

**`tokens/`** — `fonts.css`, `palette.css` (raw brand ramps + engine debug colours),
`typography.css`, `spacing.css`, `borders.css`, `shadows.css`, `motion.css`,
`semantic.css` (the aliases product code should use, plus the light and game scopes),
`engine-themes.css` (the six engine presets, verbatim).

**`components/`** — 11 primitives, matching the engine's inventory one-for-one.

| Component | Group | Mirrors |
| --- | --- | --- |
| `Panel` | `core/` | `ui/components/panel.py` |
| `Label` | `core/` | `ui/components/text.py` |
| `Image` | `core/` | `ui/components/image.py` |
| `Canvas` | `core/` | `ui/components/canvas.py` |
| `Button` | `forms/` | `ui/components/button.py` |
| `Checkbox` | `forms/` | `ui/components/checkbox.py` |
| `Slider` | `forms/` | `ui/components/slider.py` |
| `TextInput` | `forms/` | `ui/components/text_input.py` |
| `ProgressBar` | `feedback/` | `ui/components/progress_bar.py` |
| `NavBar` | `navigation/` | `ui/components/navbar.py` |
| `BoxContainer` | `layout/` | `ui/layout.py` |

Each has a sibling `.d.ts` (props contract) and `.prompt.md` (what & when, plus a usage example).

**Consuming these components in a Babel page — one required precaution.** Babel standalone
downlevels top-level `const` to `var`, so `const { Image, Canvas } = window.PyguaraDesignSystem_…`
assigns `window.Image`, clobbering the native `Image` constructor and breaking `new Image()`
page-wide (html-to-image, PNG/PDF/PPTX export, any lazy-loader). **Always alias those two:**
`const { Image: DSImage, Canvas: DSCanvas, … } = window.PyguaraDesignSystem_…` — every kit and card
in this project does. The component names in the `.prompt.md` examples are the export names, not
the local bindings.

**Not built, deliberately:** `Widget` (`ui/components/widget.py`) is an abstract base class that
resolves theme colours by state — it renders nothing, so it has no React counterpart. Its
behaviour is encoded in the state tokens and in every component's disabled/hover handling instead.

**Intentional additions** — three, each with a reason:

1. `Button` variants `wood`, `sage` and `ghost`. The Python `Button` has one look. The source
   *art* has wood and painted menu plates — `sage` recolours the plate into colonial green — and
   the editor needs a chrome-free toolbar button.
2. `Panel`'s `bevel` prop, and the bevel/stamp shadow tokens. Derived from
   `graphics/ninepatch.py` plus the plate art; the Python `Panel` draws a flat rect.
3. The Cerrado Dusk / Cerrado Day theme pair in `semantic.css`. None of the engine's six presets
   is an earthy brand theme, and the brief asked for one in both polarities. The engine's presets
   are preserved untouched in `engine-themes.css`.

**`guidelines/`** — 29 specimen cards feeding the Design System tab, grouped
**Brand** (logo, characters, world, props, icons, direction), **Colors** (nine brand ramps — Guará,
Cerrado, wood & ink, vegetation & amber sky, verdant, roxo, water, falcão, debug — plus both
semantic themes and text levels), **Type** (display, pixel, body, mono),
**Spacing** (scale, engine geometry, borders, shadows, motion) and **Engine** (theme presets,
developer shortcuts).

**`ui_kits/`** — five surfaces. Each has an `index.html`, its JSX, and a `README.md` naming the
source files it was built from.

| Kit | Fidelity |
| --- | --- |
| `editor/` | **Recreation.** Read from `pyguara/editor/` and `pyguara/tools/`. Hierarchy, viewport, Inspector, Assets, Resource Inspector, real F-key overlays, real menu items. Restyled into the Cerrado palette per the brief; layout, names and copy unchanged. |
| `game/` | **Composition.** Engine primitives + the provided art. Title → HUD → Pause → Options. The button plates and title lockup are literal; the engine ships no game code, so the screens themselves are new. |
| `site/` | **New work.** No website exists in the source. |
| `docs/` | **New work chrome, real content.** Sidebar mirrors the engine's real packages; the code sample and presets table are verbatim from `theme_presets.py`. |
| `store/` | **New work.** A generic product-page layout — deliberately not any specific storefront's chrome. |

**Backgrounds are windows cut from the one illustration, never recomposited.** Two 16:9 crops:
`scene-window-grove.png` (grove, plank platform, water, Guará running — no wordmark) backs
gameplay, the editor viewport and the site hero; `scene-window-sign.png` (the carved lockup, no characters) is
there for surfaces that want the sign baked into the background. Title screens use the grove window
plus the transparent `logo-pyguara-lockup.png` on top — the two largest type layers must never
share a frame, which is what happens if you back a menu with the sign window. Use a crop, **not** `object-position` — the full art's aspect is within 7% of 16:9,
so panning has no range and every focus value shows the same frame. Because each window already
contains its subjects, **never overlay the lockup or a character sprite on a window that shows
one** — pick the other window instead. Erasing subjects out of a plate was tried, and looked
exactly like what it was.

**`assets/`** — `art/` (crops from the current key art: scene plate, sign lockup, fox mark,
Guará, Falcão, collectibles, solar leaf panel, water basin, mushroom canopy, floating island,
trees, plank platform), `mascot-pyguara.png`, and the legacy `sprites/` folder.

---

## Caveats — please read

1. **Fonts are substituted.** The source art uses hand-drawn pixel lettering; there are no font
   files anywhere in the repository. Press Start 2P, Silkscreen, Pixelify Sans and JetBrains Mono
   are the closest Google Fonts matches. **Please send the real font files** if the game has them,
   and I will swap them in with proper `@font-face` rules.
2. **There is still no logo file.** `logo-pyguara-lockup.png` and `badge-pyguara-mark.png` are
   crops from the key-art PNG — lossless, but rectangular and without transparency. A vector or
   cut-out lockup would improve every surface immediately. The lockup also reads
   "PYGUARA / SOLAR ENGINE / ENGINE" — the duplicated word is in the source art and needs a fix
   there, not here.
3. **Palette hexes are sampled from the key art.** The source PNG is lossless, so these are exact
   pixel values — but they are sampled from one illustration, not an authored palette. If the game
   has a palette file (`.gpl`, `.hex`, or a `Resources`-loaded artistic palette as
   `common/palette.py` suggests), that should replace `tokens/palette.css`.
4. **Site, docs and store kits are proposals, not recreations.** Nothing in the source defines
   them. Their layout and copy are mine and should be reviewed as new design work.
5. **GitHub was never connected.** Everything came from the attached local folder. If the
   repository has branches, assets or docs the folder lacks, they were not seen.
