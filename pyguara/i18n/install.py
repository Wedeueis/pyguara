"""Building the application's translator from its config."""

from __future__ import annotations

from pathlib import Path

from pyguara import assets
from pyguara.config.types import I18nConfig
from pyguara.events.dispatcher import EventDispatcher
from pyguara.i18n.events import LocaleChanged
from pyguara.i18n.locales import system_locale
from pyguara.i18n.translator import Translator
from pyguara.log import get_logger
from pyguara.ui.text_case import set_case_language

__all__ = ["install_translator"]

logger = get_logger(__name__)


def install_translator(
    config: I18nConfig, dispatcher: EventDispatcher
) -> Translator | None:
    """Load the locales folder, choose a locale, and announce changes.

    The locale is `config.locale`, or the system's when that is empty,
    narrowed to the closest one there is a file for (`pt-PT` gets `pt-BR`,
    an unsupported language gets the source). A change of locale later is
    dispatched as `LocaleChanged`. Case changes (`pyguara.ui.text_case`)
    follow the locale, now and on every change, so Turkish upper-cases
    `i` to `İ`. The folder may be in a mounted pack.

    Args:
        config: The `i18n` section.
        dispatcher: Where `LocaleChanged` goes.

    Returns:
        The translator, or None when the folder does not exist: a game that
        is not localised does not need one.

    Raises:
        FileNotFoundError: If the folder exists without the source file.
        ValueError: If a locale file is not a valid table.
    """
    directory = Path(config.directory)
    if not assets.is_dir(directory):
        return None
    probe = Translator.from_directory(
        directory, locale=config.source, source=config.source
    )
    wanted = config.locale or system_locale()
    probe.choose(wanted)

    def announce(locale: str) -> None:
        set_case_language(locale)
        dispatcher.dispatch(LocaleChanged(locale=locale))

    set_case_language(probe.locale)
    probe.on_change(announce)
    logger.info(
        f"Text in {probe.locale!r} (asked for {wanted or 'the source'!r}; "
        f"available: {', '.join(probe.available)})"
    )
    return probe
