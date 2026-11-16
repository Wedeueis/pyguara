# Localisation

Player-visible text lives in one file per language, not in the code. Code
names a **key**; the engine finds the text for it in the player's language.

```python
class Hud(Scene):
    def on_enter(self) -> None:
        self.title.text = self.tr("title")
        self.waiting.text = self.tr("room.waiting", player=host_name)

    def update(self, dt: float) -> None:
        self.scrap.text = self.tr("hud.salvage", count=self.salvage)
```

## The files

`locales/<locale>.json`, one per language, UTF-8, named by BCP 47 tag:
`en.json`, `zh-Hans.json`, `pt-BR.json`. Each is a flat object of keys:

```json
{
  "_meta": {"reviewed": false, "translator": "machine draft"},
  "title": "Рекламатор",
  "room.waiting": "Ожидание {player}...",
  "hud.salvage": {
    "one": "{count} обломок",
    "few": "{count} обломка",
    "many": "{count} обломков",
    "other": "{count} обломка"
  }
}
```

- **The source locale (`en` by default) is the reference.** Every key the
  game uses must be there.
- **A placeholder is `{name}`**, optionally with a format spec:
  `{ratio:.0%}`. A translator may move it anywhere in the sentence. Nothing
  else is allowed (`{0}`, `{player.name}`, `{x!r}`), because a translation
  file is data from outside the code and `str.format` could otherwise walk
  the attributes of what is passed in. A file that tries is refused when it
  loads.
- **A plural entry is an object of CLDR forms**: `zero`, `one`, `two`,
  `few`, `many`, `other`. `other` is required. Pass `count=`, an int, and
  the form is picked by the language's rule. A language without plurals
  (Chinese, Japanese, Korean) may give a plain string.
- **`_meta.reviewed: false`** marks a translation no native speaker has
  signed off yet. A file without it counts as reviewed.

### Plural forms by language

| Languages | Forms a translation must give | Notes |
| --- | --- | --- |
| `en`, `de`, `tr` | `one`, `other` | `one` is exactly 1 |
| `es`, `it` | `one`, `other` | `many` is optional, for exact millions |
| `fr`, `pt` | `one`, `other` | 0 is singular too; `many` optional, as above |
| `ru` | `one`, `few`, `many`, `other` | 1, 21: `one`. 2-4, 22: `few`. 5-20, 25: `many` |
| `zh`, `ja`, `ko` | `other` | No plural forms |

Another language is refused until its rules are added to
`pyguara/i18n/plurals.py`, rather than given English's.

## What a lookup does

| Situation | Result |
| --- | --- |
| The key is in the current locale | Its text |
| Only the source has the key | The source's text, and one warning in the log per key and locale |
| The source lacks the key | `MissingStringError`: code asking for text nobody wrote |
| A plural form the entry lacks | The `other` form |
| A placeholder with no value | `KeyError` |

## Choosing the language

The `i18n` config section:

| Setting | Default | |
| --- | --- | --- |
| `locale` | `""` | A tag such as `"pt-BR"`. Empty uses the operating system's |
| `directory` | `"locales"` | The folder of locale files. Without it, nothing is loaded |
| `source` | `"en"` | The language the game is written in |

`directory` is read through `pyguara.assets`, so `locales/` can ship in a
pack. A relative path is relative to the working directory, which a
player's shortcut decides, so a built game should set it from where its own
files are, as it does for any other asset.

The locale asked for is narrowed to the closest one there is a file for:
an exact match, then (for Chinese) the same script, then the same language
in another region (`pt-PT` gets `pt-BR`), and otherwise the source.

A game on Steam should use the language the player chose there:

```python
from pyguara.i18n import best_locale, locale_from_steam

steam_locale = locale_from_steam(steam_language)        # "schinese" -> "zh-Hans"
translator.locale = best_locale(steam_locale or "", translator.available, source="en")
```

Setting `translator.locale` while the game runs dispatches `LocaleChanged`;
a screen built from keys rebuilds its text when it hears it. Case changes
in `pyguara.ui.text_case` follow the locale from startup and on every
change, so `upper("i")` is `"İ"` in Turkish.

Outside a scene, take the `Translator` from the container,
`app.container.get(Translator)`, and pass it to what needs it.

## Checking the files

```bash
pyguara i18n check locales/
pyguara i18n check locales/ --require-reviewed     # for a release build
```

It compares every locale with the source and reports keys that are missing
or stray, placeholders that differ, plural forms the language needs and the
entry lacks, and files that will not load. A translation not yet reviewed
is a warning, or a failure with `--require-reviewed`. The exit status is 1
on any error.
