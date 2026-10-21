# Command-Line Tools

`pyguara.cli` is the offline toolbox — things you run from a shell against a
project on disk, never from inside a running game. It installs one console
script:

```toml
[project.scripts]
pyguara = "pyguara.cli:main"
```

`main` is a [Click](https://click.palletsprojects.com/) group with two
sub-commands:

| Command | What it does |
|---------|--------------|
| `pyguara build`  | Package a game into a standalone executable (wraps PyInstaller). |
| `pyguara dist`   | Generate per-store upload scripts and platform icons. |
| `pyguara atlas`  | Pack a folder of sprites into one texture atlas + JSON metadata. |

```bash
pyguara --help
pyguara --version
pyguara build --help
pyguara atlas --help
```

Both sub-commands exit non-zero on failure (`1` for a usage/tool error, the
PyInstaller exit code for a failed build), so they compose in scripts and CI.

---

## `pyguara build`

Compiles an entry script and its assets into a distributable bundle.

```bash
# onedir bundle (default) into dist/
pyguara build games/guara_falcao/main.py --output dist/guara_falcao

# one self-contained file, custom name and icon
pyguara build games/true_coral/main.py --onefile --name TrueCoral \
    --icon games/true_coral/assets/icon.ico
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

A default set of hidden imports (`pygame`, `pymunk`, `moderngl`, `numpy`,
`PIL`, `msgpack`, …) is always passed so the frozen build finds the engine's
backends; add project-specific ones with `--hidden-import`.

### Options

| Option | Default | Notes |
|--------|---------|-------|
| `-o, --output` | `dist/` | Bundle destination. |
| `-n, --name` | entry-script stem | Executable / bundle name. |
| `--onefile / --onedir` | `--onedir` | Single file vs. a directory. |
| `--windowed / --console` | `--windowed` | Hide the OS console on launch. |
| `--icon` | — | Any format Pillow reads; converted to the host's. |
| `--bundle-id` | — | macOS bundle identifier, e.g. `com.studio.game`. |
| `-a, --assets` | auto-detect | Repeatable. Asset directories to bundle. |
| `--add-data` | — | Repeatable. Raw `src<sep>dst` PyInstaller spec. |
| `--hidden-import` | — | Repeatable. Extra modules to force-include. |
| `--clean` | off | Wipe the PyInstaller cache first. |
| `--debug` | off | `--debug=all`. |
| `--dry-run` | off | Print the PyInstaller command and stop. |

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

Packs every image in a directory into one atlas texture using a
shelf-packing algorithm (sprites sorted tallest-first, laid into horizontal
rows), and writes JSON metadata the engine's `ResourceManager.load_atlas`
reads back.

```bash
pyguara atlas -i assets/sprites/ -o build/atlas.png -m build/atlas.json
pyguara atlas -i assets/sprites/ -o build/atlas.png -s 4096 -p 4
```

Supported inputs: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tga` (non-`RGBA` images
are converted). The scan is **one directory deep**, not recursive.

### Options

| Option | Default | Notes |
|--------|---------|-------|
| `-i, --input` | *(required)* | Directory of source sprites. |
| `-o, --output` | *(required)* | Atlas PNG path. |
| `-m, --metadata` | — | JSON metadata path. Omit to skip. |
| `-s, --size` | `2048` | Atlas is a square `size × size`. |
| `-p, --padding` | `2` | Transparent gutter around each sprite. |

### Metadata shape

```json
{
  "atlas_size": [2048, 2048],
  "padding": 2,
  "sprite_count": 3,
  "regions": {
    "player": { "x": 2, "y": 2, "width": 64, "height": 64,
                "original_size": [64, 64] }
  }
}
```

A region's name is the source filename **without extension**. `sprite_count`
always equals `len(regions)`.

### Failures are loud

The generator refuses ambiguous or impossible input rather than producing a
subtly wrong atlas:

- **Stem collision.** `hero.png` and `hero.jpg` in the same folder both want
  the region name `hero`. This raises `ValueError` naming the offending
  files — rename or remove one.
- **Sprite doesn't fit.** A sprite larger than `--size` in *either*
  dimension (plus padding) raises — increase `--size` or shrink the sprite.
  (Width used to slip through and get silently cropped.)
- **Output inside the input.** `generate()` excludes the resolved `-o`/`-m`
  paths from its own scan, so re-running with the atlas written back into the
  sprite folder does not ingest the previous atlas. Still cleaner to keep
  build output in its own directory.

### Two ways to invoke it

`pyguara atlas …` and `python -m pyguara.cli.atlas_generator …` run the same
Click command with the same options — the module entry point delegates
straight to it.

---

## Testing

`tests/test_build_tool.py` covers argument assembly and the `--dry-run` /
missing-PyInstaller paths with Click's `CliRunner` (a real PyInstaller run is
not exercised). `tests/test_atlas_tool.py` covers `load_images` / `pack` /
`generate`, the collision and size guards, and round-tripping the metadata
through `ResourceManager.load_atlas`.
