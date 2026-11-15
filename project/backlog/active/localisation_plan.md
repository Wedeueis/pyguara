# Localisation

Phase 2 of `engine_completion_roadmap.md`. Reclaimer ships in Steam's ten
largest languages (the user's call, 2026-11-15):

| Code | Language | What the engine needs for it |
| --- | --- | --- |
| `en` | English | The source language |
| `zh-Hans` | Simplified Chinese | A CJK font; line breaks between characters |
| `ru` | Russian | Four plural forms |
| `es` | Spanish | -- |
| `pt-BR` | Brazilian Portuguese | -- |
| `de` | German | Long words: layouts must wrap or shrink |
| `ja` | Japanese | A CJK font (Japanese glyph forms); line breaks between characters, with kinsoku |
| `ko` | Korean | A CJK font (Hangul); wraps on spaces |
| `fr` | French | Its own plural rule: 0 and 1 are singular |
| `tr` | Turkish | Dotted and dotless i: `"i".upper()` is wrong |

None is right-to-left and none needs shaping, so the text renderer keeps
its one-character-one-glyph model. Arabic, Hindi and the like would need
shaping and bidi (HarfBuzz-class work); they are not planned.

**Translations:** Claude drafts every language; each file is marked
unreviewed until a native speaker signs it off. Drafts are fine for
development and playtests, not for release.

## The work, one PR each

| # | Repository | What |
| --- | --- | --- |
| L1 (this PR) | pyguara | `pyguara.i18n`: string tables per locale, `{name}` placeholders, CLDR plural forms for the ten, English fallback, a `locale` setting, and `pyguara i18n check`, which finds missing keys, stray keys, placeholder mismatches and missing plural forms |
| L2 | pyguara | Font fallback in both renderers: a character the main face lacks is drawn from the next face that has it, chosen per locale for Han (Japanese forms for `ja`, Simplified for `zh-Hans`) |
| L3 | pyguara | Line breaking for CJK in `wrap_text` and rich text, with the kinsoku rules (no line starts with `。` or `」`); locale-aware upper and lower case for Turkish |
| L4 | reclaimer_v2 | Every player-visible string to `locales/en.json`; drafts for the other nine; the Noto Sans CJK fonts; the language from Steam, else the system, else English |

Then packed assets, which will carry the fonts.

**Done when** Reclaimer can be switched to each of the ten, every screen
reads in that language with nothing clipped or missing a glyph, and the
check command passes for all ten.
