"""Regression tests for EngineLogger's kwargs-to-extra handling (LOG-1) and the
logging migration (execute the logging migration)."""

import logging

import pytest

import pyguara.log as log_module
from pyguara.log.manager import LogManager
from pyguara.log.types import LogLevel


@pytest.fixture
def logger():
    manager = LogManager()
    manager.configure(level=LogLevel.DEBUG, console=False)
    log = manager.get_logger("test.log1")
    yield log
    manager.shutdown()


@pytest.mark.unit
def test_critical_with_exc_info_true_does_not_raise(logger):
    logger.critical("m", exc_info=True)


@pytest.mark.unit
def test_info_with_reserved_attribute_name_does_not_raise(logger):
    logger.info("m", module="a")


@pytest.mark.unit
def test_exception_does_not_raise(logger):
    logger.exception(ValueError("x"))


@pytest.mark.unit
def test_stack_info_and_stacklevel_are_forwarded_to_stdlib_logger(logger, caplog):
    with caplog.at_level(logging.DEBUG, logger="test.log1"):
        logger.debug("m", stack_info=True, stacklevel=1)

    assert caplog.records[0].stack_info is not None


@pytest.mark.unit
def test_shutdown_closes_file_handler(tmp_path):
    manager = LogManager()
    log_file = tmp_path / "engine.log"
    manager.configure(level=LogLevel.INFO, console=False, log_file=log_file)
    log = manager.get_logger("test.shutdown")
    log.info("hello")

    handlers = list(log._logger.handlers)
    assert handlers

    manager.shutdown()

    for handler in handlers:
        assert handler.stream is None or getattr(handler.stream, "closed", True)


@pytest.mark.unit
def test_get_logger_returns_same_instance_regardless_of_call_count():
    manager = LogManager()
    manager.configure(level=LogLevel.DEBUG, console=False)

    first = manager.get_logger("test.identity")
    second = manager.get_logger("test.identity")

    assert first is second
    manager.shutdown()


@pytest.mark.unit
def test_configure_rebuilds_handlers_for_already_constructed_loggers(tmp_path):
    manager = LogManager()
    manager.configure(level=LogLevel.INFO, console=False)
    log = manager.get_logger("test.rebuild")
    assert not any(isinstance(h, logging.FileHandler) for h in log._logger.handlers)

    log_file = tmp_path / "reconfigured.log"
    manager.configure(level=LogLevel.INFO, console=False, log_file=log_file)

    assert any(isinstance(h, logging.FileHandler) for h in log._logger.handlers)
    manager.shutdown()


@pytest.mark.unit
def test_printf_style_args_are_forwarded_like_stdlib_logging(caplog):
    manager = LogManager()
    manager.configure(level=LogLevel.DEBUG, console=False)
    log = manager.get_logger("test.printf")

    with caplog.at_level(logging.DEBUG, logger="test.printf"):
        log.error("Failed to load '%s': %s", "clip.wav", "boom")

    assert caplog.records[0].getMessage() == "Failed to load 'clip.wav': boom"
    manager.shutdown()


@pytest.mark.unit
def test_module_level_get_logger_is_backed_by_shared_default_manager():
    name = "test.shared_default"
    first = log_module.get_logger(name)
    second = log_module.default_log_manager.get_logger(name)

    assert first is second


# -- Source attribution --


