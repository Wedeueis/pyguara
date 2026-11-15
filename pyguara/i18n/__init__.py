"""Localisation: player-visible text by key, in the player's language.

Game code names a key; each locale has a file of text for the keys:

```python
tr("room.waiting", player="Ana")      # "Waiting for Ana..." / "Ожидание Ana..."
tr("hud.salvage", count=3)            # the right plural form per language
```

See `docs/systems/localisation.md`.
"""

from pyguara.i18n.events import LocaleChanged
from pyguara.i18n.install import install_translator
from pyguara.i18n.locales import best_locale, locale_from_steam, system_locale
from pyguara.i18n.plurals import (
    PLURAL_FORMS,
    language_of,
    plural_category,
    required_plural_forms,
    supported_languages,
)
from pyguara.i18n.table import LocaleTable, UnsafePlaceholderError, placeholders
from pyguara.i18n.translator import MissingStringError, Translator

__all__ = [
    "PLURAL_FORMS",
    "LocaleChanged",
    "LocaleTable",
    "MissingStringError",
    "Translator",
    "UnsafePlaceholderError",
    "best_locale",
    "install_translator",
    "language_of",
    "locale_from_steam",
    "placeholders",
    "plural_category",
    "required_plural_forms",
    "supported_languages",
    "system_locale",
]
