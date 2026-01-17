"""Tests for coroutine scripting system."""

from pyguara.scripting.coroutines import (
    Coroutine,
    CoroutineManager,
    WaitForSeconds,
    WaitUntil,
    WaitWhile,
    wait_for_seconds,
    wait_until,
    wait_while,
)


class TestWaitInstructions:
    """Test wait instruction classes."""

    def test_wait_for_seconds_completes(self):
        """WaitForSeconds should complete after duration."""
        wait = WaitForSeconds(1.0)

        # Not complete initially
        assert not wait.is_complete(0.0)

        # Not complete after partial time
        assert not wait.is_complete(0.5)

        # Complete after full duration
        assert wait.is_complete(0.5)

    def test_wait_for_seconds_immediate(self):
        """WaitForSeconds with 0 duration should complete immediately."""
        wait = WaitForSeconds(0.0)

        assert wait.is_complete(0.0)

    def test_wait_until_condition_false(self):
        """WaitUntil should wait while condition is false."""
        flag = {"value": False}
        wait = WaitUntil(lambda: flag["value"])

        assert not wait.is_complete(0.0)

    def test_wait_until_condition_true(self):
        """WaitUntil should complete when condition becomes true."""
        flag = {"value": False}
        wait = WaitUntil(lambda: flag["value"])

        assert not wait.is_complete(0.0)

        flag["value"] = True
        assert wait.is_complete(0.0)

    def test_wait_while_condition_true(self):
        """WaitWhile should wait while condition is true."""
        flag = {"value": True}
        wait = WaitWhile(lambda: flag["value"])

        assert not wait.is_complete(0.0)

    def test_wait_while_condition_false(self):
        """WaitWhile should complete when condition becomes false."""
        flag = {"value": True}
        wait = WaitWhile(lambda: flag["value"])

        assert not wait.is_complete(0.0)

        flag["value"] = False
        assert wait.is_complete(0.0)


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_wait_for_seconds_function(self):
        """wait_for_seconds should create WaitForSeconds."""
        wait = wait_for_seconds(2.0)

        assert isinstance(wait, WaitForSeconds)
        assert wait.duration == 2.0

    def test_wait_until_function(self):
        """wait_until should create WaitUntil."""

        def condition():
            return True

        wait = wait_until(condition)

        assert isinstance(wait, WaitUntil)
        assert wait.condition is condition

    def test_wait_while_function(self):
        """wait_while should create WaitWhile."""

        def condition():
            return False

        wait = wait_while(condition)

        assert isinstance(wait, WaitWhile)
        assert wait.condition is condition


