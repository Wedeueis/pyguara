"""A second process for `test_net_udp.py`: a real peer on a real socket.

Not collected as a test. Reports what it sees as lines on stdout.
"""

from __future__ import annotations

import sys
import time

from pyguara.net import (
    Channel,
    ClientSession,
    Invite,
    Joined,
    MessageReceived,
    UdpTransport,
    Versions,
)


def hold_the_gil(seconds: float) -> None:
    """Keep the GIL for about `seconds`, with no chance for a thread to take it.

    `time.sleep` releases it, and a Python busy loop offers it every 5 ms, so a
    test using either would pass even if the socket thread needed the GIL. A single
    C call that never returns to the interpreter does hold it.
    """
    sample = 2_000_000
    began = time.perf_counter()
    sum(range(sample))
    per_item = (time.perf_counter() - began) / sample
    sum(range(int(seconds / per_item)))


def main() -> int:
    """Join, optionally stall with the GIL held, then count what arrived."""
    invite = Invite.parse(sys.argv[1])
    stall = float(sys.argv[2])
    versions = Versions("test", "test")
    transport = UdpTransport.client(
        invite.key, 424242, invite.host, invite.port, versions.encode()
    )
    session = ClientSession(transport)
    received = 0
    stalled = stall == 0
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        for event in session.poll():
            if isinstance(event, Joined):
                print("joined", flush=True)
            elif isinstance(event, MessageReceived):
                received += 1
                if event.data == b"done":
                    print(f"received {received}", flush=True)
                    session.send(Channel.EVENTS, b"thanks")
                    time.sleep(0.2)
                    session.close()
                    return 0
        if session.joined and not stalled:
            stalled = True
            print("stalling", flush=True)
            hold_the_gil(stall)
            print("resumed", flush=True)
        time.sleep(0.005)
    print(f"timed out after {received}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
