from dataclasses import dataclass
from pyguara.events.protocols import Event


@dataclass
class CustomEvent(Event):
    data: str
    timestamp: float = 0.0
    source: object = None


def test_subscribe_and_dispatch(event_dispatcher):
    received = []

    def handler(event: CustomEvent):
        received.append(event.data)

    event_dispatcher.subscribe(CustomEvent, handler)
    event_dispatcher.dispatch(CustomEvent(data="hello"))

    assert len(received) == 1
    assert received[0] == "hello"


def test_unsubscribe(event_dispatcher):
    received = []

    def handler(event: CustomEvent):
        received.append(event.data)

    event_dispatcher.subscribe(CustomEvent, handler)
    event_dispatcher.unsubscribe(CustomEvent, handler)
    event_dispatcher.dispatch(CustomEvent(data="hello"))

    assert len(received) == 0


def test_priority(event_dispatcher):
    order = []

    def handler_low(e):
        order.append("low")

    def handler_high(e):
        order.append("high")

    event_dispatcher.subscribe(CustomEvent, handler_low, priority=1)
    event_dispatcher.subscribe(CustomEvent, handler_high, priority=10)

    event_dispatcher.dispatch(CustomEvent(data=""))

    assert order == ["high", "low"]


def test_event_queue(event_dispatcher):
    received = []

    def handler(e):
        received.append(e.data)

    event_dispatcher.subscribe(CustomEvent, handler)

    # Queue event
    event_dispatcher.queue_event(CustomEvent(data="queued"))
    assert len(received) == 0  # Not processed yet

    # Process
    event_dispatcher.process_queue()
    assert len(received) == 1
    assert received[0] == "queued"


def test_event_filtering(event_dispatcher):
    received = []

    def handler(e):
        received.append(e.data)

    # Only accept data="yes"
    event_dispatcher.subscribe(
        CustomEvent, handler, filter_func=lambda e: e.data == "yes"
    )

    event_dispatcher.dispatch(CustomEvent(data="no"))
    event_dispatcher.dispatch(CustomEvent(data="yes"))

    assert len(received) == 1
    assert received[0] == "yes"
