from dataclasses import dataclass
from typing import Any
from pyguara.events.protocols import Event


@dataclass
class CustomEvent(Event):
    data: str
    timestamp: float = 0.0
    source: object = None


def test_subscribe_and_dispatch(event_dispatcher) -> None:
    received = []

    def handler(event: CustomEvent):
        received.append(event.data)

    event_dispatcher.subscribe(CustomEvent, handler)
    event_dispatcher.dispatch(CustomEvent(data="hello"))

    assert len(received) == 1
    assert received[0] == "hello"


def test_unsubscribe(event_dispatcher) -> None:
    received = []

    def handler(event: CustomEvent):
        received.append(event.data)

    event_dispatcher.subscribe(CustomEvent, handler)
    event_dispatcher.unsubscribe(CustomEvent, handler)
    event_dispatcher.dispatch(CustomEvent(data="hello"))

    assert len(received) == 0


def test_priority(event_dispatcher) -> None:
    order = []

    def handler_low(e):
        order.append("low")

    def handler_high(e):
        order.append("high")

    event_dispatcher.subscribe(CustomEvent, handler_low, priority=1)
    event_dispatcher.subscribe(CustomEvent, handler_high, priority=10)

    event_dispatcher.dispatch(CustomEvent(data=""))

    assert order == ["high", "low"]


def test_event_queue(event_dispatcher) -> None:
    received = []

    def handler(e: Any) -> None:
        received.append(e.data)

    event_dispatcher.subscribe(CustomEvent, handler)

    # Queue event
    event_dispatcher.queue_event(CustomEvent(data="queued"))
    assert len(received) == 0  # Not processed yet

    # Process
    event_dispatcher.process_queue()
    assert len(received) == 1
    assert received[0] == "queued"


def test_event_filtering(event_dispatcher) -> None:
    received = []

    def handler(e: Any) -> None:
        received.append(e.data)

    # Only accept data="yes"
    event_dispatcher.subscribe(
        CustomEvent, handler, filter_func=lambda e: e.data == "yes"
    )

    event_dispatcher.dispatch(CustomEvent(data="no"))
    event_dispatcher.dispatch(CustomEvent(data="yes"))

    assert len(received) == 1
    assert received[0] == "yes"


def test_error_handling_strategy_raise():
    """Test that RAISE strategy re-raises exceptions."""
    import pytest
    import logging
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.events.types import ErrorHandlingStrategy

    logger = logging.getLogger("test")
    dispatcher = EventDispatcher(
        logger=logger, error_strategy=ErrorHandlingStrategy.RAISE
    )

    def failing_handler(e: CustomEvent) -> None:
        raise ValueError("Test error")

    dispatcher.subscribe(CustomEvent, failing_handler)

    # Should re-raise the exception
    with pytest.raises(ValueError, match="Test error"):
        dispatcher.dispatch(CustomEvent(data="test"))


def test_error_handling_strategy_log():
    """Test that LOG strategy logs and continues."""
    import logging
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.events.types import ErrorHandlingStrategy

    logger = logging.getLogger("test")
    dispatcher = EventDispatcher(
        logger=logger, error_strategy=ErrorHandlingStrategy.LOG
    )

    execution_order = []

    def failing_handler(e: CustomEvent) -> None:
        execution_order.append("failing")
        raise ValueError("Test error")

    def success_handler(e: CustomEvent) -> None:
        execution_order.append("success")

    dispatcher.subscribe(CustomEvent, failing_handler, priority=10)
    dispatcher.subscribe(CustomEvent, success_handler, priority=5)

    # Should log error and continue to next handler
    dispatcher.dispatch(CustomEvent(data="test"))

    # Both handlers should have been called
    assert execution_order == ["failing", "success"]


def test_error_handling_strategy_ignore():
    """Test that IGNORE strategy silently ignores errors."""
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.events.types import ErrorHandlingStrategy

    dispatcher = EventDispatcher(error_strategy=ErrorHandlingStrategy.IGNORE)

    execution_order = []

    def failing_handler(e: CustomEvent) -> None:
        execution_order.append("failing")
        raise ValueError("Test error")

    def success_handler(e: CustomEvent) -> None:
        execution_order.append("success")

    dispatcher.subscribe(CustomEvent, failing_handler, priority=10)
    dispatcher.subscribe(CustomEvent, success_handler, priority=5)

    # Should silently ignore error and continue
    dispatcher.dispatch(CustomEvent(data="test"))

    # Both handlers should have been called
    assert execution_order == ["failing", "success"]


def test_error_message_includes_context():
    """Test that error messages include handler and event type information."""
    import pytest
    import logging
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.events.types import ErrorHandlingStrategy
    from unittest.mock import MagicMock

    logger = MagicMock(spec=logging.Logger)
    dispatcher = EventDispatcher(
        logger=logger, error_strategy=ErrorHandlingStrategy.RAISE
    )

    def my_failing_handler(e: CustomEvent) -> None:
        raise ValueError("Test error")

    dispatcher.subscribe(CustomEvent, my_failing_handler)

    # Should log error with context
    with pytest.raises(ValueError):
        dispatcher.dispatch(CustomEvent(data="test"))

    # Verify logger was called with error message containing context
    logger.error.assert_called_once()
    error_msg = logger.error.call_args[0][0]
    assert "my_failing_handler" in error_msg
    assert "CustomEvent" in error_msg
    assert "Test error" in error_msg
