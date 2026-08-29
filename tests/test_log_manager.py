"""Regression tests for EngineLogger's kwargs-to-extra handling (LOG-1)."""

import logging

import pytest

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
