# Command-Line Tools

`pyguara.cli` is the offline toolbox — things you run from a shell against a
project on disk, never from inside a running game. It installs one console
script:

```toml
[project.scripts]
pyguara = "pyguara.cli:main"
```

`main` is a [Click](https://click.palletsprojects.com/) group of
sub-commands:

| Command | What it does |
|---------|--------------|
| `pyguara new`    | Create a project that runs: one scene, an entry point, an assets folder. |
| `pyguara build`  | Package a game into a standalone executable (wraps PyInstaller). |
| `pyguara dist`   | Generate per-store upload scripts and platform icons. |
| `pyguara atlas`  | Pack a folder of sprites into atlas pages + JSON metadata, optionally trimmed. |
| `pyguara sounds` | Build placeholder sound effects from a JSON recipe file, one `.wav` each. |
| `pyguara studio` | Studio's agent surface: `ops`, `mcp` and `instructions`. See [Studio](studio.md) and [Agent Integration](../guides/agent-integration.md). |

```bash
pyguara --help
pyguara --version
pyguara build --help
pyguara atlas --help
```

`build` and `atlas` exit non-zero on failure (`1` for a usage/tool error, the
PyInstaller exit code for a failed build), so they compose in scripts and CI.

---

## `pyguara new`

```bash
pyguara new my-game
cd my-game
python -m my_game
```

Creates `my-game/` and writes into it:

| File | What it is |
| --- | --- |
| `my_game/__main__.py` | The entry point: the window's title and size, then `pyguara.run(MainScene)` |
| `my_game/scenes.py` | One scene, with a component and a box that moves at the fixed rate |
| `pyproject.toml` | The project, depending on the engine version that created it, with a `my-game` script |
| `assets/` | Empty, for textures, sounds, fonts and data |
| `AGENTS.md` and its shims | What `pyguara studio instructions` writes; `--no-instructions` leaves them out |

The package is the name in lower case with hyphens as underscores. A name
that could not be imported is refused, as is one that would shadow `pyguara`
or a standard library module. So is a target directory that already has
something in it; `--directory` puts the project somewhere other than `./NAME`.

No file edits `sys.path`: `python -m my_game` runs from the project folder,
and `pip install -e .` adds a `my-game` command. Run either from the project
folder: the engine reads `config/` and `assets/` and writes `logs/` and
`saves/` relative to the working directory.

---

## `pyguara build`

Compiles an entry script and its assets into a distributable bundle.

```bash
# onedir bundle (default) into dist/
pyguara build examples/guara_falcao/main.py --output dist/guara_falcao

# one self-contained file, custom name and icon
pyguara build examples/true_coral/main.py --onefile --name TrueCoral \
    --icon examples/true_coral/assets/icon.ico
```

### How it runs

`build` shells out to PyInstaller **through the current interpreter** —
`python -m PyInstaller …`, not a bare `pyinstaller` on `PATH` — so it works
inside a `uv`/venv install where the console script may not be exported.
`import PyInstaller` failing prints an install hint and exits `1`; you need
the `build` extra:

```bash
uv sync --extra build      # or: pip install -e .[build]
```

### Asset bundling

With no `-a/--assets`, `build` looks next to the entry script for a folder
named `assets`, `resources`, or `data` (any case) and bundles the first it
finds. Pass `-a` one or more times to be explicit; each becomes a PyInstaller
`--add-data` entry preserving the folder name at runtime.

A default set of hidden imports (`pygame`, `numpy`,
`PIL`, `msgpack`, …) is always passed so the frozen build finds the engine's
backends; add project-specific ones with `--hidden-import`.

### Asset packs

`--pack` bakes the asset folders (auto-detected or given with `-a`) into one
file, `<name>.pak`, and bundles that instead of the folders. An install then
holds one asset file rather than hundreds:

```bash
pyguara build main.py --pack
```

- Each folder keeps its own name inside the pack (`assets/sprites/hero.png`),
  the path `--add-data` would have given the loose file. Paths the game's
  code builds, such as `Path(__file__).parent / "assets" / ...`, find it
  unchanged.
- **The frozen game mounts every `.pak` in its bundle on its first asset
  read**, through `pyguara.assets`. There is nothing to call. Run from
  source, nothing is mounted and the loose files are read.
- Already-compressed files (PNG, JPEG, OGG, MP3, FLAC) are stored as they
  are; everything else is deflated. Hidden files and `__pycache__` are left
  out; `.meta` sidecars are kept.
- The pack is reproducible: the same folders bake to the same bytes.
- A game's own file reads must go through `pyguara.assets` too
  (`assets.read_text(path)` rather than `open(path)`), or they will not find
  packed files. See `docs/systems/resources.md`, "Packed assets".

### Crash reports

A build is `--windowed` by default, so it has no console: an unhandled
exception closes the window and the player sees nothing else. Install the
crash reporter first thing in the entry script, before the application is
built, so a failure at startup is caught too:

```python
from pyguara.crash import install_crash_reporter

install_crash_reporter("Guara & Falcao")
app = create_application()
```

A crash then writes `crash-<date>-<time>-<pid>.txt` under `crashes/` in
the player's data directory: `~/.local/share/<game>` on Linux, under
`%LOCALAPPDATA%` on Windows, `~/Library/Application Support/<game>` on
macOS. It holds the traceback, the pyguara and Python versions, the
platform, whether the build is frozen, the native store, the renderer and
the GPU, and anything the game added with `pyguara.crash.note(key, value)`,
such as the level. The newest 20 are kept. Where there is a console, the
report's path is printed and the traceback still follows.

Where there is none -- a frozen build not started from a terminal -- the
player is also shown a dialog with the error's message and the report's
path: a message box on Windows, an alert through `osascript` on macOS,
and `zenity` or `kdialog` on Linux when either is installed (otherwise
nothing is shown). `install_crash_reporter(..., dialog=True)` or `False`
overrides that. A project made by `pyguara new` installs the reporter in
its entry point.

### A machine with no usable GPU

The default renderer stops at startup with `NoGraphicsAdapterError`,
which the reporter shows the player as above. The engine never switches
renderer by itself, because the software renderer has no lighting or
post-processing. A game that accepts the difference turns on the
fallback, and ships the software renderer by building in an environment
with the `pyguara[pygame]` extra installed (`pyguara build` bundles
pygame whenever it is importable):

```python
def configure(config: GameConfig) -> None:
    config.display.software_fallback = True
```

or `"software_fallback": true` under `display` in the config file. With
it on and no GPU, the game starts on `pygame`, logs a warning, and notes
the switch in any later crash report.

It is opt-in because the folder is named after the game. Ctrl+C is not a
crash, and an exception in a background thread, which does not end the
program, is not reported. A report contains paths from the player's
machine, home directory included, so it is theirs to send.

### Options

| Option | Default | Notes |
|--------|---------|-------|
| `-o, --output` | `dist/` | Bundle destination. |
| `-n, --name` | entry-script stem | Executable / bundle name. |
| `--onefile / --onedir` | `--onedir` | Single file vs. a directory. |
| `--windowed / --console` | `--windowed` | Hide the OS console on launch. |
| `--icon` | — | Any format Pillow reads; converted to the host's. |
| `--bundle-id` | — | macOS bundle identifier, e.g. `com.studio.game`. |
| `--game-version` | `pyproject.toml`'s | The version in the Windows file details. |
| `--company` | — | Company name in the Windows file details. |
| `--copyright` | — | Copyright line in the Windows file details. |
| `-a, --assets` | auto-detect | Repeatable. Asset directories to bundle. |
| `--add-data` | — | Repeatable. Raw `src<sep>dst` PyInstaller spec. |
| `--hidden-import` | — | Repeatable. Extra modules to force-include. |
| `--clean` | off | Wipe the PyInstaller cache first. |
| `--debug` | off | `--debug=all`. |
| `--pack` | off | Bake the asset folders into one `<name>.pak` instead of bundling them loose. |
| `--dry-run` | off | Print the PyInstaller command and stop. |

### Windows file details

A Windows `.exe` carries a version resource, which Explorer shows on the
file's Details tab and Task Manager uses for its name: product name,
description, file and product version, company and copyright. `pyguara
build` writes it from `--name`, the version and the two optional flags.
The version is `--game-version`, else `[project].version` in the nearest
`pyproject.toml` above the entry script, which a `pyguara new` project
has. With neither, the build says so and the `.exe` has no details;
`--company` or `--copyright` with no version is an error rather than
dropped. Windows stores four 16-bit numbers, taken from the release part
(`1.4.0rc2` is 1.4.0.0); the text fields keep the whole string.

After a successful build, the generated `build/` work directory and the
`<name>.spec` file are removed from `--output`. The reported `Output:` path
points at the executable — for `--onedir` that is
`<output>/<name>/<name>[.exe]`, one level inside the bundle directory.

### Icons

`--icon` takes **any image Pillow can read**, and converts it to the format
the host toolchain needs — `.ico` on Windows, `.icns` on macOS, `.png`
elsewhere — into the PyInstaller work directory, not the shipped bundle.
This matters because PyInstaller converts nothing and **fails** on
Windows given a `.png`, so a project with one `logo.png` could not be
built there. Pass an already-correct file and it is used untouched.

PyInstaller cannot cross-compile, so "the host" and "the target" are the
same thing: a Windows `.exe` is built on Windows. `pyguara dist icons`
writes all three formats at once if you want them committed.

Use `--dry-run` to see exactly what would be executed without needing
PyInstaller installed:

```bash
pyguara build main.py --onefile --dry-run
```

---

## `pyguara dist`

Generates the per-store scripts that take a built game to players. It
**writes scripts and never uploads**: that needs `steamcmd` or `butler`, a
store account, and for Steam a Steam Guard code, none of which belongs
inside a game engine.

```bash
pyguara dist icons logo.png --out build/icons
pyguara dist steam --app-id 480 --depot-id 481 --content dist/MyGame
pyguara dist itch --target studio/my-game --content dist/MyGame --version 0.1.0
```

### `pyguara dist icons`

Writes `icon.ico` (multi-size: 16, 32, 48, 64, 128, 256 — Windows picks
one per context, and a single-size file is a blurry taskbar icon),
`icon.icns` and `icon.png` from one source image. Sizes larger than the
source are skipped rather than upscaled.

### `pyguara dist steam`

Writes a content-builder script set into `--out` (default `dist/steam/`):

| file | what it is |
| --- | --- |
| `scripts/app_build_<appid>.vdf` | the build: which depots, which branch |
| `scripts/depot_build_<depotid>.vdf` | the depot: which files go in it |
| `upload.sh` / `upload.bat` | `steamcmd +run_app_build` around the above |
| `dev/steam_appid.txt` | **development only** — see below |
| `README.md` | the manual steps, including Steam Guard |

Two defaults are deliberate. `Preview` is `1`, because a wrong
`ContentRoot` produces a completely successful build of the wrong files
and the only sign is the file list. `SetLive` is **empty**, because naming
a branch there publishes to customers the moment the upload finishes.

**`steam_appid.txt` is never put in the content root**, and the depot
script excludes it by name as well. It overrides the App ID Steam supplies
*and* makes `SteamAPI_RestartAppIfNecessary` return false, so a customer
who launches the executable directly plays with no Steam client attached —
no overlay, no achievements, no cloud saves, and no error. Copy it next to
the executable while testing locally only.

One known uncertainty, stated in the generated README too: the depot
script's root key is `DepotBuildConfig`, which is what the SDK's bundled
samples and working upload pipelines use, while Valve's documentation page
spells the same block `DepotBuild`. If `steamcmd` rejects the file, diff
it against `sdk/tools/ContentBuilder/scripts` and trust those.

### `pyguara dist itch`

Writes `push.sh` wrapping `butler push <dir> user/game:channel`.

The channel name is not cosmetic: itch.io reads it to decide which
platform an upload is for, and one naming no platform is tagged for none
and offered to nobody — while butler reports success. So a channel that
matches none of `win`, `windows`, `mac`, `osx`, `linux`, `android` is
**refused**, with the list in the error. Several in one name is fine, as
butler's own example `win-linux-mac-stable` shows. With no `--channel`,
the host platform's name is used.

---

## `pyguara atlas`

Packs every image in a directory into atlas pages using a shelf-packing
algorithm (sprites sorted tallest-first, laid into horizontal rows), and
writes JSON metadata the engine's `ResourceManager.load_atlas` reads back.

```bash
pyguara atlas -i assets/sprites/ -o build/atlas.png -m build/atlas.json
pyguara atlas -i assets/sprites/ -o build/atlas.png -s 4096 -p 4
pyguara atlas -i assets/sprites/ -o build/atlas.png -m build/atlas.json \
  -s 2048x1024 --trim --fit pot
```

Supported inputs: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tga` (non-`RGBA` images
are converted). The scan is **one directory deep**, not recursive.

### Options

| Option | Default | Notes |
|--------|---------|-------|
| `-i, --input` | *(required)* | Directory of source sprites. |
| `-o, --output` | *(required)* | Atlas PNG path. |
| `-m, --metadata` | — | JSON metadata path. Omit to skip. |
| `-s, --size` | `2048` | Largest page: `2048` is square, `2048x1024` is not. |
| `-p, --padding` | `2` | Transparent gutter around each sprite. |
| `--trim` | off | Cut each sprite's fully transparent border off before packing. |
| `--fit` | `fixed` | Page size: `fixed` is the full `--size`, `tight` crops to what the page holds, `pot` crops and rounds each side up to a power of two, never past `--size`. |

### Trimming

With `--trim`, a sprite that is mostly transparent border takes only its
opaque part's room. The region's `width` and `height` are the kept part,
`original_size` is the source image, and `offset` is where the kept part
sat in it. A wholly transparent image keeps one transparent pixel. At run
time `AtlasRegion.trimmed` says whether a region was cut, and
`AtlasRegion.center_offset` is what to add to a centred draw position so
the region lands where the whole image would have. Off by default, because
trimming changes each region's size, and code that draws a region at its
rect's size would draw it smaller.

### Pages

Sprites that overflow a page go on the next one. Page 0 is the `-o` file,
and later pages sit beside it as `atlas_1.png`, `atlas_2.png` and so on.
Several pages need `-m`, since only the metadata says which page holds a
sprite. Without it, an overflow is an error. `load_atlas(path, metadata)`
loads every page: `Atlas.pages` lists them, page 0 is `Atlas.texture`, and
`Atlas.texture_of(name)` is the one a region is on. Rerunning into the
sprite folder ingests none of the previous run's pages, and deletes a page
the new run no longer needs.

### Metadata shape

```json
{
  "atlas_size": [2048, 2048],
  "padding": 2,
  "sprite_count": 3,
  "pages": [
    { "image": "atlas.png", "size": [2048, 2048] },
    { "image": "atlas_1.png", "size": [2048, 2048] }
  ],
  "regions": {
    "player": { "x": 2, "y": 2, "width": 40, "height": 58,
                "original_size": [64, 64], "offset": [12, 6], "page": 0 }
  }
}
```

A region's name is the source filename **without extension**. `sprite_count`
always equals `len(regions)`. `atlas_size` is page 0's size. Metadata
without `pages`, `offset` or `page`, as older versions wrote it, loads as
one untrimmed page. A page `image` must be a bare file name; a path is
refused, since the metadata travels with the game's assets.

### Failures are loud

The generator refuses ambiguous or impossible input rather than producing a
subtly wrong atlas:

- **Stem collision.** `hero.png` and `hero.jpg` in the same folder both want
  the region name `hero`. This raises `ValueError` naming the offending
  files — rename or remove one.
- **Sprite doesn't fit.** A sprite larger than `--size` in *either*
  dimension (plus padding) raises, because no page could hold it. Increase
  `--size` or shrink the sprite.
- **Output inside the input.** `generate()` excludes the resolved `-o`/`-m`
  paths from its own scan, so re-running with the atlas written back into the
  sprite folder does not ingest the previous atlas. Still cleaner to keep
  build output in its own directory.

### Two ways to invoke it

`pyguara atlas …` and `python -m pyguara.cli.atlas_generator …` run the same
Click command with the same options — the module entry point delegates
straight to it.

---

## `pyguara sounds`

Builds placeholder sound effects, so a game has audio to wire up before
it has real assets.

```bash
pyguara sounds data/sounds.json assets/audio/
pyguara sounds data/sounds.json assets/audio/ --seed 7
```

`RECIPES` is a JSON object mapping each sound's name to its recipe: a tree
of tones, noise and envelopes, in the format `pyguara.audio.placeholder`
documents. Every recipe is checked before anything is written, and a bad
one fails the command without leaving a partial set behind. `--seed` is
shared by every sound; change it to reroll their noise.

---

## Testing

`tests/test_build_tool.py` covers argument assembly and the `--dry-run` /
missing-PyInstaller paths with Click's `CliRunner` (a real PyInstaller run is
not exercised). `tests/test_atlas_tool.py` covers `load_images` / `pack` /
`generate`, the collision and size guards, and round-tripping the metadata
through `ResourceManager.load_atlas`. `tests/test_atlas_pages.py` covers
trimming, `--fit`, pages, and loading them back.