class TestCoroutine:
    """Test Coroutine class."""

    def test_simple_coroutine(self):
        """Simple coroutine should execute to completion."""
        executed = []

        def simple():
            executed.append(1)
            yield
            executed.append(2)
            yield
            executed.append(3)

        coro = Coroutine(simple())

        # First update: executes up to first yield
        assert coro.update(0.016)
        assert executed == [1]
        assert not coro.is_complete

        # Second update: executes to second yield
        assert coro.update(0.016)
        assert executed == [1, 2]
        assert not coro.is_complete

        # Third update: executes to completion
        assert not coro.update(0.016)
        assert executed == [1, 2, 3]
        assert coro.is_complete

    def test_coroutine_with_wait_for_seconds(self):
        """Coroutine should wait for specified duration."""
        executed = []

        def wait_sequence():
            executed.append("start")
            yield wait_for_seconds(1.0)
            executed.append("after_wait")

        coro = Coroutine(wait_sequence())

        # First update: start and begin waiting
        assert coro.update(0.016)
        assert executed == ["start"]

        # Wait not complete yet
        assert coro.update(0.5)
        assert executed == ["start"]

        # Wait complete, continue
        assert not coro.update(0.5)
        assert executed == ["start", "after_wait"]
        assert coro.is_complete

    def test_coroutine_with_wait_until(self):
        """Coroutine should wait until condition is true."""
        executed = []
        flag = {"value": False}

        def wait_sequence():
            executed.append("start")
            yield wait_until(lambda: flag["value"])
            executed.append("after_wait")

        coro = Coroutine(wait_sequence())

        # Start and begin waiting
        assert coro.update(0.016)
        assert executed == ["start"]

        # Condition still false
        assert coro.update(0.016)
        assert executed == ["start"]

        # Set condition to true
        flag["value"] = True
        assert not coro.update(0.016)
        assert executed == ["start", "after_wait"]

    def test_coroutine_with_wait_while(self):
        """Coroutine should wait while condition is true."""
        executed = []
        flag = {"value": True}

        def wait_sequence():
            executed.append("start")
            yield wait_while(lambda: flag["value"])
            executed.append("after_wait")

        coro = Coroutine(wait_sequence())

        # Start and begin waiting
        assert coro.update(0.016)
        assert executed == ["start"]

        # Condition still true, keep waiting
        assert coro.update(0.016)
        assert executed == ["start"]

        # Set condition to false
        flag["value"] = False
        assert not coro.update(0.016)
        assert executed == ["start", "after_wait"]

    def test_nested_coroutine(self):
        """Coroutine should support yielding other coroutines."""
        executed = []

        def inner():
            executed.append("inner_start")
            yield
            executed.append("inner_end")

        def outer():
            executed.append("outer_start")
            yield Coroutine(inner())
            executed.append("outer_end")

        coro = Coroutine(outer())

        # Outer starts
        assert coro.update(0.016)
        assert executed == ["outer_start", "inner_start"]

        # Inner and outer both complete
        assert not coro.update(0.016)
        assert executed == ["outer_start", "inner_start", "inner_end", "outer_end"]

    def test_nested_generator(self):
        """Coroutine should auto-wrap yielded generators."""
        executed = []

        def inner():
            executed.append("inner")
            yield

        def outer():
            executed.append("outer")
            yield inner()  # Yield generator directly

        coro = Coroutine(outer())

        assert coro.update(0.016)
        assert executed == ["outer", "inner"]

    def test_stop_coroutine(self):
        """Stopping coroutine should prevent further execution."""
        executed = []

        def sequence():
            executed.append(1)
            yield
            executed.append(2)
            yield
            executed.append(3)

        coro = Coroutine(sequence())

        coro.update(0.016)
        assert executed == [1]

        coro.stop()
        assert coro.is_complete

        # Further updates should do nothing
        coro.update(0.016)
        assert executed == [1]

    def test_stop_nested_coroutine(self):
        """Stopping outer coroutine should stop nested ones."""
        executed = []

        def inner():
            executed.append("inner_start")
            yield
            executed.append("inner_end")

        def outer():
            executed.append("outer_start")
            yield Coroutine(inner())
            executed.append("outer_end")

        coro = Coroutine(outer())

        coro.update(0.016)
        assert executed == ["outer_start", "inner_start"]

        coro.stop()

        # Further updates should do nothing
        coro.update(0.016)
        assert executed == ["outer_start", "inner_start"]


class TestCoroutineManager:
    """Test CoroutineManager class."""

    def test_manager_creation(self):
        """CoroutineManager should initialize empty."""
        manager = CoroutineManager()

        assert manager.active_count == 0

    def test_start_coroutine(self):
        """Should start and track coroutines."""

        def simple():
            yield

        manager = CoroutineManager()
        coro = manager.start_coroutine(simple())

        assert manager.active_count == 1
        assert isinstance(coro, Coroutine)

    def test_update_coroutines(self):
        """Should update all active coroutines."""
        executed = []

        def coro1():
            executed.append("coro1_1")
            yield
            executed.append("coro1_2")

        def coro2():
            executed.append("coro2_1")
            yield
            executed.append("coro2_2")

        manager = CoroutineManager()
        manager.start_coroutine(coro1())
        manager.start_coroutine(coro2())

        # First update
        manager.update(0.016)
        assert "coro1_1" in executed
        assert "coro2_1" in executed
        assert manager.active_count == 2

        # Second update - both complete
        manager.update(0.016)
        assert "coro1_2" in executed
        assert "coro2_2" in executed
        assert manager.active_count == 0

    def test_auto_remove_completed(self):
        """Completed coroutines should be auto-removed."""

        def short():
            yield

        def long():
            yield
            yield
            yield

        manager = CoroutineManager()
        manager.start_coroutine(short())
        manager.start_coroutine(long())

        assert manager.active_count == 2

        # After one update, both still active
        manager.update(0.016)
        assert manager.active_count == 2

        # After second update, short completes
        manager.update(0.016)
        assert manager.active_count == 1

    def test_stop_specific_coroutine(self):
        """Should be able to stop specific coroutine."""

        def sequence():
            yield
            yield
            yield

        manager = CoroutineManager()
        coro1 = manager.start_coroutine(sequence())
        manager.start_coroutine(sequence())

        assert manager.active_count == 2

        manager.stop_coroutine(coro1)
        assert manager.active_count == 1

        # Verify coro2 still runs
        manager.update(0.016)
        assert manager.active_count == 1

    def test_stop_nonexistent_coroutine(self):
        """Stopping nonexistent coroutine should return False."""

        def sequence():
            yield

        manager = CoroutineManager()
        coro = Coroutine(sequence())

        result = manager.stop_coroutine(coro)
        assert result is False

    def test_stop_all(self):
        """Should stop all active coroutines."""

        def sequence():
            yield
            yield
            yield

        manager = CoroutineManager()
        manager.start_coroutine(sequence())
        manager.start_coroutine(sequence())
        manager.start_coroutine(sequence())

        assert manager.active_count == 3

        manager.stop_all()
        assert manager.active_count == 0

    def test_active_coroutines_is_copy(self):
        """active_coroutines should return a copy."""

        def sequence():
            yield

        manager = CoroutineManager()
        manager.start_coroutine(sequence())

        active = manager.active_coroutines
        active.clear()

        assert manager.active_count == 1


