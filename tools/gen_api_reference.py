"""Generate the API reference: one page per public module of `pyguara`.

Run by `mkdocs-gen-files` while the site builds. Nothing is written to the
repository; the pages exist only in the built site. Each page is a single
`mkdocstrings` directive, so the text comes from the docstrings.
"""

from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "pyguara"

navigation = mkdocs_gen_files.Nav()

for source in sorted(PACKAGE.rglob("*.py")):
    module_path = source.relative_to(ROOT).with_suffix("")
    parts = module_path.parts

    if parts[-1] == "__main__":
        continue
    if parts[-1] == "__init__":
        parts = parts[:-1]
        page = Path("reference", *parts, "index.md")
    else:
        page = Path("reference", *parts).with_suffix(".md")
    # A leading underscore marks a module as private to the engine.
    if any(part.startswith("_") for part in parts):
        continue

    identifier = ".".join(parts)
    navigation[parts] = page.relative_to("reference").as_posix()

    with mkdocs_gen_files.open(page, "w") as handle:
        handle.write(f"# `{identifier}`\n\n::: {identifier}\n")
    mkdocs_gen_files.set_edit_path(page, source.relative_to(ROOT).as_posix())

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as handle:
    handle.writelines(navigation.build_literate_nav())
