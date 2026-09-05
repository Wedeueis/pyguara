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