class TestCoroutineIntegration:
    """Test complex coroutine scenarios."""

    def test_sequence_with_multiple_waits(self):
        """Coroutine with multiple wait instructions."""
        executed = []

        def sequence():
            executed.append("start")
            yield wait_for_seconds(0.5)
            executed.append("after_0.5s")
            yield wait_for_seconds(0.5)
            executed.append("after_1.0s")
            yield wait_for_seconds(0.5)
            executed.append("after_1.5s")

        manager = CoroutineManager()
        manager.start_coroutine(sequence())

        # Start
        manager.update(0.016)
        assert executed == ["start"]

        # First wait (need ~0.5s)
        for _ in range(31):  # 31 * 0.016 = 0.496
            manager.update(0.016)
        manager.update(0.016)  # Complete first wait
        assert "after_0.5s" in executed

        # Second wait
        for _ in range(31):
            manager.update(0.016)
        manager.update(0.016)
        assert "after_1.0s" in executed

        # Third wait
        for _ in range(31):
            manager.update(0.016)
        manager.update(0.016)
        assert "after_1.5s" in executed

        assert manager.active_count == 0

    def test_parallel_coroutines_with_different_durations(self):
        """Multiple coroutines with different completion times."""
        results = []

        def fast():
            yield wait_for_seconds(0.1)
            results.append("fast")

        def medium():
            yield wait_for_seconds(0.2)
            results.append("medium")

        def slow():
            yield wait_for_seconds(0.3)
            results.append("slow")

        manager = CoroutineManager()
        manager.start_coroutine(fast())
        manager.start_coroutine(medium())
        manager.start_coroutine(slow())

        # Update for 0.15s (fast completes)
        for _ in range(10):
            manager.update(0.016)

        assert "fast" in results
        assert manager.active_count == 2

        # Update for another 0.1s (medium completes)
        for _ in range(7):
            manager.update(0.016)

        assert "medium" in results
        assert manager.active_count == 1

        # Update for another 0.15s (slow completes)
        for _ in range(10):
            manager.update(0.016)

        assert "slow" in results
        assert manager.active_count == 0

    def test_coroutine_chain(self):
        """Coroutine that starts other coroutines."""
        executed = []

        def subtask():
            executed.append("subtask_start")
            yield wait_for_seconds(0.1)
            executed.append("subtask_end")

        def main_task():
            executed.append("main_start")
            yield subtask()
            executed.append("main_middle")
            yield subtask()
            executed.append("main_end")

        manager = CoroutineManager()
        manager.start_coroutine(main_task())

        # Start main and first subtask
        manager.update(0.016)
        assert executed == ["main_start", "subtask_start"]

        # Complete first subtask
        for _ in range(7):
            manager.update(0.016)

        assert "subtask_end" in executed
        assert "main_middle" in executed

        # Complete second subtask
        for _ in range(7):
            manager.update(0.016)

        assert executed[-1] == "main_end"
        assert manager.active_count == 0

    def test_conditional_waiting(self):
        """Use wait_until for game state checking."""
        game_state = {"score": 0}

        def wait_for_score():
            yield wait_until(lambda: game_state["score"] >= 10)

        manager = CoroutineManager()
        manager.start_coroutine(wait_for_score())

        # Coroutine waits
        for _ in range(10):
            manager.update(0.016)
            game_state["score"] += 1

        assert manager.active_count == 1

        # Score reaches 10
        manager.update(0.016)
        assert manager.active_count == 0

    def test_yield_none_continues_immediately(self):
        """Yielding None should continue on next update."""
        executed = []

        def sequence():
            executed.append(1)
            yield None
            executed.append(2)
            yield None
            executed.append(3)

        coro = Coroutine(sequence())

        coro.update(0.016)
        assert executed == [1]

        coro.update(0.016)
        assert executed == [1, 2]

        coro.update(0.016)
        assert executed == [1, 2, 3]
