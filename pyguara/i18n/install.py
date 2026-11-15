"""Building the application's translator from its config."""

from __future__ import annotations

from pathlib import Path

from pyguara.config.types import I18nConfig
from pyguara.events.dispatcher import EventDispatcher
from pyguara.i18n.events import LocaleChanged
from pyguara.i18n.locales import best_locale, system_locale
from pyguara.i18n.translator import Translator
from pyguara.log import get_logger

__all__ = ["install_translator"]

logger = get_logger(__name__)


def install_translator(
    config: I18nConfig, dispatcher: EventDispatcher
) -> Translator | None:
    """Load the locales folder, choose a locale, and announce changes.

    The locale is `config.locale`, or the system's when that is empty,
    narrowed to the closest one there is a file for (`pt-PT` gets `pt-BR`,
    an unsupported language gets the source). A change of locale later is
    dispatched as `LocaleChanged`.

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
    if not directory.is_dir():
        return None
    probe = Translator.from_directory(
        directory, locale=config.source, source=config.source
    )
    wanted = config.locale or system_locale()
    probe.locale = best_locale(wanted, probe.available, source=config.source)

    def announce(locale: str) -> None:
        dispatcher.dispatch(LocaleChanged(locale=locale))

    probe.on_change(announce)
    logger.info(
        f"Text in {probe.locale!r} (asked for {wanted or 'the source'!r}; "
        f"available: {', '.join(probe.available)})"
    )
    return probe