class _Capture(logging.Handler):
    """Collects records so their attributes can be asserted directly."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured():
    manager = LogManager()
    manager.configure(level=LogLevel.DEBUG, console=False)
    log = manager.get_logger("test.source")
    handler = _Capture()
    log._logger.addHandler(handler)
    yield log, handler
    log._logger.removeHandler(handler)
    manager.shutdown()


@pytest.mark.unit
def test_records_point_at_the_calling_code_not_the_wrapper(captured):
    """Every record used to report logger.py and the line of the internal
    `self._logger.log(...)` call, because the two wrapper frames were never
    skipped. %(lineno)d in the file format, and the module/line carried into
    OnLogEvent, were therefore the same useless value for every message in
    the engine."""
    log, handler = captured

    log.info("from the test")
    record = handler.records[-1]

    assert record.module == "test_log_manager"
    assert record.funcName == "test_records_point_at_the_calling_code_not_the_wrapper"
    assert record.pathname.endswith("test_log_manager.py")


@pytest.mark.unit
def test_every_level_method_attributes_correctly(captured):
    log, handler = captured

    log.debug("d")
    log.info("i")
    log.warning("w")
    log.error("e")
    log.critical("c")

    assert {r.module for r in handler.records} == {"test_log_manager"}
    assert all(
        r.funcName == "test_every_level_method_attributes_correctly"
        for r in handler.records
    )


@pytest.mark.unit
def test_performance_and_exception_also_attribute_correctly(captured):
    log, handler = captured

    log.performance("load", 1.5)
    log.exception(ValueError("boom"))

    assert {r.module for r in handler.records} == {"test_log_manager"}


@pytest.mark.unit
def test_a_caller_supplied_stacklevel_still_skips_the_wrapper(captured):
    """stacklevel=2 must mean "two frames above my caller", counted from user
    code, not from inside the wrapper."""
    log, handler = captured

    def helper() -> None:
        log.info("logged via a helper", stacklevel=2)

    helper()

    assert handler.records[-1].funcName == (
        "test_a_caller_supplied_stacklevel_still_skips_the_wrapper"
    )


# -- Handler ownership --


@pytest.mark.unit
def test_reconfigure_leaves_foreign_handlers_attached(captured):
    """reconfigure() cleared the whole handler list of a process-global stdlib
    logger, so it silently tore down handlers installed by the application --
    or by a second LogManager sharing the same name."""
    log, handler = captured

    log.reconfigure(
        level=LogLevel.DEBUG, event_dispatcher=None, log_file=None, console_output=False
    )

    assert handler in log._logger.handlers


@pytest.mark.unit
def test_two_managers_do_not_tear_down_each_others_handlers():
    name = "test.two_managers"
    first, second = LogManager(), LogManager()

    log_a = first.get_logger(name)
    handlers_after_a = list(log_a._logger.handlers)
    log_b = second.get_logger(name)

    assert log_a is not log_b
    assert log_a._logger is log_b._logger, "stdlib loggers are process-global"
    for handler in handlers_after_a:
        assert handler in log_a._logger.handlers

    first.shutdown()
    second.shutdown()


@pytest.mark.unit
def test_reconfigure_does_not_accumulate_its_own_handlers(tmp_path):
    manager = LogManager()
    manager.configure(level=LogLevel.INFO, console=True, log_file=tmp_path / "a.log")
    log = manager.get_logger("test.no_accumulate")
    first_count = len(log._logger.handlers)

    for index in range(3):
        manager.configure(
            level=LogLevel.INFO, console=True, log_file=tmp_path / f"{index}.log"
        )

    assert len(log._logger.handlers) == first_count
    manager.shutdown()


# -- Shutdown --


@pytest.mark.unit
def test_shutdown_detaches_handlers_not_just_closes_them(tmp_path):
    """A closed FileHandler that is still attached silently reopens its file on
    the next record, so closing alone left logging running after shutdown."""
    manager = LogManager()
    manager.configure(level=LogLevel.INFO, console=False, log_file=tmp_path / "e.log")
    log = manager.get_logger("test.detach")
    log.info("before")

    manager.shutdown()

    assert log._logger.handlers == []


@pytest.mark.unit
def test_nothing_is_written_after_shutdown(tmp_path):
    log_file = tmp_path / "engine.log"
    manager = LogManager()
    manager.configure(level=LogLevel.INFO, console=False, log_file=log_file)
    log = manager.get_logger("test.after_shutdown")
    log.info("before shutdown")
    manager.shutdown()

    log.info("after shutdown")

    contents = log_file.read_text()
    assert "before shutdown" in contents
    assert "after shutdown" not in contents


@pytest.mark.unit
def test_shutdown_is_idempotent(tmp_path):
    manager = LogManager()
    manager.configure(level=LogLevel.INFO, console=False, log_file=tmp_path / "e.log")
    manager.get_logger("test.double_shutdown")

    manager.shutdown()
    manager.shutdown()


# -- configure() --


@pytest.mark.unit
def test_configure_can_detach_the_dispatcher():
    """`if dispatcher:` meant None was indistinguishable from "unspecified",
    so event integration could be switched on but never off."""

    class FakeDispatcher:
        def dispatch(self, event) -> None: ...

    manager = LogManager()
    manager.configure(console=False, dispatcher=FakeDispatcher())
    assert manager._event_dispatcher is not None

    manager.configure(console=False, dispatcher=None)

    assert manager._event_dispatcher is None
    manager.shutdown()


@pytest.mark.unit
def test_configure_without_a_dispatcher_argument_keeps_the_current_one():
    class FakeDispatcher:
        def dispatch(self, event) -> None: ...

    dispatcher = FakeDispatcher()
    manager = LogManager()
    manager.configure(console=False, dispatcher=dispatcher)

    manager.configure(level=LogLevel.DEBUG, console=False)

    assert manager._event_dispatcher is dispatcher
    manager.shutdown()


@pytest.mark.unit
def test_propagation_can_be_disabled(captured):
    """Engine loggers install their own console handler, so an application
    that also configures root logging sees every record twice. Propagation is
    left on by default -- it is what lets an app capture engine output -- but
    must be switchable."""
    log, _ = captured
    assert log._logger.propagate is True

    log.reconfigure(
        level=LogLevel.INFO,
        event_dispatcher=None,
        log_file=None,
        console_output=True,
        propagate=False,
    )

    assert log._logger.propagate is False


# -- Structured context reaches events --


@pytest.mark.unit
def test_structured_fields_reach_the_dispatched_event():
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.log.events import OnLogEvent

    dispatcher = EventDispatcher()
    seen: list[OnLogEvent] = []
    dispatcher.subscribe(OnLogEvent, lambda e: seen.append(e))

    manager = LogManager()
    manager.configure(level=LogLevel.INFO, console=False, dispatcher=dispatcher)
    manager.get_logger("test.context").info("loading", asset="hero.png", retries=2)

    assert seen[-1].context["asset"] == "hero.png"
    assert seen[-1].context["retries"] == 2
    manager.shutdown()


@pytest.mark.unit
def test_event_context_reports_the_real_call_site():
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.log.events import OnLogEvent

    dispatcher = EventDispatcher()
    seen: list[OnLogEvent] = []
    dispatcher.subscribe(OnLogEvent, lambda e: seen.append(e))

    manager = LogManager()
    manager.configure(level=LogLevel.INFO, console=False, dispatcher=dispatcher)
    manager.get_logger("test.event_site").info("hello")

    assert seen[-1].context["module"] == "test_log_manager"
    manager.shutdown()


@pytest.mark.unit
def test_a_reserved_attribute_name_is_renamed_rather_than_dropped():
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.log.events import OnLogEvent

    dispatcher = EventDispatcher()
    seen: list[OnLogEvent] = []
    dispatcher.subscribe(OnLogEvent, lambda e: seen.append(e))

    manager = LogManager()
    manager.configure(level=LogLevel.INFO, console=False, dispatcher=dispatcher)
    manager.get_logger("test.reserved").info("m", module="mine", filename="x.py")

    assert seen[-1].context["module_"] == "mine"
    assert seen[-1].context["filename_"] == "x.py"
    manager.shutdown()


@pytest.mark.unit
def test_the_category_defaults_per_level():
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.log.events import OnLogEvent
    from pyguara.log.types import LogCategory

    dispatcher = EventDispatcher()
    seen: list[OnLogEvent] = []
    dispatcher.subscribe(OnLogEvent, lambda e: seen.append(e))

    manager = LogManager()
    manager.configure(level=LogLevel.DEBUG, console=False, dispatcher=dispatcher)
    log = manager.get_logger("test.categories")

    log.debug("d")
    log.info("i")
    log.performance("op", 0.5)
    log.warning("w", category=LogCategory.PHYSICS)

    assert [e.category for e in seen] == [
        LogCategory.DEBUG,
        LogCategory.SYSTEM,
        LogCategory.PERFORMANCE,
        LogCategory.PHYSICS,
    ]
    manager.shutdown()
