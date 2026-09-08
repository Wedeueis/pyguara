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
| `--icon` | — | `.ico` (Windows) / `.icns` (macOS). |
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

Use `--dry-run` to see exactly what would be executed without needing
PyInstaller installed:

```bash
pyguara build main.py --onefile --dry-run
```

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
